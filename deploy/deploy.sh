#!/usr/bin/env bash
# Push code (and current data) from your Mac to the server, then restart the app.
# Usage:  bash deploy/deploy.sh <SERVER_IP> [path/to/ssh-key]
set -euo pipefail
IP="${1:?Usage: bash deploy/deploy.sh <SERVER_IP> [ssh-key]}"
KEY="${2:-$HOME/.ssh/oracle_key}"
SSH_USER="${SSH_USER:-ubuntu}"   # Azure VM: SSH_USER=azureuser
cd "$(dirname "$0")/.."
rsync -avz --delete -e "ssh -i $KEY" \
  --exclude '.venv' --exclude '__pycache__' --exclude '.DS_Store' --exclude '.env' --exclude 'data/db.sqlite3*' --exclude 'staticfiles' \
  ./ "$SSH_USER@$IP:~/mk-academy/"
ssh -i "$KEY" "$SSH_USER@$IP" 'cd ~/mk-academy && if systemctl list-unit-files | grep -q mk-academy; then .venv/bin/pip install -q -r requirements.txt && set -a && . ./.env && set +a && .venv/bin/python manage.py migrate --noinput && .venv/bin/python manage.py collectstatic --noinput -v0 && sudo systemctl restart mk-academy && echo "✅ restarted"; else echo "First time: run  cd ~/mk-academy && bash deploy/setup_server.sh"; fi'
