VERSION = 2.0
import subprocess
import os
import sys
import platform
import urllib.request
from pathlib import Path

# --- CENTRAL CONFIGURATION ---
GLOBAL_CUDA_VERSION = "13.0"  # High performance default for 2026
MIN_CUDA_FOR_50XX = "12.8"
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

# --- MODULES ---

def get_gpu_vendor():
    sys_platform = platform.system()
    if sys_platform == "Windows":
        try:
            res = subprocess.run(["wmic", "path", "win32_VideoController", "get", "name"], capture_output=True, text=True)
            out = res.stdout.upper()
            if "NVIDIA" in out: return "NVIDIA"
            if "AMD" in out or "RADEON" in out: return "AMD"
            if "INTEL" in out or "ARC" in out: return "INTEL"
        except: pass
    elif sys_platform == "Linux":
        try:
            for v_file in Path("/sys/class/drm").glob("card*/device/vendor"):
                v_id = v_file.read_text().strip()
                if "0x10de" in v_id: return "NVIDIA"
                if "0x1002" in v_id: return "AMD"
                if "0x8086" in v_id: return "INTEL"
        except: pass
        try:
            res = subprocess.run(["lspci"], capture_output=True, text=True)
            out = res.stdout.upper()
            if "NVIDIA" in out: return "NVIDIA"
            if "AMD" in out: return "AMD"
            if "INTEL" in out: return "INTEL"
        except: pass
    return "UNKNOWN"

def install_torch(env):
    vendor = get_gpu_vendor()
    print(f"\n[i] Detected Hardware: {vendor}")
    
    torch_url = "https://download.pytorch.org/whl/"
    target_cu = GLOBAL_CUDA_VERSION
    is_nightly = False

    if vendor == "NVIDIA":
        try:
            res = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True)
            if "RTX 50" in res.stdout:
                # Removed 'packaging' dependency, using direct list compare
                spec = [int(x) for x in target_cu.split('.')]
                req = [int(x) for x in MIN_CUDA_FOR_50XX.split('.')]
                if spec < req:
                    print(f"[!] Hardware (RTX 50xx) requires CUDA {MIN_CUDA_FOR_50XX}+. Overriding...")
                    target_cu = MIN_CUDA_FOR_50XX
                    is_nightly = True
        except: pass

    cmd = ["uv", "pip", "install"]
    if is_nightly: cmd += ["--pre"]
    cmd += ["torch", "torchvision", "torchaudio"]

    if vendor == "NVIDIA":
        cu_suffix = f"cu{target_cu.replace('.', '')}"
        cmd += ["--extra-index-url", f"{torch_url}{cu_suffix}"]
    elif vendor == "AMD":
        cmd += ["--index-url", f"{torch_url}rocm6.2"] # Default stable ROCm
    elif vendor == "INTEL":
        cmd += ["--index-url", f"{torch_url}xpu"]
    else:
        cmd += ["--index-url", f"{torch_url}cpu"]
    
    run_cmd(cmd, env=env)

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

def task_create_launchers(bin_dir):
    """Erstellt Launcher, die Logs anzeigen UND den Browser öffnen."""
    print("\n--- Module: Creating Launchers ---")
    is_win = platform.system() == "Windows"
    launcher_name = "run_comfyui.bat" if is_win else "run_comfyui.sh"
    url = "http://127.0.0.1:8188"

    if is_win:
        # Windows Version
        content = (
            f"@echo off\n"
            f"title DaSiWa ComfyUI - Console Logs\n"
            f"echo.\n"
            f"echo [INFO] Der Browser wird in Kuerze automatisch geoeffnet...\n"
            f"echo [INFO] Schliesse dieses Fenster, um ComfyUI zu beenden.\n"
            f"echo.\n"
            f"start /b cmd /c \"timeout /t 7 >nul && start {url}\"\n"
            f"\".\\venv\\{bin_dir}\\python.exe\" main.py\n"
            f"pause"
        )
    else:
        # Linux Version
        content = (
            f"#!/bin/bash\n"
            f"echo 'Launching ComfyUI... Browser opens in 7s'\n"
            f"(sleep 7 && xdg-open {url}) &\n"
            f"./venv/{bin_dir}/python main.py"
        )

    launcher_file = Path(launcher_name)
    launcher_file.write_text(content)
    if not is_win: 
        os.chmod(launcher_file, 0o755)
    
    print(f"[+] Launcher erstellt: {launcher_name}")

def main():
    print(f"=== DaSiWa ComfyUI Installer v{VERSION} ===")
    
    # 1. Directory Setup
    default_path = Path.cwd().resolve()
    user_input = input(f"Enter target path (Leave empty for {default_path}): ").strip()
    install_base = Path(user_input) if user_input else default_path
    comfy_path = install_base / "ComfyUI"

    if comfy_path.exists():
        print(f"[!] ABORT: {comfy_path} already exists."); sys.exit(1)

    os.makedirs(install_base, exist_ok=True)
    os.chdir(install_base)
    
    # 2. Clone Core
    run_cmd(["git", "clone", "https://github.com/comfyanonymous/ComfyUI"])
    os.chdir("ComfyUI")
    
    # 3. Infrastructure
    try:
        subprocess.run(["uv", "--version"], check=True, capture_output=True)
    except:
        if platform.system() == "Windows":
            run_cmd("powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\"", shell=True)
        else:
            run_cmd("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
        os.environ["PATH"] += os.pathsep + os.path.expanduser("~/.cargo/bin")

    run_cmd(["uv", "venv", "venv", "--python", "3.12"])
    venv_env, bin_name = get_venv_env()
    
    # 4. Run Tasks
    install_torch(venv_env)
    run_cmd(["uv", "pip", "install", "-r", "requirements.txt"], env=venv_env)
    task_custom_nodes(venv_env)
    task_create_launchers(bin_name)
    
    print("\n" + "="*40 + "\nINSTALLATION SUCCESSFUL!\n" + "="*40)

if __name__ == "__main__":
    main()
