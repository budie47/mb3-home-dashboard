#!/usr/bin/env bash
# Deploy the dashboard to a Debian/Ubuntu host over SSH.
#   ./deploy.sh          install or update code (your apps/sections/icons on the host are kept)
#   ./deploy.sh backup   copy the host's live data into ./backup/ (git-ignored)
set -euo pipefail
cd "$(dirname "$0")"

[ -f deploy.env ] || { echo "Missing deploy.env - copy deploy.env.example and fill it in." >&2; exit 1; }
# shellcheck disable=SC1091
source deploy.env
: "${TARGET:?}" "${SERVER_NAME:?}" "${TITLE:=Homelab}"

if [ "${1:-}" = "backup" ]; then
  dest="backup/$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$dest"
  ssh "$TARGET" 'tar -C /var/www/home -cf - apps.json sections.json icons 2>/dev/null' | tar -C "$dest" -xf -
  echo "Backed up to $dest"
  exit 0
fi

# Build the bundle with placeholders filled in.
stage=$(mktemp -d); trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/web" "$stage/bin" "$stage/systemd"
cp -r web/. "$stage/web/"
# HTML-escape, then escape for the sed replacement
esc() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' | sed -e 's/[&|\\]/\\&/g'; }
sed -i "s|__TITLE__|$(esc "$TITLE")|g" "$stage/web/index.html"
sed "s|__SERVER_NAME__|$SERVER_NAME|" deploy/nginx.conf.template > "$stage/nginx.conf"
cp bin/home-api.py "$stage/bin/home-api"
cp bin/home-check-status.py "$stage/bin/home-check-status"
cp deploy/systemd/* "$stage/systemd/"
cp data/apps.example.json data/sections.example.json deploy/install.sh "$stage/"

tar -C "$stage" -czf - . | ssh "$TARGET" 'd=$(mktemp -d) && tar -C "$d" -xzf - && bash "$d/install.sh" "$d"; rc=$?; rm -rf "$d"; exit $rc'
