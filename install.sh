#!/bin/bash
# DaSiWa ComfyUI - Linux Bootstrapper
# We don't use 'set -e' here so we can catch the error ourselves

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
curl -L -s -o "$ZIP_FILE" "$REPO_ZIP"
mkdir -p "$TEMP_DIR"
unzip -q -o "$ZIP_FILE" -d "$TEMP_DIR"

# 3. Move and Overwrite
INNER_DIR=$(find "$TEMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)

if [ -z "$INNER_DIR" ]; then
    echo "[!] Error: Extraction failed. Is 'unzip' installed?"
    exit 1
fi

echo "[*] Syncing files..."
cp -af "$INNER_DIR"/. .

# 4. Cleanup
rm "$ZIP_FILE"
rm -rf "$TEMP_DIR"

# 5. The "Hand-off" to Python
echo "[*] Launching setup_logic.py..."

# Check which python command works
if command -v python3 &>/dev/null; then
    PY_CMD="python3"
elif command -v python &>/dev/null; then
    PY_CMD="python"
else
    echo "[!] Error: No Python found. Please install python3."
    exit 1
fi

# Run it!
$PY_CMD "setup_logic.py" --branch "testing"

# If we get here, Python failed to start
if [ $? -ne 0 ]; then
    echo "[!] Python exited with an error code."
    exit 1
fi
