#!/usr/bin/env bash
# Set (or change) the login for https://<your-site>/admin/ on Azure. Site restarts (~30s).
#   bash deploy/azure_admin.sh
# The password is typed here (hidden) and stored as an Azure App Setting, never in the code.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONWARNINGS=ignore
RG=mk-academy-rg
APP=$(grep ^APP= deploy/.azure-app 2>/dev/null | cut -d= -f2)
[ -n "$APP" ] || { echo "Deploy the site first: bash deploy/azure_deploy.sh"; exit 1; }

read -rp "Admin username: " USERNAME
[ -n "$USERNAME" ] || { echo "Username can't be empty"; exit 1; }
read -rsp "Admin password (at least 10 characters): " PASSWORD; echo
[ ${#PASSWORD} -ge 10 ] || { echo "Password too short"; exit 1; }
read -rsp "Repeat password: " PASSWORD2; echo
[ "$PASSWORD" = "$PASSWORD2" ] || { echo "Passwords don't match"; exit 1; }

az webapp config appsettings set -g $RG -n "$APP" -o none \
  --settings ADMIN_USERNAME="$USERNAME" ADMIN_PASSWORD="$PASSWORD"
echo "✅ Saved. After the restart (~30s) log in at https://$APP.azurewebsites.net/admin/"
