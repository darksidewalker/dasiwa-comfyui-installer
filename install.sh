#!/bin/bash
# DaSiWa ComfyUI - Linux Bootstrapper
cd "$(dirname "$0")"

echo "==========================================="
echo "    DaSiWa ComfyUI Installer (Linux)"
echo "==========================================="

# 1. Configuration
REPO_ZIP="https://github.com/darksidewalker/dasiwa-comfyui-installer/archive/refs/heads/main.zip"
ZIP_FILE="repo.zip"
TEMP_DIR="temp_extract"

# 2. Download and Extract
echo "[*] Downloading latest components..."
curl -L -o "$ZIP_FILE" "$REPO_ZIP"

if [ -d "$TEMP_DIR" ]; then rm -rf "$TEMP_DIR"; fi
mkdir -p "$TEMP_DIR"
unzip -q "$ZIP_FILE" -d "$TEMP_DIR"

# 3. Move and Overwrite (The Linux way)
# GitHub zips have a nested folder, we find it and move its contents here
INNER_DIR=$(find "$TEMP_DIR" -maxdepth 1 -type d | grep "installer-main" | head -n 1)
cp -rf "$INNER_DIR"/* .

# 4. Cleanup
rm "$ZIP_FILE"
rm -rf "$TEMP_DIR"

# 5. Smart Config Reading
# We try to get the display version from config.json using a simple python one-liner
if [ -f "config.json" ]; then
    PY_VERSION=$(python3 -c "import json; print(json.load(open('config.json'))['python']['display_name'])" 2>/dev/null)
else
    PY_VERSION="3.12"
fi

echo "[+] Target Python: $PY_VERSION"

# 6. Launch
if command -v python3 &>/dev/null; then
    python3 setup_logic.py
else
    echo "[!] Error: Python3 not found. Please install it (e.g., sudo apt install python3)"
    exit 1
fi