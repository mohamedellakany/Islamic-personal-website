#!/usr/bin/env bash
# One-time setup on a fresh Oracle Cloud Ubuntu VM (22.04 / 24.04).
# Run ON THE SERVER from the project folder:  bash deploy/setup_server.sh
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="$(whoami)"
echo "→ Installing into $APP_DIR as $APP_USER"

sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip nginx iptables-persistent

# Python environment
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip -q
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q

# App service (gunicorn on localhost:8000, restarts automatically)
sed -e "s#__APP_DIR__#$APP_DIR#g" -e "s#__APP_USER__#$APP_USER#g" \
  "$APP_DIR/deploy/mk-academy.service" | sudo tee /etc/systemd/system/mk-academy.service >/dev/null

# Daily data refresh from YouTube (03:30 server time)
sed -e "s#__APP_DIR__#$APP_DIR#g" -e "s#__APP_USER__#$APP_USER#g" \
  "$APP_DIR/deploy/mk-sync.service" | sudo tee /etc/systemd/system/mk-sync.service >/dev/null
sudo cp "$APP_DIR/deploy/mk-sync.timer" /etc/systemd/system/mk-sync.timer

# nginx in front (port 80 → gunicorn), static files served directly
sed -e "s#__APP_DIR__#$APP_DIR#g" "$APP_DIR/deploy/nginx.conf" | sudo tee /etc/nginx/sites-available/mk-academy >/dev/null
sudo ln -sf /etc/nginx/sites-available/mk-academy /etc/nginx/sites-enabled/mk-academy
sudo rm -f /etc/nginx/sites-enabled/default
chmod o+x "$HOME" "$APP_DIR" "$APP_DIR/static" 2>/dev/null || true   # let nginx read /static

# Oracle Ubuntu images block everything except SSH in iptables — open 80 + 443
for port in 80 443; do
  sudo iptables -C INPUT -p tcp --dport $port -m state --state NEW -j ACCEPT 2>/dev/null || \
  sudo iptables -I INPUT 6 -p tcp --dport $port -m state --state NEW -j ACCEPT
done
sudo netfilter-persistent save

# First data sync if none was uploaded
if [ ! -f "$APP_DIR/data/channel.json" ]; then
  echo "→ No data/channel.json found, syncing from YouTube (≈1–2 min)…"
  "$APP_DIR/.venv/bin/python" "$APP_DIR/sync.py" || echo "!! Sync failed (YouTube may block cloud IPs). Upload data/channel.json from your Mac instead — see README."
fi

sudo systemctl daemon-reload
sudo systemctl enable --now mk-academy mk-sync.timer
sudo nginx -t && sudo systemctl restart nginx

IP=$(curl -s ifconfig.me || echo "<your-public-ip>")
echo ""
echo "✅ Done. Open:  http://$IP"
echo "   Logs:  sudo journalctl -u mk-academy -f"
