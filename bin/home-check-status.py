#!/usr/bin/env python3
"""Probe each app's real IP and write status.json for the dashboard."""
import json, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

ROOT = "/var/www/home"

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None

opener = urllib.request.build_opener(NoRedirect)

def probe(app):
    start = time.time()
    try:
        opener.open(app.get("ip") or app["url"], timeout=4)
        up = True
    except urllib.error.HTTPError:
        up = True  # any HTTP response (302, 401...) means the service answered
    except Exception:
        up = False
    return app["id"], {"up": up, "ms": int((time.time() - start) * 1000)}

apps = json.load(open(f"{ROOT}/apps.json"))
with ThreadPoolExecutor(8) as ex:
    result = dict(ex.map(probe, apps))
out = {"checked": int(time.time()), "apps": result}
tmp = f"{ROOT}/status.json.tmp"
json.dump(out, open(tmp, "w"))
import os; os.replace(tmp, f"{ROOT}/status.json")
