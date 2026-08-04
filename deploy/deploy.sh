#!/usr/bin/env bash
set -euo pipefail

PI_HOST="${PI_HOST:-pi@raspberrypi}"
TARGET_DIR="/home/eduard/boardgame-bot"

echo "Deploying to $PI_HOST:$TARGET_DIR ..."

# Sync source files (excluding venv, data, git, etc.)
rsync -avz \
    --exclude '.venv' \
    --exclude 'data' \
    --exclude '.env' \
    --exclude '__pycache__' \
    --exclude '.git' \
    --exclude '*.log*' \
    --exclude 'backups' \
    ./ "$PI_HOST:$TARGET_DIR/"

# Install deps and restart service
ssh "$PI_HOST" << 'ENDSSH'
    cd /home/eduard/boardgame-bot
    uv sync
    sudo systemctl restart boardgame-bot
    echo "---"
    sudo systemctl status boardgame-bot --no-pager
ENDSSH

echo "Deploy complete."
