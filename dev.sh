#!/usr/bin/env bash
# Run the website locally with auto-reload (save a file → the site reloads). Ctrl+C to stop.
#
#   bash dev.sh
#
# Cloudflare live streaming: put your settings in .env (copy .env.example), they load automatically.
set -euo pipefail
cd "$(dirname "$0")"

[ -x .venv/bin/python ] || { echo "First time: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }
.venv/bin/python -c "import django" 2>/dev/null || { echo "Install the new requirements first:  .venv/bin/pip install -r requirements.txt"; exit 1; }
# Local settings (Cloudflare etc.) from .env, if present
if [ -f .env ]; then set -a; source .env; set +a; fi
if [ -n "${CF_STREAM_CUSTOMER:-}" ] && [ -n "${CF_LIVE_INPUT_ID:-}" ]; then
  LIVE_INFO="Cloudflare live input ${CF_LIVE_INPUT_ID:0:8}… (checked every 20s)"
else
  LIVE_INFO="YouTube only (add Cloudflare settings to .env to use your own stream)"
fi
IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 127.0.0.1)

# Pick the first free port from 5000 (5000 is often taken by an IDE run or AirPlay).
PORT=${PORT:-5000}
while lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; do PORT=$((PORT + 1)); done

cat <<INFO

══════════════════════════════════════════════════════════════
 🌐 Website:    http://127.0.0.1:$PORT
    Admin:      http://127.0.0.1:$PORT/admin/   (first time: .venv/bin/python manage.py createsuperuser)
    Live page:  http://127.0.0.1:$PORT/live
    Other devices on this Wi-Fi:  http://$IP:$PORT
 📡 Live source: $LIVE_INFO
══════════════════════════════════════════════════════════════
 Edit files and save: the site reloads by itself. Ctrl+C to stop.

INFO

export DJANGO_DEBUG=1
.venv/bin/python manage.py migrate --noinput -v0           # create/update the database (data/db.sqlite3)
.venv/bin/python manage.py import_channel --if-empty       # first time only: load the lessons
exec .venv/bin/python manage.py runserver "0.0.0.0:$PORT"
