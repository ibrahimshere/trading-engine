#!/usr/bin/env bash
# Deploy the execution service to the DigitalOcean droplet.
#
# Usage (from repo root):
#   bash execution/deploy/deploy.sh
#
# What it does:
#   1. rsync execution/ source to /opt/orb-trader/ on the droplet
#   2. Restart the orb-trader systemd service
#
# Prerequisites:
#   - SSH access to root@143.110.148.234 (set up SSH keys)
#   - Initial setup already done (setup.sh + install-service.sh)
set -euo pipefail

DROPLET="root@143.110.148.234"
REMOTE_DIR="/opt/orb-trader"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Deploying from $LOCAL_DIR ==="

echo "--- Syncing source files ---"
rsync -avz --delete \
    --exclude '.venv/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.env' \
    --exclude 'logs/' \
    --exclude 'config/checkpoint.json' \
    --exclude 'config/trade_history.json' \
    --exclude 'config/exec_configs.json' \
    --exclude 'config/overrides.json' \
    --exclude 'config/adaptive_risk_state.json' \
    "$LOCAL_DIR/" "$DROPLET:$REMOTE_DIR/"

echo "--- Installing dependencies ---"
ssh "$DROPLET" "cd $REMOTE_DIR && uv sync"

echo "--- Ensuring MAIN_DB_URL exists in remote .env ---"
ssh "$DROPLET" "if [ -f $REMOTE_DIR/.env ] && ! grep -q '^MAIN_DB_URL=' $REMOTE_DIR/.env; then printf '\nMAIN_DB_URL=http://127.0.0.1:8100\n' >> $REMOTE_DIR/.env; fi"
ssh "$DROPLET" "if [ -f $REMOTE_DIR/.env ]; then if grep -q '^EXEC_API_HOST=' $REMOTE_DIR/.env; then sed -i 's/^EXEC_API_HOST=.*/EXEC_API_HOST=127.0.0.1/' $REMOTE_DIR/.env; else printf '\nEXEC_API_HOST=127.0.0.1\n' >> $REMOTE_DIR/.env; fi; fi"

echo "--- Restarting service ---"
ssh "$DROPLET" "systemctl restart orb-trader"

echo "--- Verifying ---"
sleep 3
ssh "$DROPLET" "systemctl is-active orb-trader && ss -tlnp | grep 8000 || echo 'WARNING: port 8000 not yet listening (may take a few seconds for ATR warmup)'"

echo "=== Deploy complete ==="
