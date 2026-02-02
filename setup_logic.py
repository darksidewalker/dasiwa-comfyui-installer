VERSION = 1.6
import subprocess
import os
import sys
import platform
import urllib.request
from pathlib import Path

# --- ZENTRALE KONFIGURATION ---
CUDA_VERSION = "cu121"  # Zentral steuerbar: cu121, cu124, cu130 etc.
NODES_LIST_URL = "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/custom_nodes.txt"
NODES_LIST_FILE = "custom_nodes.txt"

# --- CORE UTILS ---
def run_cmd(cmd, env=None, shell=False):
    subprocess.run(cmd, check=True, env=env, shell=shell)

def get_venv_env():
    venv_path = Path.cwd() / "venv"
    full_env = os.environ.copy()
    full_env["VIRTUAL_ENV"] = str(venv_path)
    
    if platform.system() == "Windows":
        bin_dir = "Scripts"
    else:
        bin_dir = "bin"
        
    full_env["PATH"] = str(venv_path / bin_dir) + os.pathsep + full_env["PATH"]
    return full_env, bin_dir

# --- MODULE ---

def task_create_launchers(bin_dir):
    """Erstellt Start-Dateien für Windows und Linux."""
    print("\n--- Modul: Launcher Erstellung ---")
    
    # Pfad zum Python in der Venv
    if platform.system() == "Windows":
        python_path = f"venv\\{bin_dir}\\python.exe"
        launcher_name = "run_comfyui.bat"
        content = f"@echo off\n\"{python_path}\" main.py\npause"
    else:
        python_path = f"venv/{bin_dir}/python"
        launcher_name = "run_comfyui.sh"
        content = f"#!/bin/bash\n./{python_path} main.py"

    launcher_file = Path(launcher_name)
    launcher_file.write_text(content)
    
    # Ausführbar machen (Linux/macOS)
    if platform.system() != "Windows":
        os.chmod(launcher_file, 0o755)
    
    print(f"[+] Launcher erstellt: {launcher_name}")

def task_install_torch(env):
    print(f"\n--- Modul: PyTorch ({CUDA_VERSION}) ---")
    extra_index = f"https://download.pytorch.org/whl/{CUDA_VERSION}"
    run_cmd([
        "uv", "pip", "install", 
        "torch", "torchvision", "torchaudio", 
        "--extra-index-url", extra_index
    ], env=env)

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
            print(f">> Syncing: {repo_name}")
            if not node_dir.exists():
                run_cmd(["git", "clone", repo, str(node_dir)])
            
            req_file = node_dir / "requirements.txt"
            if req_file.exists():
                run_cmd(["uv", "pip", "install", "-r", str(req_file)], env=env)
    except Exception as e:
        print(f"Hinweis bei Custom Nodes: {e}")

# --- HAUPTABLAUF ---

def main():
    # 1. Init & Pfad-Abfrage
    default_path = Path.cwd().resolve()
    print(f"Standard-Installationspfad: {default_path}")
    user_input = input(f"Installationspfad (Enter für {default_path}): ").strip()
    install_base = Path(user_input) if user_input else default_path
    comfy_path = install_base / "ComfyUI"

    if comfy_path.exists():
        print(f"[!] ABBRUCH: {comfy_path} existiert bereits.")
        sys.exit(1)

    # 2. Ordner-Struktur vorbereiten
    os.makedirs(install_base, exist_ok=True)
    os.chdir(install_base)
    
    # 3. Installation Kern
    print(f"\n--- Klone ComfyUI nach {comfy_path} ---")
    run_cmd(["git", "clone", "https://github.com/comfyanonymous/ComfyUI"])
    os.chdir("ComfyUI")
    
    # UV & Venv Setup
    print("\n--- Infrastruktur Setup ---")
    try:
        run_cmd(["uv", "--version"])
    except:
        if platform.system() == "Windows":
            run_cmd("powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\"", shell=True)
        else:
            run_cmd("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
        os.environ["PATH"] += os.pathsep + os.path.expanduser("~/.cargo/bin")

    run_cmd(["uv", "venv", "venv", "--python", "3.12"])
    
    # Umgebung für uv laden
    venv_env, bin_name = get_venv_env()
    
    # Tasks ausführen
    task_install_torch(venv_env)
    
    print("\n--- Modul: Core Requirements ---")
    run_cmd(["uv", "pip", "install", "-r", "requirements.txt"], env=venv_env)
    
    task_custom_nodes(venv_env)
    
    # Launcher erstellen
    task_create_launchers(bin_name)
    
    print("\n" + "="*40)
    print("INSTALLATION ERFOLGREICH!")
    print(f"ComfyUI wurde in {os.getcwd()} installiert.")
    print("Nutze die 'run_comfyui' Datei zum Starten.")
    print("="*40)

if __name__ == "__main__":
    main()
