#!/usr/bin/env bash
# FREE test of streaming from your phone to your website — no YouTube, no paid service.
#
#   bash live-test/start.sh            → watch on this Mac / same Wi-Fi (local site)
#   bash live-test/start.sh --public   → also a free public https link + the Azure site shows it
#
# Press Ctrl+C to stop. Phone must be on the same Wi-Fi as this Mac.
set -euo pipefail
cd "$(dirname "$0")"
command -v mediamtx >/dev/null || { echo "Install first:  brew install mediamtx"; exit 1; }

[ -f .stream-key ] || openssl rand -hex 8 > .stream-key   # private key, never committed
KEY=$(cat .stream-key)
IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 127.0.0.1)
RG=mk-academy-rg; APP=$(grep ^APP= ../deploy/.azure-app 2>/dev/null | cut -d= -f2 || true)

sed "s/__STREAM_KEY__/$KEY/" mediamtx.yml > .mediamtx.run.yml
mediamtx .mediamtx.run.yml > mediamtx.log 2>&1 &
MTX=$!; TUN=""
cleanup() {
  kill $MTX $TUN 2>/dev/null || true
  if [ -n "$TUN" ] && [ -n "$APP" ]; then
    echo "→ Removing the test stream address from the Azure site…"
    az webapp config appsettings delete -g $RG -n "$APP" --setting-names OWN_LIVE_HLS -o none 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM
sleep 1

HLS="http://$IP:8888/live/index.m3u8"
if [ "${1:-}" = "--public" ]; then
  cloudflared tunnel --url http://localhost:8888 --no-autoupdate > tunnel.log 2>&1 &
  TUN=$!
  echo "→ Opening a free public link…"
  for _ in $(seq 1 30); do
    URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' tunnel.log | head -1 || true)
    [ -n "$URL" ] && break; sleep 1
  done
  [ -n "${URL:-}" ] || { echo "!! Tunnel did not start, see live-test/tunnel.log"; exit 1; }
  HLS="$URL/live/index.m3u8"
  if [ -n "$APP" ]; then
    echo "→ Pointing the Azure site at it (site restarts, ~30s)…"
    PYTHONWARNINGS=ignore az webapp config appsettings set -g $RG -n "$APP" --settings OWN_LIVE_HLS="$HLS" -o none
  fi
fi

cat <<INFO

══════════════════════════════════════════════════════════════
 📱 LARIX BROADCASTER (phone on the same Wi-Fi)
    Settings → Connections → New connection:
      URL:   rtmp://$IP:1935/live?user=phone&pass=$KEY
    Video: 1280x720, 30 fps, ~2500 kbps, landscape. Tap the red button to go live.

 🌐 WEBSITE
INFO
if [ -n "$TUN" ]; then
  echo "    Public:  https://$APP.azurewebsites.net/live   (stream: $HLS)"
else
  echo "    Run the site with your stream (new terminal, project folder):"
  echo "      OWN_LIVE_HLS=$HLS HOST=0.0.0.0 .venv/bin/python app.py"
  echo "    then open http://127.0.0.1:5000/live  (or http://$IP:5000/live on other devices)"
fi
cat <<INFO
══════════════════════════════════════════════════════════════
 Keep the key private (anyone with it can broadcast). Ctrl+C to stop.
INFO
wait $MTX
