#!/usr/bin/env bash
# Run the website locally with auto-reload (save a file → the site reloads). Ctrl+C to stop.
#
#   bash dev.sh
#
# To test your own live stream (e.g. Cloudflare Stream), pass its HLS address:
#   OWN_LIVE_HLS=https://customer-xxxx.cloudflarestream.com/<input-id>/manifest/video.m3u8 bash dev.sh
set -euo pipefail
cd "$(dirname "$0")"

[ -x .venv/bin/python ] || { echo "First time: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }
IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 127.0.0.1)

# Pick the first free port from 5000 (5000 is often taken by an IDE run or AirPlay).
PORT=${PORT:-5000}
while lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; do PORT=$((PORT + 1)); done

cat <<INFO

══════════════════════════════════════════════════════════════
 🌐 Website:    http://127.0.0.1:$PORT
    Live page:  http://127.0.0.1:$PORT/live
    Other devices on this Wi-Fi:  http://$IP:$PORT
══════════════════════════════════════════════════════════════
 Edit files and save: the site reloads by itself. Ctrl+C to stop.

INFO

HOST=0.0.0.0 PORT=$PORT exec .venv/bin/python app.py
