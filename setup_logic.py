import subprocess
import os
import sys
import platform
import urllib.request
import shutil
import argparse # Added for branch handling
from pathlib import Path
import time
from utils.logger import Logger
from utils.reporter import Reporter

# --- CONFIGURATION ---
TARGET_PYTHON_VERSION = "3.12.10"
GLOBAL_CUDA_VERSION = "13.0"
MIN_CUDA_FOR_50XX = "12.8"
NODES_LIST_URL = "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/custom_nodes.txt"
NODES_LIST_FILE = "custom_nodes.txt"

PRIORITY_PACKAGES = [
    "torch", 
    "torchvision", 
    "torchaudio",
    "numpy>=2.1.0,<=2.3.0", 
    "pillow>=11.0.0", 
    "pydantic>=2.10.0",
]

IS_WIN = platform.system() == "Windows"
Logger.init()

# --- UTILITIES ---
def is_admin():
    try:
        if IS_WIN:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        return os.getuid() == 0
    except: return False

def run_cmd(cmd, env=None, shell=False, capture=False):
    return subprocess.run(cmd, check=True, env=env, shell=shell, capture_output=capture, text=True)

def get_venv_env():
    venv_path = Path.cwd() / "venv"
    full_env = os.environ.copy()
    full_env["VIRTUAL_ENV"] = str(venv_path)
    bin_dir = "Scripts" if IS_WIN else "bin"
    full_env["PATH"] = str(venv_path / bin_dir) + os.pathsep + full_env["PATH"]
    return full_env, bin_dir

def remove_readonly(func, path, excinfo=None):
    import stat
    os.chmod(path, stat.S_IWRITE)
    func(path)

# --- BOOTSTRAPS ---
def bootstrap_python():
    if not IS_WIN:
        Logger.error(f"Python {TARGET_PYTHON_VERSION} missing. Install via package manager.")
        sys.exit(1)
    Logger.log(f"Downloading Python {TARGET_PYTHON_VERSION}...", "info")
    url = f"https://www.python.org/ftp/python/{TARGET_PYTHON_VERSION}/python-{TARGET_PYTHON_VERSION}-amd64.exe"
    installer = Path.home() / "py_installer.exe"
    urllib.request.urlretrieve(url, installer)
    run_cmd(f'"{installer}" /quiet InstallAllUsers=1 PrependPath=1', shell=True)
    os.remove(installer)

def bootstrap_git():
    if not IS_WIN:
        Logger.error("Git missing. Install via sudo apt install git.")
        sys.exit(1)
    Logger.log("Downloading Git...", "info")
    url = "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe"
    installer = Path.home() / "git_installer.exe"
    urllib.request.urlretrieve(url, installer)
    run_cmd(f'"{installer}" /VERYSILENT /NORESTART', shell=True)
    os.remove(installer)

# --- HARDWARE DETECTION ---
def get_gpu_report():
    """Identifies GPUs and selects the most capable vendor."""
    gpus = []
    try:
        if IS_WIN:
            cmd = "wmic path win32_VideoController get Name, AdapterRAM /format:list"
            res = run_cmd(cmd, shell=True, capture=True)
            current_gpu = {}
            for line in res.stdout.splitlines():
                if "=" in line:
                    key, val = line.split("=", 1)
                    if key.strip() == "Name": current_gpu["name"] = val.strip()
                    if key.strip() == "AdapterRAM": current_gpu["vram"] = abs(int(val.strip())) if val.strip() else 0
                if "name" in current_gpu and "vram" in current_gpu:
                    gpus.append(current_gpu); current_gpu = {}
        else:
            res = run_cmd(["lspci"], capture=True)
            for line in res.stdout.splitlines():
                if "VGA" in line or "3D" in line: gpus.append({"name": line, "vram": 0})
    except: pass

    if not gpus: return {"vendor": "UNKNOWN", "name": "Generic"}

    gpus.sort(key=lambda x: x.get('vram', 0), reverse=True)
    winner = gpus[0]
    name_up = winner['name'].upper()
    
    vendor = "UNKNOWN"
    if "NVIDIA" in name_up: vendor = "NVIDIA"
    elif "INTEL" in name_up: vendor = "INTEL"
    elif "AMD" in name_up or "RADEON" in name_up: vendor = "AMD"

    Logger.log(f"Primary GPU: {winner['name']}", "ok")
    return {"vendor": vendor, "name": winner['name']}

