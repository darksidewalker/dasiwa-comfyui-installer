#!/bin/bash
# --- install.sh ---
cd "$(dirname "$0")"

echo -e "\e[32m==========================================="
echo -e "    DaSiWa ComfyUI Installer (Linux)"
echo -e "===========================================\e[0m"

# 1. Download and Extract (Testing Branch)
REPO_ZIP="https://github.com/darksidewalker/dasiwa-comfyui-installer/archive/refs/heads/main.zip"
curl -L -o repo.zip "$REPO_ZIP"
unzip -q -o repo.zip -d temp_extract
INNER_DIR=$(find temp_extract -mindepth 1 -maxdepth 1 -type d | head -n 1)
cp -af "$INNER_DIR"/. .
rm -rf repo.zip temp_extract

# 2. Ensure UV is available
if ! command -v uv &> /dev/null; then
    echo "[*] Installing UV (Standalone)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.cargo/env
fi

# 3. Read Python version from config.json
TARGET_VER=$(grep -oP '(?<="display_name": ")[^"]*' config.json || echo "3.12")

# 4. Fetch Portable Python via UV
echo "[*] Ensuring Portable Python $TARGET_VER via UV..."
uv python install "$TARGET_VER"
PY_PATH=$(uv python find "$TARGET_VER" | tr -d '\r')

# 5. Launch Setup
if [ -f "$PY_PATH" ]; then
    echo -e "\e[32m[+] Launching Setup Logic...\e[0m"
    "$PY_PATH" setup_logic.py --branch "testing"
else
    echo -e "\e[31m[-] ERROR: UV could not find Python $TARGET_VER.\e[0m"
    exit 1
fi