#!/usr/bin/env python3
"""Tiny API for the dashboard: apps (add/edit/delete/move) and sections. Form posts, redirects back to /."""
import json, os, re, secrets, threading
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

ROOT = "/var/www/home"
APPS = f"{ROOT}/apps.json"
SECTIONS = f"{ROOT}/sections.json"
ICONS = f"{ROOT}/icons"
MAX_BODY = 2 * 1024 * 1024
ICON_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp",
              "image/svg+xml": "svg", "image/x-icon": "ico", "image/vnd.microsoft.icon": "ico"}
lock = threading.Lock()


def load():
    with open(APPS) as f:
        return json.load(f)


def save(apps):
    # written in place (not tmp+rename) so home-status.path sees the change
    with open(APPS, "w") as f:
        f.write(json.dumps(apps, indent=2, ensure_ascii=False))


def load_sections(apps):
    """Ordered section names; any group used by an app but missing from the file is appended."""
    try:
        with open(SECTIONS) as f:
            sections = json.load(f)
    except FileNotFoundError:
        sections = []
    for a in apps:
        if a["group"] not in sections:
            sections.append(a["group"])
    return sections


def save_sections(sections):
    with open(SECTIONS, "w") as f:
        f.write(json.dumps(sections, indent=2, ensure_ascii=False))


def move_app(apps, app_id, group, index):
    """Move app into group at position index (among that group's apps)."""
    app = next((a for a in apps if a["id"] == app_id), None)
    if app is None:
        return False
    apps.remove(app)
    app["group"] = group
    peers = [a for a in apps if a["group"] == group]
    if index < len(peers):
        apps.insert(apps.index(peers[index]), app)
    elif peers:
        apps.insert(apps.index(peers[-1]) + 1, app)
    else:
        apps.append(app)
    return True


def section_action(path, form, apps, sections):
    """Handle /api/sections/*. Returns an error code or None."""
    name = form.get("name", "")[:40]
    if path == "/api/sections/add":
        if not name:
            return "invalid"
        if name in sections:
            return "exists"
        sections.append(name)
    elif path == "/api/sections/rename":
        old = form.get("old", "")
        if not name or old not in sections:
            return "invalid"
        if name != old and name in sections:
            return "exists"
        sections[sections.index(old)] = name
        for a in apps:
            if a["group"] == old:
                a["group"] = name
    elif path == "/api/sections/delete":
        if any(a["group"] == name for a in apps):
            return "notempty"
        if name in sections:
            sections.remove(name)
    elif path == "/api/sections/move":
        if name not in sections:
            return "invalid"
        i = sections.index(name)
        j = i - 1 if form.get("dir") == "up" else i + 1
        if 0 <= j < len(sections):
            sections[i], sections[j] = sections[j], sections[i]
    else:
        return "notfound"
    return None


def valid_url(u):
    return bool(re.match(r"^https?://[^\s\"'<>]+$", u))


def slug(name, taken):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "app"
    s, n = base, 2
    while s in taken:
        s, n = f"{base}-{n}", n + 1
    return s


def parse_form(headers, body):
    """Return (fields, files) for urlencoded or multipart bodies. files: name -> (content_type, bytes)."""
    ctype = headers.get("Content-Type", "")
    if not ctype.startswith("multipart/form-data"):
        return {k: v[0].strip() for k, v in parse_qs(body.decode()).items()}, {}
    msg = BytesParser(policy=HTTP).parsebytes(b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + body)
    fields, files = {}, {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        data = part.get_payload(decode=True) or b""
        if part.get_filename() is not None:
            if data:
                files[name] = (part.get_content_type(), data)
        else:
            fields[name] = data.decode("utf-8", "replace").strip()
    return fields, files


def store_icon(app_id, upload):
    ctype, data = upload
    ext = ICON_TYPES.get(ctype)
    if not ext:
        raise ValueError("icon type")
    os.makedirs(ICONS, exist_ok=True)
    name = f"{app_id}-{secrets.token_hex(4)}.{ext}"
    with open(f"{ICONS}/{name}", "wb") as f:
        f.write(data)
    return f"icons/{name}"


def remove_icon(app):
    path = app.pop("iconFile", None)
    if path and re.fullmatch(r"icons/[\w.-]+", path):
        try:
            os.remove(f"{ROOT}/{path}")
        except FileNotFoundError:
            pass


def apply_fields(app, form, files):
    """Validate and copy form fields onto app. Returns False if input is invalid."""
    name, url, ip = form.get("name", ""), form.get("url", ""), form.get("ip", "")
    if not name or not valid_url(url) or (ip and not valid_url(ip)):
        return False
    app.update(name=name[:60], url=url, group=form.get("group", "")[:40] or "Other",
               icon=form.get("icon", "")[:8] or "🔗")
    for key, val in (("ip", ip), ("note", form.get("note", "")[:80])):
        if val:
            app[key] = val
        else:
            app.pop(key, None)
    if "iconFile" in files:
        new = store_icon(app["id"], files["iconFile"])
        remove_icon(app)
        app["iconFile"] = new
    elif form.get("removeIcon"):
        remove_icon(app)
    return True


class Handler(BaseHTTPRequestHandler):
    def back(self, msg=None):
        self.send_response(303)
        self.send_header("Location", "/" + (f"?err={msg}" if msg else ""))
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY:
            return self.back("toolarge")
        form, files = parse_form(self.headers, self.rfile.read(length))
        with lock:
            apps = load()
            sections = load_sections(apps)
            if self.path.startswith("/api/sections/"):
                err = section_action(self.path, form, apps, sections)
                if err:
                    return self.back(err)
                save(apps)
                save_sections(sections)
                return self.back()
            try:
                if self.path == "/api/apps/add":
                    app = {"id": slug(form.get("name", ""), {a["id"] for a in apps})}
                    if not apply_fields(app, form, files):
                        return self.back("invalid")
                    apps.append(app)
                elif self.path == "/api/apps/update":
                    app = next((a for a in apps if a["id"] == form.get("id")), None)
                    if app is None:
                        return self.back("notfound")
                    if not apply_fields(app, form, files):
                        return self.back("invalid")
                elif self.path == "/api/apps/move":
                    group = form.get("group", "")
                    if group not in sections or not form.get("index", "").isdigit():
                        return self.back("invalid")
                    if not move_app(apps, form.get("id"), group, int(form["index"])):
                        return self.back("notfound")
                elif self.path == "/api/apps/delete":
                    for a in apps:
                        if a["id"] == form.get("id"):
                            remove_icon(a)
                    apps = [a for a in apps if a["id"] != form.get("id")]
                else:
                    self.send_error(404)
                    return
            except ValueError:
                return self.back("icontype")
            save(apps)
            save_sections(load_sections(apps))
        self.back()

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("127.0.0.1", 8099), Handler).serve_forever()
