#!/bin/bash
# --- install.sh ---

# 1. Absolute Anchor
if [ -n "${BASH_SOURCE[0]}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
else
    SCRIPT_DIR="$PWD"
fi
cd "$SCRIPT_DIR"

echo ""
echo -e "\e[36m╔══════════════════════════════════════════════════════════════╗\e[0m"
echo -e "\e[36m║            DaSiWa ComfyUI Installer (Linux)                  ║\e[0m"
echo -e "\e[36m╚══════════════════════════════════════════════════════════════╝\e[0m"
echo ""

# 2. Define URLs and Paths
REPO_ZIP_URL="https://github.com/darksidewalker/dasiwa-comfyui-installer/archive/refs/heads/main.zip"
ZIP_FILE="$SCRIPT_DIR/repo.zip"
TEMP_DIR="$SCRIPT_DIR/temp_extract"

# Check if config exists to override the URL
if [ -f "config.json" ]; then
    CONF_URL=$(python3 -c "import json; print(json.load(open('config.json'))['repository']['zip_url'])" 2>/dev/null)
    if [ -n "$CONF_URL" ]; then REPO_ZIP_URL="$CONF_URL"; fi
fi

# 3. Download and Sync
echo "[*] Downloading installer components..."
if ! curl -L -o "$ZIP_FILE" "$REPO_ZIP_URL"; then
    echo -e "\e[31m[-] FATAL: Could not download installer from $REPO_ZIP_URL\e[0m"
    exit 1
fi

rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

echo "[*] Extracting..."
if ! unzip -q -o "$ZIP_FILE" -d "$TEMP_DIR"; then
    echo -e "\e[31m[-] ERROR: Extraction failed. Is the ZIP corrupted?\e[0m"
    exit 1
fi

# GitHub zips nest everything inside a folder like 'repo-main/'
INNER_DIR=$(find "$TEMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)

if [ -n "$INNER_DIR" ]; then
    echo "[*] Syncing files to $SCRIPT_DIR..."
    cp -af "$INNER_DIR"/. "$SCRIPT_DIR/"
    rm -rf "$ZIP_FILE" "$TEMP_DIR"
else
    echo -e "\e[31m[-] ERROR: Extraction layout unexpected.\e[0m"
    exit 1
fi

# 4. UV & Python Environment
if ! command -v uv &> /dev/null; then
    echo "[*] UV not found. Installing UV..."
    if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
        echo -e "\e[31m[-] FATAL: Could not install UV.\e[0m"
        exit 1
    fi
    # Refresh PATH for the current shell
    source "$HOME/.cargo/env" 2>/dev/null || export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
fi

# Read target Python from config (local overrides global if present)
TARGET_VER=$(python3 -c "
import json, os
cfg = json.load(open('config.json'))
if os.path.exists('config.local.json'):
    local = json.load(open('config.local.json'))
    if 'python' in local and 'display_name' in local['python']:
        print(local['python']['display_name']); raise SystemExit
print(cfg['python']['display_name'])
" 2>/dev/null || echo "3.12")

echo "[*] Ensuring Portable Python $TARGET_VER via UV..."
uv python install "$TARGET_VER"
PY_PATH=$(uv python find "$TARGET_VER" | tr -d '\r')

# 5. Hand off to Python
if [ -f "$PY_PATH" ]; then
    echo -e "\e[32m[+] Launching Setup Logic...\e[0m"
    "$PY_PATH" setup_logic.py --branch "master"
    EXIT_CODE=$?
    exit $EXIT_CODE
else
    echo -e "\e[31m[-] ERROR: Could not locate Python via UV.\e[0m"
    exit 1
fi
