#!/bin/bash
# --- install.sh (Robust Bootstrapper) ---

# 1. Absolute Anchor
# Ensures we don't create "home" folders in ~/Downloads
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

echo -e "\e[32m==========================================="
echo -e "    DaSiWa ComfyUI Installer (Linux)"
echo -e "===========================================\e[0m"

# 2. Define URLs and Paths
# We hardcode the fallback URL since config.json might not exist on first run
REPO_ZIP_URL="https://github.com/darksidewalker/dasiwa-comfyui-installer/archive/refs/heads/main.zip"
ZIP_FILE="$SCRIPT_DIR/repo.zip"
TEMP_DIR="$SCRIPT_DIR/temp_extract"

# Check if config exists to override the URL
if [ -f "config.json" ]; then
    # Try to extract the zip_url using a simple python one-liner (more robust than grep)
    CONF_URL=$(python3 -c "import json; print(json.load(open('config.json'))['repository']['zip_url'])" 2>/dev/null)
    if [ -n "$CONF_URL" ]; then REPO_ZIP_URL="$CONF_URL"; fi
fi

# 3. Download and Sync
echo "[*] Downloading installer components..."
curl -L -o "$ZIP_FILE" "$REPO_ZIP_URL"

# Clean up previous failed attempts
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

echo "[*] Extracting..."
unzip -q -o "$ZIP_FILE" -d "$TEMP_DIR"

# GitHub zips nest everything inside a folder like 'repo-main/'
INNER_DIR=$(find "$TEMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)

if [ -n "$INNER_DIR" ]; then
    echo "[*] Syncing files to $SCRIPT_DIR..."
    # Copying content of INNER_DIR to SCRIPT_DIR
    # Using 'cp' with a dot slash avoids the "copying into itself" error
    cp -af "$INNER_DIR"/. "$SCRIPT_DIR/"
    
    # Cleanup download artifacts
    rm -rf "$ZIP_FILE" "$TEMP_DIR"
else
    echo -e "\e[31m[-] ERROR: Extraction failed. Is the ZIP corrupted?\e[0m"
    exit 1
fi

# 4. UV & Python Environment
if ! command -v uv &> /dev/null; then
    echo "[*] UV not found. Installing UV..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Refresh path for the current shell session
    source "$HOME/.cargo/env" 2>/dev/null || export PATH="$HOME/.cargo/bin:$PATH"
fi

# Now that sync is done, config.json is guaranteed to exist
TARGET_VER=$(python3 -c "import json; print(json.load(open('config.json'))['python']['display_name'])" 2>/dev/null || echo "3.12")

echo "[*] Ensuring Portable Python $TARGET_VER via UV..."
uv python install "$TARGET_VER"
PY_PATH=$(uv python find "$TARGET_VER" | tr -d '\r')

# 5. Hand off to Python
if [ -f "$PY_PATH" ]; then
    echo -e "\e[32m[+] Launching Setup Logic...\e[0m"
    "$PY_PATH" setup_logic.py --branch "main"
else
    echo -e "\e[31m[-] ERROR: Could not locate Python via UV.\e[0m"
    exit 1
fi