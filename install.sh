#!/bin/bash
# DaSiWa ComfyUI - Linux Bootstrapper
cd "$(dirname "$0")"

echo "==========================================="
echo "    DaSiWa ComfyUI Installer (Linux)"
echo "==========================================="

REPO_URL="https://github.com/darksidewalker/dasiwa-comfyui-installer.git"

# Check if we already have the code
if [ ! -d ".git" ]; then
    echo "[INFO] Syncing installer components..."
    git init > /dev/null
    git remote add origin "$REPO_URL"
    git fetch > /dev/null
    git checkout -f main > /dev/null
else
    echo "[INFO] Updating installer..."
    git pull origin main > /dev/null
fi

# Launch the logic
if command -v python3 &>/dev/null; then
    python3 setup_logic.py
else
    echo "[!] Error: Python3 not found."
    exit 1
fi