# --- CORE TASKS ---
def install_torch(env, hw):
    vendor = hw['vendor']
    gpu_name = hw['name'].upper()
    target_cu = GLOBAL_CUDA_VERSION
    is_nightly = False
    
    if vendor == "NVIDIA":
        try:
            res_drv = run_cmd(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], capture=True)
            driver_ver = float(res_drv.stdout.split('.')[0])
            
            if "GTX 10" in gpu_name or "PASCAL" in gpu_name:
                Logger.log("Pascal Architecture detected. Using CUDA 12.1.", "warn")
                target_cu = "12.1"
            elif "RTX 50" in gpu_name:
                Logger.log("Blackwell 50-series detected. Enabling Nightly.", "info")
                target_cu = MIN_CUDA_FOR_50XX
                is_nightly = True
        except: pass

    cmd = ["uv", "pip", "install"]
    if is_nightly: cmd += ["--pre"]
    
    if target_cu == "12.1":
        cmd += ["torch==2.4.1", "torchvision==0.19.1", "torchaudio==2.4.1"]
    else:
        cmd += ["torch", "torchvision", "torchaudio"]
    
    base_url = "https://download.pytorch.org/whl/"
    if vendor == "NVIDIA":
        cmd += ["--extra-index-url", f"{base_url}cu{target_cu.replace('.', '')}"]
    elif vendor == "AMD":
        cmd += ["--index-url", f"{base_url}rocm6.2"]
    elif vendor == "INTEL":
        cmd += ["--index-url", f"{base_url}xpu"]

    Logger.log(f"Installing Torch for {vendor} (CUDA {target_cu})...", "info")
    run_cmd(cmd, env=env)

def task_check_ffmpeg(venv_env=None):
    Logger.log("Checking FFmpeg...", "info")
    if shutil.which("ffmpeg"):
        Logger.log("FFmpeg found.", "ok")
        return

    if IS_WIN:
        try:
            Logger.log("Attempting Winget FFmpeg install...", "info")
            run_cmd(["winget", "install", "ffmpeg", "--accept-source-agreements", "--accept-package-agreements"], capture=True)
            return
        except:
            Logger.log("Winget failed. Using UV failsafe...", "warn")

    if venv_env:
        try:
            run_cmd(["uv", "pip", "install", "static-ffmpeg"], env=venv_env)
            Logger.log("Portable FFmpeg installed in venv.", "ok")
        except:
            Logger.error("FFmpeg installation failed.")

