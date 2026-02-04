import subprocess
import os
import sys
import platform
import urllib.request
from pathlib import Path

# --- CENTRAL CONFIGURATION ---
VERSION = 2.5
GLOBAL_CUDA_VERSION = "13.0"
MIN_CUDA_FOR_50XX = "12.8"
NODES_LIST_URL = "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/custom_nodes.txt"
NODES_LIST_FILE = "custom_nodes.txt"

# Global OS check to avoid NameErrors
IS_WIN = platform.system() == "Windows"

# --- CORE UTILS ---
def run_cmd(cmd, env=None, shell=False):
    subprocess.run(cmd, check=True, env=env, shell=shell)

def get_venv_env():
    venv_path = Path.cwd() / "venv"
    full_env = os.environ.copy()
    full_env["VIRTUAL_ENV"] = str(venv_path)
    bin_dir = "Scripts" if IS_WIN else "bin"
    full_env["PATH"] = str(venv_path / bin_dir) + os.pathsep + full_env["PATH"]
    return full_env, bin_dir

# --- HARDWARE DETECTION ---
def get_gpu_vendor():
    if IS_WIN:
        try:
            res = subprocess.run(["wmic", "path", "win32_VideoController", "get", "name"], capture_output=True, text=True)
            out = res.stdout.upper()
            if "NVIDIA" in out: return "NVIDIA"
            if "AMD" in out or "RADEON" in out: return "AMD"
            if "INTEL" in out or "ARC" in out: return "INTEL"
        except: pass
    else:
        try:
            for v_file in Path("/sys/class/drm").glob("card*/device/vendor"):
                v_id = v_file.read_text().strip()
                if "0x10de" in v_id: return "NVIDIA"
                if "0x1002" in v_id: return "AMD"
                if "0x8086" in v_id: return "INTEL"
        except: pass
    return "UNKNOWN"

# --- TASK MODULES ---
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
                spec = [int(x) for x in target_cu.split('.')]
                req = [int(x) for x in MIN_CUDA_FOR_50XX.split('.')]
                if spec < req:
                    print(f"[!] RTX 50-series detected! Overriding to CUDA {MIN_CUDA_FOR_50XX}...")
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
        cmd += ["--index-url", f"{torch_url}rocm6.2"]
    elif vendor == "INTEL":
        cmd += ["--index-url", f"{torch_url}xpu"]
    else:
        cmd += ["--index-url", f"{torch_url}cpu"]
    
    run_cmd(cmd, env=env)

def task_create_launchers(bin_dir):
    print("\n--- Module: Creating Launchers ---")
    launcher_name = "run_comfyui.bat" if IS_WIN else "run_comfyui.sh"
    url = "http://127.0.0.1:8188"
    args = "--enable-manager --front-end-version Comfy-Org/ComfyUI_frontend@latest"

    if IS_WIN:
        content = (
            f"@echo off\n"
            f"title DaSiWa ComfyUI - Console\n"
            f"echo.\n"
            f"echo [INFO] Opening Browser in 7 seconds...\n"
            f"echo [INFO] Latest Frontend & Manager enabled.\n"
            f"echo.\n"
            f"start /b cmd /c \"timeout /t 7 >nul && start {url}\"\n"
            f"\".\\venv\\{bin_dir}\\python.exe\" main.py {args}\n"
            f"pause"
        )
    else:
        content = (
            f"#!/bin/bash\n"
            f"echo 'Opening Browser in 7s... Manager enabled.'\n"
            f"(sleep 7 && xdg-open {url}) &\n"
            f"./venv/{bin_dir}/python main.py {args}"
        )

    Path(launcher_name).write_text(content)
    if not IS_WIN: os.chmod(launcher_name, 0o755)
    print(f"[+] Launcher created: {launcher_name}")

def task_custom_nodes(env):
    print("\n--- Module: Syncing Custom Nodes ---")
    os.makedirs("custom_nodes", exist_ok=True)
    try:
        urllib.request.urlretrieve(NODES_LIST_URL, NODES_LIST_FILE)
        with open(NODES_LIST_FILE, "r") as f:
            repos = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        for repo in repos:
            name = repo.split("/")[-1].replace(".git", "")
            node_dir = Path("custom_nodes") / name
            if not node_dir.exists():
                run_cmd(["git", "clone", repo, str(node_dir)])
            if (node_dir / "requirements.txt").exists():
                run_cmd(["uv", "pip", "install", "-r", str(node_dir / "requirements.txt")], env=env)
        if os.path.exists(NODES_LIST_FILE): os.remove(NODES_LIST_FILE)
    except Exception as e: print(f"[*] Node Note: {e}")

# --- MAIN ---
def main():
    print(f"=== DaSiWa ComfyUI Installer v{VERSION} ===")
    
    default_path = Path.cwd().resolve()
    user_input = input(f"Target path (Enter for {default_path}): ").strip()
    install_base = Path(user_input) if user_input else default_path
    comfy_path = install_base / "ComfyUI"

    if comfy_path.exists():
        print("[!] ERROR: Folder exists."); sys.exit(1)

    os.makedirs(install_base, exist_ok=True)
    os.chdir(install_base)
    
    print("\n--- Cloning ComfyUI ---")
    run_cmd(["git", "clone", "https://github.com/comfyanonymous/ComfyUI"])
    os.chdir("ComfyUI")
    
    try:
        subprocess.run(["uv", "--version"], check=True, capture_output=True)
    except:
        if IS_WIN:
            run_cmd("powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\"", shell=True)
        else:
            run_cmd("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
        os.environ["PATH"] += os.pathsep + os.path.expanduser("~/.cargo/bin")

    run_cmd(["uv", "venv", "venv", "--python", "3.12"])
    venv_env, bin_name = get_venv_env()
    
    install_torch(venv_env)
    run_cmd(["uv", "pip", "install", "-r", "requirements.txt"], env=venv_env)
    task_custom_nodes(venv_env)
    task_create_launchers(bin_name)
    
    print("\n" + "="*40 + "\nINSTALLATION COMPLETE!\n" + "="*40)

    # Auto-Launch Prompt
    launch_now = input("\nWould you like to launch ComfyUI now? [Y/n]: ").strip().lower()
    if launch_now in ["", "y", "yes"]:
        print("\n[*] Launching ComfyUI with Latest Frontend...")
        launcher = "run_comfyui.bat" if IS_WIN else "./run_comfyui.sh"
        
        if IS_WIN:
            subprocess.Popen([launcher], creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            # On Linux, we use a separate process group so closing the installer won't kill Comfy
            subprocess.Popen(["bash", launcher], start_new_session=True)
        
        print("[i] ComfyUI started in a new window. You can close this installer.")
    else:
        launcher_name = "run_comfyui.bat" if IS_WIN else "run_comfyui.sh"
        print(f"\n[i] Setup finished. Use '{launcher_name}' to start later.")

if __name__ == "__main__":
    main()
