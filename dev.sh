#!/usr/bin/env bash
# One command for local development:
#   • the website (Flask, auto-reloads when you save a file)
#   • the phone live-stream server (MediaMTX) wired into the site's /live page
#
#   bash dev.sh            → site + phone live streaming
#   bash dev.sh --no-live  → site only
#
# Ctrl+C stops everything.
set -euo pipefail
cd "$(dirname "$0")"

[ -x .venv/bin/python ] || { echo "First time: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }
IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 127.0.0.1)

# Pick the first free port from 5000 (5000 is often taken by an IDE run or AirPlay).
PORT=${PORT:-5000}
while lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; do PORT=$((PORT + 1)); done

MTX=""
cleanup() { [ -n "$MTX" ] && kill "$MTX" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

if [ "${1:-}" != "--no-live" ]; then
  command -v mediamtx >/dev/null || { echo "Install the streaming server first:  brew install mediamtx"; exit 1; }
  pkill -f "mediamtx .mediamtx.run.yml" 2>/dev/null && sleep 1 || true   # stop an older copy of this server
  [ -f live-test/.stream-key ] || openssl rand -hex 8 > live-test/.stream-key
  KEY=$(cat live-test/.stream-key)
  sed "s/__STREAM_KEY__/$KEY/g" live-test/mediamtx.yml > live-test/.mediamtx.run.yml
  (cd live-test && exec mediamtx .mediamtx.run.yml > mediamtx.log 2>&1) &
  MTX=$!
  sleep 1
  kill -0 "$MTX" 2>/dev/null || { echo "!! Streaming server failed to start, see live-test/mediamtx.log"; exit 1; }
  export OWN_LIVE_HLS="http://$IP:8888/live/index.m3u8"
  export LIVE_CHECK_SECONDS=10
fi

cat <<INFO

══════════════════════════════════════════════════════════════
 🌐 Website:      http://127.0.0.1:$PORT
    Live page:    http://127.0.0.1:$PORT/live
    Other devices on this Wi-Fi:  http://$IP:$PORT
INFO
if [ -n "$MTX" ]; then cat <<INFO

 📱 Larix Broadcaster (same Wi-Fi):
    URL:  rtmp://$IP:1935/ingest/$KEY
    (or  Server: rtmp://$IP:1935/ingest   Stream key: $KEY)
INFO
fi
cat <<INFO
══════════════════════════════════════════════════════════════
 Edit files and save: the site reloads by itself. Ctrl+C stops everything.

INFO

HOST=0.0.0.0 PORT=$PORT .venv/bin/python app.py
