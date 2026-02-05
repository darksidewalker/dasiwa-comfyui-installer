import subprocess
import os
import sys
import platform
import urllib.request
import shutil
from pathlib import Path

# --- CENTRAL CONFIGURATION ---
VERSION = 2.9
TARGET_PYTHON_VERSION = "3.12.10"
GLOBAL_CUDA_VERSION = "13.0"
MIN_CUDA_FOR_50XX = "12.8"
NODES_LIST_URL = "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/custom_nodes.txt"
NODES_LIST_FILE = "custom_nodes.txt"

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

# --- BOOTSTRAP GATES ---
def bootstrap_python():
    if not IS_WIN:
        print(f"[!] Python missing. Please install {TARGET_PYTHON_VERSION}.")
        sys.exit(1)

    print(f"\n[!] Python {TARGET_PYTHON_VERSION} not found or blocked by MS-Store.")
    print("[*] Downloading official installer from Python.org...")
    url = f"https://www.python.org/ftp/python/{TARGET_PYTHON_VERSION}/python-{TARGET_PYTHON_VERSION}-amd64.exe"
    installer_path = Path.home() / "python_installer.exe"
    
    try:
        urllib.request.urlretrieve(url, installer_path)
        print("[*] Running silent installation (This bypasses the MS-Store)...")
        # PrependPath=1 is critical here to jump ahead of the Store alias in the Registry
        install_cmd = f'"{installer_path}" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0'
        subprocess.run(install_cmd, shell=True, check=True)
        print("\n[+] Python installed successfully!")
    except Exception as e:
        print(f"[!] Critical Error: {e}")
        sys.exit(1)
    finally:
        if installer_path.exists(): os.remove(installer_path)

def bootstrap_git():
    if not IS_WIN: sys.exit(1)
    print("\n[!] Git missing. Downloading official Git...")
    git_url = "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe"
    installer_path = Path.home() / "git_installer.exe"
    try:
        urllib.request.urlretrieve(git_url, installer_path)
        print("[*] Installing Git silently...")
        install_cmd = f'"{installer_path}" /VERYSILENT /NORESTART /NOCANCEL /SP-'
        subprocess.run(install_cmd, shell=True, check=True)
    finally:
        if installer_path.exists(): os.remove(installer_path)

def get_gpu_vendor():
    if IS_WIN:
        try:
            ps_cmd = "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"
            res = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True)
            out = res.stdout.upper()
            if "NVIDIA" in out: return "NVIDIA"
            if "AMD" in out or "RADEON" in out: return "AMD"
        except: pass
    else:
        # --- Linux Detection Logic ---
        try:
            # Check kernel sysfs for vendor IDs
            # 0x10de = NVIDIA, 0x1002 = AMD, 0x8086 = Intel
            for v_file in Path("/sys/class/drm").glob("card*/device/vendor"):
                v_id = v_file.read_text().strip().lower()
                if "0x10de" in v_id: return "NVIDIA"
                if "0x1002" in v_id: return "AMD"
                if "0x8086" in v_id: return "INTEL"
            
            # Fallback: Try lspci if sysfs is restricted
            res = subprocess.run(["lspci"], capture_output=True, text=True)
            out = res.stdout.upper()
            if "NVIDIA" in out: return "NVIDIA"
            if "AMD" in out or "ATI" in out: return "AMD"
            if "INTEL" in out and "GRAPHICS" in out: return "INTEL"
        except: pass

    return "UNKNOWN"

# --- TASK MODULES ---
def install_torch(env):
    vendor = get_gpu_vendor()
    
    # If detection fails, don't crash—ask the user!
    if vendor == "UNKNOWN":
        print("\n[!] GPU Detection Failed (Common on some Linux distros or WSL).")
        print("Please choose your hardware manually to avoid a broken CPU-only install:")
        print(" [1] NVIDIA (RTX/GTX)")
        print(" [2] AMD (Radeon)")
        print(" [3] Intel (Arc)")
        print(" [A] Abort")
        
        choice = input("\nSelection: ").strip().upper()
        vendor = {"1":"NVIDIA", "2":"AMD", "3":"INTEL"}.get(choice, "ABORT")
        if vendor == "ABORT": 
            print("[!] Installation cancelled."); sys.exit(0)

    print(f"\n[i] Configuring installation for: {vendor}")

    target_cu = GLOBAL_CUDA_VERSION
    is_nightly = False
    if vendor == "NVIDIA":
        try:
            res = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True)
            if "RTX 50" in res.stdout:
                target_cu = MIN_CUDA_FOR_50XX
                is_nightly = True
        except: pass

    cmd = ["uv", "pip", "install"]
    if is_nightly: cmd += ["--pre"]
    cmd += ["torch", "torchvision", "torchaudio"]
    if vendor == "NVIDIA": cmd += ["--extra-index-url", f"https://download.pytorch.org/whl/cu{target_cu.replace('.', '')}"]
    elif vendor == "AMD": cmd += ["--index-url", "https://download.pytorch.org/whl/rocm6.2"]
    elif vendor == "INTEL": cmd += ["--index-url", "https://download.pytorch.org/whl/xpu"]
    run_cmd(cmd, env=env)