def task_custom_nodes(env):
    Logger.log("nodes", "start")
    nodes_dir = Path("custom_nodes")
    nodes_dir.mkdir(exist_ok=True)
    
    mgr_path = nodes_dir / "comfyui-manager"
    if mgr_path.exists() and not (mgr_path / ".git").exists():
        shutil.rmtree(mgr_path, onexc=remove_readonly)
    
    if not mgr_path.exists():
        run_cmd(["git", "clone", "https://github.com/ltdrdata/ComfyUI-Manager", str(mgr_path)])
    else:
        run_cmd(["git", "-C", str(mgr_path), "pull"])

    try:
        urllib.request.urlretrieve(NODES_LIST_URL, NODES_LIST_FILE)
        with open(NODES_LIST_FILE, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        
        for line in lines:
            repo_url = line.split("|")[0].strip()
            if "comfyui-manager" in repo_url.lower(): continue
            
            name = repo_url.split("/")[-1].replace(".git", "")
            node_path = nodes_dir / name
            
            if not node_path.exists():
                Logger.log(f"Cloning {name}...", "info")
                run_cmd(["git", "clone", "--recursive", repo_url, str(node_path)])
            else:
                run_cmd(["git", "-C", str(node_path), "pull"])

            req = node_path / "requirements.txt"
            if req.exists():
                run_cmd(["uv", "pip", "install", "-r", str(req)], env=env)
    except Exception as e:
        Logger.error(f"Custom node sync error: {e}")
    
    Logger.log("nodes", "done")

def task_create_launchers(bin_dir):
    l_name = "run_comfyui.bat" if IS_WIN else "run_comfyui.sh"
    venv_python = Path.cwd() / "venv" / bin_dir / ("python.exe" if IS_WIN else "python")
    
    # Simple, standard arguments
    args = "--enable-manager --preview-method auto"

    if IS_WIN:
        content = f"@echo off\ntitle ComfyUI\nstart http://127.0.0.1:8188\n\"{venv_python}\" main.py {args}\npause"
    else:
        content = f"#!/bin/bash\n(sleep 5 && xdg-open http://127.0.0.1:8188) &\n\"{venv_python}\" main.py {args}"
    
    Path(l_name).write_text(content)
    if not IS_WIN: os.chmod(l_name, 0o755)
    Logger.log(f"Launcher created: {l_name}", "ok")

# --- MAIN ---
def main():
    # Setup Argument Parser
    parser = argparse.ArgumentParser()
    # Capture start time at the very beginning
    start_time = time.time()
    # This now refers to the INSTALLER branch (testing/main)
    parser.add_argument("--branch", default="main", help="Installer logic branch")
    args = parser.parse_args()
    installer_branch = args.branch

    # 2. Define the official ComfyUI branch
    # We hardcode this to 'master'
    COMFY_OFFICIAL_BRANCH = "master" 

    try: run_cmd(["python", "--version"], capture=True)
    except: bootstrap_python(); sys.exit(0)
    try: run_cmd(["git", "--version"], capture=True)
    except: bootstrap_git(); sys.exit(0)

    # Note the Installer Branch in the logs for your own tracking
    Logger.log(f"DaSiWa ComfyUI Installer (Installer: {installer_branch})", "info", bold=True)
    hw = get_gpu_report()
    
    base_path = Path.cwd()
    comfy_path = base_path / "ComfyUI"

    # --- REPO SYNC (Always uses ComfyUI Master) ---
    if not comfy_path.exists():
        Logger.log(f"Cloning ComfyUI ({COMFY_OFFICIAL_BRANCH})...", "info")
        run_cmd(["git", "clone", "-b", COMFY_OFFICIAL_BRANCH, "https://github.com/comfyanonymous/ComfyUI", str(comfy_path)])
    
    os.chdir(comfy_path)

    # Branch Guard: Ensure the folder is on master
    try:
        current_comfy_branch = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True).stdout.strip()
        if current_comfy_branch != COMFY_OFFICIAL_BRANCH:
            Logger.log(f"Aligning ComfyUI to {COMFY_OFFICIAL_BRANCH}...", "warn")
            run_cmd(["git", "fetch", "origin"])
            run_cmd(["git", "checkout", COMFY_OFFICIAL_BRANCH])
            run_cmd(["git", "pull", "origin", COMFY_OFFICIAL_BRANCH])
    except Exception as e:
        Logger.log(f"ComfyUI branch sync skipped: {e}", "info")

    # --- ENVIRONMENT SETUP ---
    Logger.log("Preparing Virtual Environment...", "info")
    run_cmd(["uv", "venv", "venv", "--python", TARGET_PYTHON_VERSION, "--clear"])
    venv_env, bin_dir = get_venv_env()

    # --- TASKS ---
    task_check_ffmpeg(venv_env)
    install_torch(venv_env, hw)
    run_cmd(["uv", "pip", "install", "-r", "requirements.txt"], env=venv_env)
    task_custom_nodes(venv_env)

    # --- FINALIZATION ---
    Logger.log("Finalizing stability packages...", "info")
    run_cmd(["uv", "pip", "install"] + PRIORITY_PACKAGES, env=venv_env)
    
    task_create_launchers(bin_dir)

    # --- THE SUMMARY CALL ---
    Reporter.show_summary(hw, venv_env, start_time)

    Logger.success("Installation Complete!")
    if input("\nLaunch ComfyUI now? [Y/n]: ").lower() in ('y', ''):
        l = "run_comfyui.bat" if IS_WIN else "./run_comfyui.sh"
        # On Linux/Unix, we need to make sure the script is executable
        if not IS_WIN:
            os.chmod(l, 0o755)
        subprocess.Popen([l], shell=IS_WIN, creationflags=subprocess.CREATE_NEW_CONSOLE if IS_WIN else 0)

if __name__ == "__main__":
    main()