#!/usr/bin/env bash
# Push code (and current data) from your Mac to the server, then restart the app.
# Usage:  bash deploy/deploy.sh <SERVER_IP> [path/to/ssh-key]
set -euo pipefail
IP="${1:?Usage: bash deploy/deploy.sh <SERVER_IP> [ssh-key]}"
KEY="${2:-$HOME/.ssh/oracle_key}"
SSH_USER="${SSH_USER:-ubuntu}"   # Azure VM: SSH_USER=azureuser
cd "$(dirname "$0")/.."
rsync -avz --delete -e "ssh -i $KEY" \
  --exclude '.venv' --exclude '__pycache__' --exclude '.DS_Store' \
  ./ "$SSH_USER@$IP:~/mk-academy/"
ssh -i "$KEY" "$SSH_USER@$IP" 'if systemctl list-unit-files | grep -q mk-academy; then sudo systemctl restart mk-academy && echo "✅ restarted"; else echo "First time: run  cd ~/mk-academy && bash deploy/setup_server.sh"; fi'
