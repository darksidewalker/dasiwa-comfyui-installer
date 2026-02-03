#!/bin/bash
echo "==========================================="
echo "    Welcome to the DaSiWa ComfyUI Installer"
echo "==========================================="
echo "ComfyUI Prerequisites Check (Linux)"
# Detect Distribution
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    OS="unknown"
fi

get_install_cmd() {
    case "$OS" in
        ubuntu|debian|pop|mint) echo "apt-get update && apt-get install -y git python3 python3-pip" ;;
        arch|manjaro)           echo "pacman -Syu --noconfirm git python python-pip" ;;
        fedora|rhel|centos)     echo "dnf install -y git python3 python3-pip" ;;
        *)                      echo "manual_install" ;;
    esac
}

check_and_prompt() {
    local cmd=$(get_install_cmd)
    
    if ! command -v git &> /dev/null || ! command -v python3 &> /dev/null; then
        echo "[!] Missing dependencies (Git or Python3)."
        
        if [ "$cmd" = "manual_install" ]; then
            echo "Your distribution ($OS) is not automatically supported."
            echo "Please install 'git' and 'python3' manually."
            exit 1
        fi

        echo "Recommended command: sudo $cmd"
        read -p "Would you like to run this command now with sudo? (y/n): " choice
        if [[ "$choice" =~ ^[Yy]$ ]]; then
            sudo sh -c "$cmd"
        else
            echo "Installation aborted. Please install dependencies manually."
            exit 1
        fi
    fi
}

check_and_prompt

# Download the python wrapper if it doesn't exist
if [ ! -f "install_comfyui.py" ]; then
    echo "[!] Downloading installer wrapper..."
    curl -L -o install_comfyui.py https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install_comfyui.py
fi

echo "[+] Prerequisites met. Launching Python installer..."
python3 install_comfyui.py
