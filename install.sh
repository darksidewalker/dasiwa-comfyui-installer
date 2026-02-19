#!/bin/bash
# DaSiWa ComfyUI - Linux Bootstrapper

# 1. Move to script directory
cd "$(dirname "$0")"

echo "==========================================="
echo "    DaSiWa ComfyUI Installer (Linux)"
echo "==========================================="

# 2. Dependency Check (Git)
if ! command -v git &>/dev/null; then
    echo "[!] Error: Git is not installed. Please install it (sudo apt install git)."
    exit 1
fi

# 3. Sync Repository
REPO_URL="https://github.com/darksidewalker/dasiwa-comfyui-installer.git"
if [ ! -d ".git" ]; then
    echo "[INFO] Cloning installer repository..."
    git clone -b main "$REPO_URL" .
else
    echo "[INFO] Updating installer..."
    git pull origin main
fi

# 4. Launch Logic
if command -v python3 &>/dev/null; then
    python3 setup_logic.py
else
    echo "[!] Error: Python3 not found."
    exit 1
fi