def task_create_launchers(bin_dir):
    launcher_name = "run_comfyui.bat" if IS_WIN else "run_comfyui.sh"
    args = "--enable-manager --front-end-version Comfy-Org/ComfyUI_frontend@latest"
    if IS_WIN:
        content = f"@echo off\ntitle DaSiWa ComfyUI\nstart \"\" \"http://127.0.0.1:8188\"\n\".\\venv\\{bin_dir}\\python.exe\" main.py {args}\npause"
    else:
        content = f"#!/bin/bash\n(sleep 7 && xdg-open http://127.0.0.1:8188) &\n./venv/{bin_dir}/python main.py {args}"
    Path(launcher_name).write_text(content)
    if not IS_WIN: os.chmod(launcher_name, 0o755)

def task_custom_nodes(env):
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
    except: pass

# --- MAIN ---
def main():
    # Detect MS-Store Fake Python
    try:
        res = subprocess.run(["python", "-c", "import sys; print(sys.prefix)"], capture_output=True, text=True)
        if "WindowsApps" in res.stdout or res.returncode != 0: raise Exception("StoreAlias")
    except:
        bootstrap_python()
        print("\n[!] RESTART REQUIRED: Close this window and run the installer again.")
        sys.exit(0)

    try: subprocess.run(["git", "--version"], capture_output=True, text=True)
    except:
        bootstrap_git()
        print("\n[!] RESTART REQUIRED: Close this window and run the installer again.")
        sys.exit(0)

    print(f"=== DaSiWa ComfyUI Installer v{VERSION} ===")
    default_path = Path.cwd().resolve()
    user_input = input(f"Target path (Enter for {default_path}): ").strip()
    install_base = Path(user_input) if user_input else default_path
    comfy_path = install_base / "ComfyUI"
    
    yaml_config = comfy_path / "extra_model_paths.yaml"
    temp_backup = Path.home() / ".dasiwa_temp_backup.yaml"

    mode = "install"
    if comfy_path.exists():
        c = input(f"\n[!] {comfy_path} exists. [U]pdate / [O]verwrite / [A]bort: ").strip().lower()
        if c == 'o':
            if yaml_config.exists(): shutil.copy2(yaml_config, temp_backup)
            shutil.rmtree(comfy_path); mode = "install"
        elif c == 'u': mode = "update"
        else: sys.exit(0)

    os.makedirs(install_base, exist_ok=True)
    os.chdir(install_base)
    
    if mode == "install":
        run_cmd(["git", "clone", "https://github.com/comfyanonymous/ComfyUI"])
        os.chdir("ComfyUI")
        if temp_backup.exists(): shutil.move(temp_backup, Path.cwd() / "extra_model_paths.yaml")
    else:
        os.chdir("ComfyUI")
        run_cmd(["git", "fetch", "--all"])
        run_cmd(["git", "reset", "--hard", "origin/main"])

    try: subprocess.run(["uv", "--version"], check=True, capture_output=True)
    except:
        if IS_WIN: run_cmd("powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\"", shell=True)
        else: run_cmd("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
        os.environ["PATH"] += os.pathsep + os.path.expanduser("~/.cargo/bin")

    run_cmd(["uv", "venv", "venv", "--python", TARGET_PYTHON_VERSION])
    venv_env, bin_name = get_venv_env()
    
    install_torch(venv_env)
    run_cmd(["uv", "pip", "install", "-r", "requirements.txt"], env=venv_env)
    task_custom_nodes(venv_env)
    task_create_launchers(bin_name)
    
    print("\n" + "="*40 + "\nDONE!\n" + "="*40)
    if input("\nLaunch now? [Y/n]: ").strip().lower() in ["", "y", "yes"]:
        l = "run_comfyui.bat" if IS_WIN else "./run_comfyui.sh"
        if IS_WIN: subprocess.Popen([l], creationflags=subprocess.CREATE_NEW_CONSOLE)
        else: subprocess.Popen(["bash", l], start_new_session=True)

if __name__ == "__main__":
    main()
