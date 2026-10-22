# Homelab Dashboard

A small, self-hosted start page for the apps in a homelab: one click to each app, a live up/down dot per app, and an edit mode for managing everything from the page itself.

- Cards grouped into sections; on phones it switches to an icon grid
- Status check every minute against each app's internal address
- Edit mode: add, edit and delete apps, upload icons (PNG/JPG/SVG/WebP/GIF/ICO) or use emoji
- Create, rename, reorder and delete sections; drag apps to reorder or move between sections (touch supported)
- No database and no build step: nginx + two small Python scripts (standard library only)

## How it works

| Piece | Where it runs | What it does |
|---|---|---|
| `web/index.html` | nginx, `/var/www/home` | The page. nginx SSI inlines `apps.json`, `sections.json`, `status.json` and SortableJS into it |
| `bin/home-api.py` | `home-api.service` on `127.0.0.1:8099`, proxied at `/api/` | Saves add/edit/delete/move and section changes to `apps.json` / `sections.json`, stores icons |
| `bin/home-check-status.py` | `home-status.timer` (every 60 s) and `home-status.path` (when `apps.json` changes) | Probes each app and writes `status.json` |

## Deploy

Needs a Debian/Ubuntu host (an LXC container works well) you can reach as root over SSH.

```bash
cp deploy.env.example deploy.env   # set TARGET, SERVER_NAME, TITLE
./deploy.sh
```

The first deploy installs nginx and seeds the example apps. Later deploys only update the code: your apps, sections and icons on the host are never overwritten.

To copy the live data from the host into `backup/` (git-ignored):

```bash
./deploy.sh backup
```

## Keeping your links private

Your real app list lives only on the host (`/var/www/home/apps.json`, `sections.json`, `icons/`). The repo contains code and made-up examples in `data/*.example.json`; `.gitignore` excludes `deploy.env`, `backup/` and real data files. Before pushing, a quick check:

```bash
git grep -nIiE "your-domain|192\.168\.|tailnet-name" -- . ':!web/vendor'
```

## Security notes

- There is no login. Anyone who can reach the page can edit it, so keep it on your LAN/VPN, or put it behind your reverse proxy's access list or basic auth.
- Uploaded icons are served with a sandboxing `Content-Security-Policy`, so an uploaded SVG cannot run scripts.

## Credits

Drag and drop by [SortableJS](https://github.com/SortableJS/Sortable) (MIT), vendored in `web/vendor/`.
