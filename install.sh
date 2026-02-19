#!/bin/bash
# DaSiWa ComfyUI - Linux Bootstrapper

# 1. Ensure we are in the script's directory
cd "$(dirname "$0")"

echo "==========================================="
echo "    DaSiWa ComfyUI Installer (Linux)"
echo "==========================================="

# 2. Update Python filename and Download
# We use setup_logic.py to match your current GitHub structure
if [ ! -f "setup_logic.py" ]; then
    echo "[INFO] Downloading installer engine..."
    curl -L -o setup_logic.py https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/setup_logic.py
fi

# 3. Launch the Python logic
# We use python3 specifically as most Linux distros alias it this way
if command -v python3 &>/dev/null; then
    python3 setup_logic.py
elif command -v python &>/dev/null; then
    python setup_logic.py
else
    echo "[!] Error: Python not found. Please install python3 (e.g., sudo apt install python3)"
    exit 1
fi
