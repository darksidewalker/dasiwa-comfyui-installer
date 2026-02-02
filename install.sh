#!/bin/bash

echo "==========================================="
echo "    ComfyUI Prerequisites Check (Linux)"
echo "==========================================="

# Distribution erkennen
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
        echo "[!] Fehlende Pakete erkannt (Git oder Python3)."
        
        if [ "$cmd" = "manual_install" ]; then
            echo "Deine Distribution ($OS) wird nicht automatisch unterstuetzt."
            echo "Bitte installiere 'git' und 'python3' manuell."
            exit 1
        fi

        echo "Empfohlener Befehl: sudo $cmd"
        read -p "Soll ich diesen Befehl jetzt mit sudo ausfuehren? (j/n): " choice
        if [[ "$choice" =~ ^[Jj]$ ]]; then
            sudo sh -c "$cmd"
        else
            echo "Installation abgebrochen. Bitte installiere die Pakete manuell."
            exit 1
        fi
    fi
}

# Ablauf
check_and_prompt

# Starte Installer
echo "[+] Voraussetzungen erfuellt. Starte Python-Installer..."
python3 install_comfyui.py
