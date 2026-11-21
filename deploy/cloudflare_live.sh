#!/usr/bin/env bash
# Copy your Cloudflare live settings from .env to the Azure site (site restarts, ~30s).
#   bash deploy/cloudflare_live.sh        → turn Cloudflare live ON with the values in .env
#   bash deploy/cloudflare_live.sh --off  → remove them (site goes back to YouTube only)
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONWARNINGS=ignore
RG=mk-academy-rg
APP=$(grep ^APP= deploy/.azure-app 2>/dev/null | cut -d= -f2)
[ -n "$APP" ] || { echo "Deploy the site first: bash deploy/azure_deploy.sh"; exit 1; }

if [ "${1:-}" = "--off" ]; then
  az webapp config appsettings delete -g $RG -n "$APP" -o none \
    --setting-names CF_STREAM_CUSTOMER CF_LIVE_INPUT_ID CF_API_TOKEN OWN_LIVE_HLS
  echo "✅ Cloudflare live removed from https://$APP.azurewebsites.net (YouTube only)"; exit 0
fi

[ -f .env ] || { echo "Create .env first:  cp .env.example .env  (then fill in the values)"; exit 1; }
set -a; source .env; set +a
[ -n "${CF_STREAM_CUSTOMER:-}" ] && [ -n "${CF_LIVE_INPUT_ID:-}" ] && [[ "$CF_STREAM_CUSTOMER" != *xxxx* ]] \
  || { echo "Fill in CF_STREAM_CUSTOMER and CF_LIVE_INPUT_ID in .env"; exit 1; }

SETTINGS=(CF_STREAM_CUSTOMER="$CF_STREAM_CUSTOMER" CF_LIVE_INPUT_ID="$CF_LIVE_INPUT_ID")
[ -n "${CF_API_TOKEN:-}" ] && SETTINGS+=(CF_API_TOKEN="$CF_API_TOKEN")
az webapp config appsettings set -g $RG -n "$APP" -o none --settings "${SETTINGS[@]}"
echo "✅ Cloudflare live ON for https://$APP.azurewebsites.net/live"
echo "   Check: https://$APP.azurewebsites.net/healthz  →  \"cloudflare\": {\"configured\": true}"
