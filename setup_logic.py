VERSION = 1.4
import subprocess
import os
import sys
import platform
import urllib.request
from pathlib import Path

# --- KONFIGURATION ---
NODES_LIST_URL = "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/custom_nodes.txt"
NODES_LIST_FILE = "custom_nodes.txt"

# --- CORE UTILS ---
def run_cmd(cmd, env=None, shell=False):
    subprocess.run(cmd, check=True, env=env, shell=shell)

def get_venv_env():
    venv_path = Path.cwd() / "venv"
    full_env = os.environ.copy()
    full_env["VIRTUAL_ENV"] = str(venv_path)
    bin_dir = "Scripts" if platform.system() == "Windows" else "bin"
    full_env["PATH"] = str(venv_path / bin_dir) + os.pathsep + full_env["PATH"]
    return full_env, bin_dir

# --- MODULE (Einfach erweiterbar) ---

def task_install_ffmpeg():
    """Prüft und installiert FFmpeg (Beispiel für Modularität)."""
    print("\n--- Modul: FFmpeg Check ---")
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        print("[+] FFmpeg ist bereits installiert.")
    except:
        print("[!] FFmpeg fehlt. Installation wird empfohlen...")
        if platform.system() == "Windows":
            print("Tipp: Nutze 'winget install ffmpeg'")
        else:
            print("Tipp: Nutze 'sudo apt install ffmpeg' oder 'pacman -S ffmpeg'")

def task_setup_uv():
    print("\n--- Modul: UV Setup ---")
    try:
        subprocess.run(["uv", "--version"], check=True, capture_output=True)
    except:
        if platform.system() == "Windows":
            run_cmd("powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\"", shell=True)
        else:
            run_cmd("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
        os.environ["PATH"] += os.pathsep + os.path.expanduser("~/.cargo/bin")

def task_install_torch(env):
    print("\n--- Modul: PyTorch (Nvidia) ---")
    run_cmd(["uv", "pip", "install", "torch", "torchvision", "torchaudio", "--extra-index-url", "https://download.pytorch.org/whl/cu121"], env=env)

def task_custom_nodes(env):
    print("\n--- Modul: Custom Nodes ---")
    os.makedirs("custom_nodes", exist_ok=True)
    try:
        urllib.request.urlretrieve(NODES_LIST_URL, NODES_LIST_FILE)
        with open(NODES_LIST_FILE, "r") as f:
            repos = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        
        for repo in repos:
            repo_name = repo.split("/")[-1].replace(".git", "")
            node_dir = Path("custom_nodes") / repo_name
            if not node_dir.exists():
                run_cmd(["git", "clone", repo, str(node_dir)])
            
            req_file = node_dir / "requirements.txt"
            if req_file.exists():
                run_cmd(["uv", "pip", "install", "-r", str(req_file)], env=env)
    except Exception as e:
        print(f"Fehler bei Custom Nodes: {e}")

# --- HAUPTABLAUF ---

def main():
    # 1. Init & Pfade
    default_path = Path.cwd().resolve()
    user_input = input(f"Installationspfad (Enter für {default_path}): ").strip()
    install_base = Path(user_input) if user_input else default_path
    comfy_path = install_base / "ComfyUI"

    if comfy_path.exists():
        print("[!] ComfyUI existiert bereits."); sys.exit(1)

    # 2. Infrastruktur
    os.makedirs(install_base, exist_ok=True)
    os.chdir(install_base)
    
    # 3. Task-Sequenz
    run_cmd(["git", "clone", "https://github.com/comfyanonymous/ComfyUI"])
    os.chdir("ComfyUI")
    
    task_setup_uv()
    run_cmd(["uv", "venv", "venv", "--python", "3.12"])
    
    # Venv-Umgebung laden
    venv_env, bin_name = get_venv_env()
    
    # Hier kannst du neue Tasks einfach einfügen:
    task_install_ffmpeg() 
    task_install_torch(venv_env)
    
    print("\n--- Modul: Core Requirements ---")
    run_cmd(["uv", "pip", "install", "-r", "requirements.txt"], env=venv_env)
    
    task_custom_nodes(venv_env)
    
    # 5. Abschluss
    python_exe = os.path.join("venv", bin_name, "python")
    # Launcher-Logik hier... (abgekürzt)
    print("\n=== SETUP FERTIG ===")

if __name__ == "__main__":
    main()
