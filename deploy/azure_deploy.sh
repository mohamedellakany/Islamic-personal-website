#!/usr/bin/env bash
# Deploy to Azure App Service (Free F1, Linux, Python 3.12). Safe to re-run for updates.
# First run:  bash deploy/azure_deploy.sh [app-name] [region]   (both optional)
# Updates:    bash deploy/azure_deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."
STATE=deploy/.azure-app
RG=mk-academy-rg
PLAN=mk-academy-plan

if [ -f "$STATE" ]; then source "$STATE"; fi
APP="${1:-${APP:-}}"
LOC="${2:-${LOC:-westeurope}}"
APP="${APP:-drmoustafakamel-academy}"

# Name must be globally unique (it becomes <name>.azurewebsites.net).
# If someone else already uses it, add a short number automatically.
if [ ! -f "$STATE" ] && host "$APP.azurewebsites.net" >/dev/null 2>&1; then
  OLD="$APP"; APP="$APP-$((RANDOM % 900 + 100))"
  echo "→ '$OLD' is taken, using '$APP' instead"
fi
printf 'APP=%s\nLOC=%s\n' "$APP" "$LOC" > "$STATE"
export PYTHONWARNINGS=ignore   # hide harmless SyntaxWarnings printed by azure-cli itself

az account show >/dev/null 2>&1 || az login

# Regions to try, in order, if one refuses new customers or the free plan.
FALLBACK_REGIONS="uaenorth northeurope swedencentral francecentral germanywestcentral uksouth eastus eastus2 centralus westus2 canadacentral southeastasia"

if ! az webapp show -g "$RG" -n "$APP" >/dev/null 2>&1; then
  # The resource group is only a folder; its region doesn't limit where the app runs.
  az group show -n "$RG" >/dev/null 2>&1 || az group create -n "$RG" -l "$LOC" -o none

  if ! az appservice plan show -g "$RG" -n "$PLAN" >/dev/null 2>&1; then
    CREATED=""
    for R in $LOC $FALLBACK_REGIONS; do
      echo "→ Trying free F1 plan in ${R}…"
      if ERR=$(az appservice plan create -g "$RG" -n "$PLAN" -l "$R" --sku F1 --is-linux -o none 2>&1); then
        CREATED="$R"; break
      fi
      if echo "$ERR" | grep -qiE "disallowed|not accepting|quota|not available|SkuNotAvailable|LocationNotAvailable|NoRegisteredProviderFound|limit"; then
        echo "   ✗ ${R} unavailable, trying next region"
      else
        echo "$ERR"; exit 1   # a different problem: show it and stop
      fi
    done
    [ -n "$CREATED" ] || { echo "!! No region accepted the free plan. Try again later."; exit 1; }
    LOC="$CREATED"
    printf 'APP=%s\nLOC=%s\n' "$APP" "$LOC" > "$STATE"
    echo "   ✓ Using region: ${LOC}"
  fi

  az webapp create -g "$RG" -p "$PLAN" -n "$APP" --runtime "PYTHON:3.12" -o none
fi

# Django: on every start apply database changes, load the catalog the first time,
# create/update the admin login (deploy/azure_admin.sh), then start the site.
# The database lives in /home/data, which Azure keeps across deploys and restarts.
echo "→ Configuring startup + settings…"
az webapp config set -g "$RG" -n "$APP" -o none --startup-file "python manage.py migrate --noinput \
&& python manage.py import_channel --if-empty && python manage.py ensure_admin \
&& python manage.py collectstatic --noinput -v0 \
&& gunicorn --bind=0.0.0.0:8000 --workers 2 --timeout 120 academy.wsgi"
SETTINGS=(SCM_DO_BUILD_DURING_DEPLOYMENT=true DISABLE_COLLECTSTATIC=true DB_PATH=/home/data/db.sqlite3 MEDIA_ROOT=/home/media)
if [ "$(az webapp config appsettings list -g "$RG" -n "$APP" --query "length([?name=='DJANGO_SECRET_KEY'])" -o tsv)" = "0" ]; then
  SETTINGS+=(DJANGO_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')")
fi
az webapp config appsettings set -g "$RG" -n "$APP" -o none --settings "${SETTINGS[@]}"
az webapp update -g "$RG" -n "$APP" --https-only true -o none   # http:// → https:// (admin login is only sent encrypted)

echo "→ Packaging (code + data/channel.json)…"
ZIP="$(mktemp -d)/site.zip"
zip -qr "$ZIP" . -x '.venv/*' '*__pycache__*' '*.DS_Store' 'deploy/.azure-app' '.git/*' '.env' 'data/db.sqlite3*' 'staticfiles/*' 'media/*'

echo "→ Uploading + installing requirements on Azure (2–4 min)…"
az webapp deploy -g "$RG" -n "$APP" --src-path "$ZIP" --type zip -o none

echo ""
echo "✅ Live at: https://$APP.azurewebsites.net"
echo "   Admin:   https://$APP.azurewebsites.net/admin/   (set the login once: bash deploy/azure_admin.sh)"
echo "   Logs:    az webapp log tail -g $RG -n $APP"
