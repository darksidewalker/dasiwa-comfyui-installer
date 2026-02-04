import subprocess
import os
import sys
import platform
import urllib.request
import shutil
from pathlib import Path

# --- CENTRAL CONFIGURATION ---
VERSION = 2.6
GLOBAL_CUDA_VERSION = "13.0"
MIN_CUDA_FOR_50XX = "12.8"
NODES_LIST_URL = "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/custom_nodes.txt"
NODES_LIST_FILE = "custom_nodes.txt"

# Global OS check
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
        # Method 1: WMIC (Legacy)
        try:
            res = subprocess.run(["wmic", "path", "win32_VideoController", "get", "name"], capture_output=True, text=True)
            out = res.stdout.upper()
            if "NVIDIA" in out: return "NVIDIA"
            if "AMD" in out or "RADEON" in out: return "AMD"
        except: pass

        # Method 2: PowerShell (Modern Windows 11)
        try:
            ps_cmd = "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"
            res = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True)
            out = res.stdout.upper()
            if "NVIDIA" in out: return "NVIDIA"
            if "AMD" in out or "RADEON" in out: return "AMD"
        except: pass

        # Method 3: Registry Check (Deep Fallback)
        try:
            reg_cmd = 'reg query "HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}" /s'
            res = subprocess.run(reg_cmd, capture_output=True, text=True, shell=True)
            out = res.stdout.upper()
            if "NVIDIA" in out: return "NVIDIA"
            if "AMD" in out: return "AMD"
        except: pass
    else:
        # Linux detection remains the same
        try:
            for v_file in Path("/sys/class/drm").glob("card*/device/vendor"):
                v_id = v_file.read_text().strip()
                if "0x10de" in v_id: return "NVIDIA"
                if "0x1002" in v_id: return "AMD"
        except: pass
    return "UNKNOWN"

# --- TASK MODULES ---
def install_torch(env):
    vendor = get_gpu_vendor()
    
    if vendor == "UNKNOWN":
        print("\n[!] WARNING: Automatic GPU detection failed.")
        print("Installing the CPU version is disabled to prevent a broken setup.")
        print("Please specify your hardware:")
        print(" [1] NVIDIA (RTX 20, 30, 40, 50-series, etc.)")
        print(" [2] AMD (Radeon, RX-series)")
        print(" [3] Intel (Arc)")
        print(" [A] Abort Installation")
        
        choice = input("\nSelect [1/2/3/A]: ").strip().upper()
        if choice == "1": vendor = "NVIDIA"
        elif choice == "2": vendor = "AMD"
        elif choice == "3": vendor = "INTEL"
        else:
            print("[!] Installation aborted by user."); sys.exit(0)

    print(f"\n[i] Preparing installation for: {vendor}")
    
    torch_url = "https://download.pytorch.org/whl/"
    target_cu = GLOBAL_CUDA_VERSION
    is_nightly = False

    if vendor == "NVIDIA":
        try:
            # Check for RTX 50-series specifically
            res = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], 
                                 capture_output=True, text=True)
            if "RTX 50" in res.stdout:
                print(f"[!] Blackwell (RTX 50) detected! Using CUDA {MIN_CUDA_FOR_50XX}...")
                target_cu = MIN_CUDA_FOR_50XX
                is_nightly = True
        except: 
            # If nvidia-smi fails but user chose NVIDIA, we stick to stable 12.4
            pass

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
            f"echo [INFO] Opening Browser in 8 seconds...\n"
            f"echo [INFO] Latest Frontend and Manager enabled.\n"
            f"echo.\n"
            f"start /b cmd /c \"timeout /t 8 >nul && start {url}\"\n"
            f"\".\\venv\\{bin_dir}\\python.exe\" main.py {args}\n"
            f"if %errorlevel% neq 0 (\n"
            f"    echo.\n"
            f"    echo [!] ComfyUI failed to start.\n"
            f"    pause\n"
            f")\n"
            f"pause"
        )
    else:
        content = (
            f"#!/bin/bash\n"
            f"echo 'Opening Browser in 8s... Manager enabled.'\n"
            f"(sleep 8 && xdg-open {url}) &\n"
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
    
    # 1. Directory Setup
    default_path = Path.cwd().resolve()
    user_input = input(f"Target path (Enter for {default_path}): ").strip()
    install_base = Path(user_input) if user_input else default_path
    comfy_path = install_base / "ComfyUI"
    
    # Backup setup
    yaml_config = comfy_path / "extra_model_paths.yaml"
    temp_backup = Path.home() / ".dasiwa_temp_backup.yaml"

    mode = "install"
    if comfy_path.exists():
        print(f"\n[!] CONFLICT: {comfy_path} already exists.")
        print(" [U] Update: Refresh core/venv (Keeps models & config)")
        print(" [O] Overwrite: DELETE everything (Wipes models, backs up config)")
        print(" [A] Abort")
        choice = input("Selection [U/O/A] (Default: A): ").strip().lower()

        if choice == 'o':
            if yaml_config.exists():
                print("[*] Backing up extra_model_paths.yaml...")
                shutil.copy2(yaml_config, temp_backup)
            print("[*] Deleting old installation...")
            shutil.rmtree(comfy_path)
            mode = "install"
        elif choice == 'u':
            print("[*] Entering Update Mode...")
            mode = "update"
        else:
            print("[!] Aborting."); sys.exit(0)

    os.makedirs(install_base, exist_ok=True)
    os.chdir(install_base)
    
    # 2. Clone or Update
    if mode == "install":
        print("\n--- Cloning ComfyUI ---")
        run_cmd(["git", "clone", "https://github.com/comfyanonymous/ComfyUI"])
        os.chdir("ComfyUI")
        if temp_backup.exists():
            print("[+] Restoring model configuration...")
            shutil.move(temp_backup, Path.cwd() / "extra_model_paths.yaml")
    else:
        print("\n--- Updating Core Code ---")
        os.chdir("ComfyUI")
        run_cmd(["git", "fetch", "--all"])
        run_cmd(["git", "reset", "--hard", "origin/main"])

    # 3. Infrastructure
    try:
        subprocess.run(["uv", "--version"], check=True, capture_output=True)
    except:
        if IS_WIN:
            run_cmd("powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\"", shell=True)
        else:
            run_cmd("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
        os.environ["PATH"] += os.pathsep + os.path.expanduser("~/.cargo/bin")

    print("\n--- Environment Setup ---")
    run_cmd(["uv", "venv", "venv", "--python", "3.12"])
    venv_env, bin_name = get_venv_env()
    
    install_torch(venv_env)
    run_cmd(["uv", "pip", "install", "-r", "requirements.txt"], env=venv_env)
    task_custom_nodes(venv_env)
    task_create_launchers(bin_name)
    
    print("\n" + "="*40 + "\nINSTALLATION COMPLETE!\n" + "="*40)

    # 4. Auto-Launch
    launch_now = input("\nWould you like to launch ComfyUI now? [Y/n]: ").strip().lower()
    if launch_now in ["", "y", "yes"]:
        print("\n[*] Launching ComfyUI...")
        launcher = "run_comfyui.bat" if IS_WIN else "./run_comfyui.sh"
        if IS_WIN:
            subprocess.Popen([launcher], creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen(["bash", launcher], start_new_session=True)
        print("[i] Started in new window. You can close this installer.")
    else:
        l_name = "run_comfyui.bat" if IS_WIN else "run_comfyui.sh"
        print(f"\n[i] Setup finished. Use '{l_name}' to start later.")

if __name__ == "__main__":
    main()
