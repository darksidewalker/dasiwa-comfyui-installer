VERSION = 1.7
import subprocess
import os
import sys
import platform
import urllib.request
from pathlib import Path

# --- CENTRAL CONFIGURATION ---
CUDA_VERSION = "cu130"  # Options: cu118, cu121, cu124, cu130 etc.
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

# --- MODULES ---

def task_create_launchers(bin_dir):
    """Creates startup scripts for Windows and Linux."""
    print("\n--- Module: Creating Launchers ---")
    
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
    
    if platform.system() != "Windows":
        os.chmod(launcher_file, 0o755)
    
    print(f"[+] Launcher created: {launcher_name}")

def task_install_torch(env):
    print(f"\n--- Module: PyTorch ({CUDA_VERSION}) ---")
    extra_index = f"https://download.pytorch.org/whl/{CUDA_VERSION}"
    run_cmd([
        "uv", "pip", "install", 
        "torch", "torchvision", "torchaudio", 
        "--extra-index-url", extra_index
    ], env=env)

def task_custom_nodes(env):
    print("\n--- Module: Custom Nodes ---")
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
        
        if os.path.exists(NODES_LIST_FILE):
            os.remove(NODES_LIST_FILE)
            
    except Exception as e:
        print(f"[*] Note regarding Custom Nodes: {e}")

# --- MAIN PROCESS ---

def main():
    print("=== DaSiWa ComfyUI Installation Logic ===")
    
    # 1. Directory Setup
    default_path = Path.cwd().resolve()
    print(f"Default installation path: {default_path}")
    user_input = input(f"Enter target path (Leave empty for {default_path}): ").strip()
    install_base = Path(user_input) if user_input else default_path
    comfy_path = install_base / "ComfyUI"

    if comfy_path.exists():
        print(f"[!] ABORT: {comfy_path} already exists.")
        sys.exit(1)

    os.makedirs(install_base, exist_ok=True)
    os.chdir(install_base)
    
    # 2. Clone Core
    print(f"\n--- Cloning ComfyUI to {comfy_path} ---")
    run_cmd(["git", "clone", "https://github.com/comfyanonymous/ComfyUI"])
    os.chdir("ComfyUI")
    
    # 3. Infrastructure (UV & Venv)
    print("\n--- Infrastructure Setup ---")
    try:
        subprocess.run(["uv", "--version"], check=True, capture_output=True)
    except:
        print("[*] Installing uv...")
        if platform.system() == "Windows":
            run_cmd("powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\"", shell=True)
        else:
            run_cmd("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
        # Update PATH for the current session
        os.environ["PATH"] += os.pathsep + os.path.expanduser("~/.cargo/bin")

    run_cmd(["uv", "venv", "venv", "--python", "3.12"])
    
    # Load environment for uv
    venv_env, bin_name = get_venv_env()
    
    # 4. Run Tasks
    task_install_torch(venv_env)
    
    print("\n--- Module: Core Requirements ---")
    run_cmd(["uv", "pip", "install", "-r", "requirements.txt"], env=venv_env)
    
    task_custom_nodes(venv_env)
    task_create_launchers(bin_name)
    
    print("\n" + "="*40)
    print("INSTALLATION SUCCESSFUL!")
    print(f"Location: {os.getcwd()}")
    print("Use the 'run_comfyui' file to start the application.")
    print("="*40)

if __name__ == "__main__":
    main()
