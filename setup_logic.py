import subprocess
import os
import sys
import platform
import urllib.request
from pathlib import Path

# Konfiguration
NODES_LIST_URL = "https://github.com/darksidewalker/dasiwa-comfyui-installer/custom_nodes.txt"
NODES_LIST_FILE = "custom_nodes.txt"

def run_cmd(cmd, shell=False):
    subprocess.run(cmd, shell=shell, check=True)

def main():
    print("=== ComfyUI Installation Setup ===")
    
    # Pfad-Auswahl
    default_path = os.getcwd()
    print(f"Standard-Installationspfad: {default_path}")
    user_input = input("Gib den gewünschten Pfad ein (Enter für Standard): ").strip()
    
    install_base = Path(user_input) if user_input else Path(default_path)
    comfy_path = install_base / "ComfyUI"

    # Check ob ComfyUI bereits existiert
    if comfy_path.exists():
        print(f"\n[!] ABBRUCH: Der Ordner '{comfy_path}' existiert bereits.")
        print("Bitte lösche den Ordner oder wähle einen anderen Pfad.")
        sys.exit(1)

    # Verzeichnis erstellen falls nötig
    if not install_base.exists():
        os.makedirs(install_base)
    
    os.chdir(install_base)

    # 1. ComfyUI clonen
    print(f"\n--- Klone ComfyUI nach {comfy_path} ---")
    run_cmd(["git", "clone", "https://github.com/comfyanonymous/ComfyUI"])
    os.chdir("ComfyUI")

    # 2. UV installieren
    print("\n--- Prüfe uv Installation ---")
    try:
        run_cmd(["uv", "--version"])
    except:
        print("Installiere uv...")
        if platform.system() == "Windows":
            run_cmd("powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\"", shell=True)
        else:
            run_cmd("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
        os.environ["PATH"] += os.pathsep + os.path.expanduser("~/.cargo/bin")

    # 3. & 4. Venv mit Python 3.12 erstellen
    print("\n--- Erstelle venv mit Python 3.12 ---")
    run_cmd(["uv", "venv", "venv", "--python", "3.12"])
    
    # Pfad-Konfiguration für venv
    suffix = "\\" if platform.system() == "Windows" else "/"
    python_exe = f"venv{suffix}Scripts{suffix}python.exe" if platform.system() == "Windows" else "venv/bin/python"

    # 5. GPU Check (Nvidia check via nvidia-smi)
    print("\n--- Prüfe GPU Hardware ---")
    is_nvidia = False
    try:
        if subprocess.run(["nvidia-smi"], capture_output=True).returncode == 0:
            is_nvidia = True
    except: pass

    if is_nvidia:
        print("Nvidia GPU erkannt. Installiere Torch...")
        run_cmd(["uv", "pip", "install", "torch", "torchvision", "torchaudio", "--extra-index-url", "https://download.pytorch.org/whl/cu121"])
    else:
        print("Abbruch: Keine Nvidia GPU erkannt (AMD/Intel Support nicht konfiguriert).")
        sys.exit(1)

    # 6. Requirements
    print("\n--- Installiere ComfyUI Haupt-Requirements ---")
    run_cmd(["uv", "pip", "install", "-r", "requirements.txt"])

    # 7. Custom Nodes aus externer Liste
    print("\n--- Setup Custom Nodes ---")
    try:
        urllib.request.urlretrieve(NODES_LIST_URL, NODES_LIST_FILE)
        with open(NODES_LIST_FILE, "r") as f:
            repos = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except Exception as e:
        print(f"Warnung: Konnte Custom Nodes Liste nicht laden ({e})")
        repos = []

    if not os.path.exists("custom_nodes"):
        os.makedirs("custom_nodes")

    for repo in repos:
        repo_name = repo.split("/")[-1].replace(".git", "")
        node_dir = os.path.join("custom_nodes", repo_name)
        
        print(f">> Installiere Node: {repo_name}")
        if not os.path.exists(node_dir):
            run_cmd(["git", "clone", repo, node_dir])
        
        node_req = os.path.join(node_dir, "requirements.txt")
        if os.path.exists(node_req):
            run_cmd(["uv", "pip", "install", "-r", node_req])

    print("\n" + "="*40)
    print("INSTALLATION ERFOLGREICH!")
    print(f"Pfad: {comfy_path}")
    print(f"Startbefehl: {python_exe} main.py")
    print("="*40)

if __name__ == "__main__":
    main()
