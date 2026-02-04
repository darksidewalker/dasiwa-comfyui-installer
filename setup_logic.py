import subprocess
import os
import sys
import platform
import urllib.request
import shutil
from pathlib import Path

# --- CENTRAL CONFIGURATION ---
VERSION = 2.8
TARGET_PYTHON_VERSION = "3.12.10"  # <--- NEW: Locked official version
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

# --- OFFICIAL PYTHON BOOTSTRAPPER ---
def bootstrap_python():
    if not IS_WIN:
        print("[!] Auto-bootstrap is currently only for Windows. Please install Python 3.12 manually.")
        sys.exit(1)

    print(f"\n[!] Python {TARGET_PYTHON_VERSION} not found or MS-Store error.")
    print("[*] Downloading official installer from Python.org...")
    
    # URL for the specific amd64 version
    url = f"https://www.python.org/ftp/python/{TARGET_PYTHON_VERSION}/python-{TARGET_PYTHON_VERSION}-amd64.exe"
    installer_path = Path.home() / "python_installer.exe"
    
    try:
        urllib.request.urlretrieve(url, installer_path)
        print("[*] Running silent installation (PrependPath=1)...")
        # /quiet: no UI, InstallAllUsers: Program Files, PrependPath: update system PATH
        install_cmd = f'"{installer_path}" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0'
        subprocess.run(install_cmd, shell=True, check=True)
        print("\n[+] Python installed successfully!")
    except Exception as e:
        print(f"[!] Critical Error during Python install: {e}")
        sys.exit(1)
    finally:
        if installer_path.exists(): os.remove(installer_path)

# --- HARDWARE DETECTION ---
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
        try:
            for v_file in Path("/sys/class/drm").glob("card*/device/vendor"):
                v_id = v_file.read_text().strip()
                if "0x10de" in v_id: return "NVIDIA"
                if "0x1002" in v_id: return "AMD"
        except: pass
    return "UNKNOWN"

# ... (install_torch, task_create_launchers, and task_custom_nodes remain the same) ...

def install_torch(env):
    vendor = get_gpu_vendor()
    if vendor == "UNKNOWN":
        print("\n[!] GPU Detection Failed.")
        print(" [1] NVIDIA | [2] AMD | [3] Intel | [A] Abort")
        choice = input("Selection: ").strip().upper()
        if choice == "1": vendor = "NVIDIA"
        elif choice == "2": vendor = "AMD"
        elif choice == "3": vendor = "INTEL"
        else: sys.exit(0)

    torch_url = "https://download.pytorch.org/whl/"
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

    if vendor == "NVIDIA":
        cu_suffix = f"cu{target_cu.replace('.', '')}"
        cmd += ["--extra-index-url", f"{torch_url}{cu_suffix}"]
    elif vendor == "AMD":
        cmd += ["--index-url", f"{torch_url}rocm6.2"]
    elif vendor == "INTEL":
        cmd += ["--index-url", f"{torch_url}xpu"]
    run_cmd(cmd, env=env)

def task_create_launchers(bin_dir):
    launcher_name = "run_comfyui.bat" if IS_WIN else "run_comfyui.sh"
    url = "http://127.0.0.1:8188"
    args = "--enable-manager --front-end-version Comfy-Org/ComfyUI_frontend@latest"
    if IS_WIN:
        content = f"@echo off\ntitle DaSiWa ComfyUI\nstart /b cmd /c \"timeout /t 7 >nul && start {url}\"\n\".\\venv\\{bin_dir}\\python.exe\" main.py {args}\npause"
    else:
        content = f"#!/bin/bash\n(sleep 7 && xdg-open {url}) &\n./venv/{bin_dir}/python main.py {args}"
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
    # Verify Python exists and is a real install, not a Store alias
    try:
        res = subprocess.run(["python", "--version"], capture_output=True, text=True)
        if "Python" not in res.stdout: raise Exception()
    except:
        bootstrap_python()
        print("\n[!] Setup complete. Please restart your Terminal/CMD and run the script again.")
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
        print(f"\n[!] CONFLICT: {comfy_path} exists. [U]pdate / [O]verwrite / [A]bort")
        c = input("Choice: ").strip().lower()
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

    # UV Install
    try: subprocess.run(["uv", "--version"], check=True, capture_output=True)
    except:
        if IS_WIN: run_cmd("powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\"", shell=True)
        else: run_cmd("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
        os.environ["PATH"] += os.pathsep + os.path.expanduser("~/.cargo/bin")

    # Use the global parameter for venv creation
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
