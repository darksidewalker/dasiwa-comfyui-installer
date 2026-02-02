VERSION = 1.3
import subprocess
import os
import sys
import platform
import urllib.request
from pathlib import Path

# Konfiguration
NODES_LIST_URL = "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/custom_nodes.txt"
NODES_LIST_FILE = "custom_nodes.txt"

def run_cmd(cmd, env=None):
    subprocess.run(cmd, check=True, env=env)

def create_launcher(python_exe):
    """Erstellt betriebssystemspezifische Start-Dateien."""
    if platform.system() == "Windows":
        launcher_path = Path("run_comfyui.bat")
        content = f"@echo off\n\"{python_exe}\" main.py\npause"
    else:
        launcher_path = Path("run_comfyui.sh")
        content = f"#!/bin/bash\n./{python_exe} main.py"
    
    launcher_path.write_text(content)
    
    if platform.system() != "Windows":
        os.chmod(launcher_path, 0o755) # Ausführbar machen unter Linux
    
    print(f"[+] Launcher erstellt: {launcher_path}")

def main():
    print("=== ComfyUI Installation Setup ===")
    
    # Pfad-Auswahl
    default_path = Path.cwd().resolve()
    print(f"Standard-Installationspfad: {default_path}")
    user_input = input(f"Gib den gewünschten Pfad ein (Enter für {default_path}): ").strip()
    
    install_base = Path(user_input) if user_input else default_path
    comfy_path = install_base / "ComfyUI"

    if comfy_path.exists():
        print(f"\n[!] ABBRUCH: Der Ordner '{comfy_path}' existiert bereits.")
        sys.exit(1)

    if not install_base.exists():
        os.makedirs(install_base, exist_ok=True)
    
    os.chdir(install_base)

    # 1. ComfyUI clonen
    print(f"\n--- Klone ComfyUI nach {comfy_path} ---")
    run_cmd(["git", "clone", "https://github.com/comfyanonymous/ComfyUI"])
    os.chdir("ComfyUI")

    # 2. UV installieren / prüfen
    print("\n--- Prüfe uv Installation ---")
    try:
        subprocess.run(["uv", "--version"], check=True, capture_output=True)
    except:
        print("Installiere uv...")
        if platform.system() == "Windows":
            subprocess.run("powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\"", shell=True, check=True)
        else:
            subprocess.run("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True, check=True)
        os.environ["PATH"] += os.pathsep + os.path.expanduser("~/.cargo/bin")

    # 3. & 4. Venv mit Python 3.12 erstellen und Umgebung simulieren
    print("\n--- Erstelle venv mit Python 3.12 ---")
    run_cmd(["uv", "venv", "venv", "--python", "3.12"])
    
    venv_path = Path.cwd() / "venv"
    full_env = os.environ.copy()
    full_env["VIRTUAL_ENV"] = str(venv_path)
    bin_dir = "Scripts" if
