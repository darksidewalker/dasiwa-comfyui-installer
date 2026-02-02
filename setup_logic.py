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
        os.chmod(launcher_path, 0o755)
    print(f"[+] Launcher erstellt: {launcher_path}")

def main():
    print("=== ComfyUI Installation Setup ===")
    
    default_path = Path.cwd().resolve()
    print(f"Standard-Installationspfad: {default_path}")
    user_input = input(f"Gib den gewünschten Pfad ein (Enter für {default_path}): ").strip()
    
    install_base = Path(user_input) if user_input else default_path
    comfy_path = install_base / "ComfyUI"

    if comfy_path.exists():
        print(f"\n[!] ABBRUCH: Der Ordner '{comfy_path}' existiert bereits.")
        sys.exit(1)

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

    # 3. & 4. Venv erstellen und PATH-Logik (HIER WAR DER FEHLER)
    print("\n--- Erstelle venv mit Python 3.12 ---")
    run_cmd(["uv", "venv", "venv", "--python", "3.12"])
    
    venv_path = Path.cwd() / "venv"
    full_env = os.environ.copy()
    full_env["VIRTUAL_ENV"] = str(venv_path)
    
    # Korrekte Zuweisung des bin_dir ohne Syntax-Fehler
    if platform.system() == "Windows":
        bin_dir = "Scripts"
    else:
        bin_dir = "bin"
        
    full_env["PATH"] = str(venv_path / bin_dir) + os.pathsep + full_env["PATH"]

    # 5. GPU Check
    print("\n--- Prüfe GPU Hardware ---")
    is_nvidia = False
    try:
        if subprocess.run(["nvidia-smi"], capture_output=True).returncode == 0:
            is_nvidia = True
    except: pass

    if is_nvidia:
        print("Nvidia GPU erkannt. Installiere Torch...")
        run_cmd(["uv", "pip", "install", "torch", "torchvision", "torchaudio", "--extra-index-url", "https://download.pytorch.org/whl/cu121"], env=full_env)
    else:
        print("Abbruch: Keine Nvidia GPU erkannt.")
        sys.exit(1)

    # 6. Requirements
    print("\n--- Installiere ComfyUI Haupt-Requirements ---")
    run_cmd(["uv", "pip", "install", "-r", "requirements.txt"], env=full_env)

    # 7. Custom Nodes
    print("\n--- Setup Custom Nodes ---")
    os.makedirs("custom_nodes", exist_ok=True)
    try:
        urllib.request.urlretrieve(NODES_LIST_URL, NODES_LIST_FILE)
        with open(NODES_LIST_FILE, "r") as f:
            repos = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except Exception as e:
        print(f"Hinweis: Liste konnte nicht geladen werden ({e})")
        repos = []

    for repo in repos:
        repo_name = repo.split("/")[-1].replace(".git", "")
        node_dir = Path("custom_nodes") / repo_name
        print(f">> Node: {repo_name}")
        if not node_dir.exists():
            run_cmd(["git", "clone", repo, str(node_dir)])
        
        node_req = node_dir / "requirements.txt"
        if node_req.exists():
            run_cmd(["uv", "pip", "install", "-r", str(node_req)], env=full_env)

    # Launcher erstellen
    python_exe = os.path.join("venv", bin_dir, "python.exe" if platform.system() == "Windows" else "python")
    create_launcher(python_exe)

    print("\n" + "="*40)
    print("INSTALLATION ERFOLGREICH!")
    print(f"Verzeichnis: {comfy_path}")
    print(f"Startbefehl: ./{python_exe} main.py")
    print("="*40)

if __name__ == "__main__":
    main()
