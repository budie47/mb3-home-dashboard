#!/usr/bin/env bash
# Runs on the target host (as root). Called by deploy.sh with the unpacked bundle dir.
set -euo pipefail
src="$1"   # unpacked bundle, see deploy.sh
command -v nginx >/dev/null || { apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nginx curl >/dev/null; }

install -d /var/www/home /var/www/home/vendor
install -d -o www-data -g www-data /var/www/home/icons
install -m 644 "$src/web/index.html" /var/www/home/index.html
install -m 644 "$src/web/vendor/"* /var/www/home/vendor/
install -m 755 "$src/bin/home-api" "$src/bin/home-check-status" /usr/local/bin/

# Seed data only on first install; never overwrite the live list.
[ -f /var/www/home/apps.json ]     || install -o www-data -g www-data -m 644 "$src/apps.example.json" /var/www/home/apps.json
[ -f /var/www/home/sections.json ] || install -o www-data -g www-data -m 644 "$src/sections.example.json" /var/www/home/sections.json
[ -f /var/www/home/status.json ]   || echo '{"checked": 0, "apps": {}}' > /var/www/home/status.json
chown www-data:www-data /var/www/home

install -m 644 "$src/nginx.conf" /etc/nginx/sites-available/home
ln -sf /etc/nginx/sites-available/home /etc/nginx/sites-enabled/home
rm -f /etc/nginx/sites-enabled/default
install -m 644 "$src/systemd/"* /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now home-api.service home-status.timer home-status.path nginx >/dev/null 2>&1
systemctl restart home-api.service
systemctl start home-status.service
nginx -t 2>/dev/null && systemctl reload nginx
echo "Deployed."
