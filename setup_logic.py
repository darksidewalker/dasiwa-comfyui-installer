import subprocess
import os
import sys
import platform
import urllib.request
import shutil
import argparse
import time
from pathlib import Path
import json

# Import Custom Utils
from utils.logger import Logger
from utils.reporter import Reporter
from utils.hardware import get_gpu_report
from utils.task_nodes import task_custom_nodes

# --- INITIALIZATION ---
IS_WIN = platform.system() == "Windows"
Logger.init()

def load_config():
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except Exception as e:
        Logger.error(f"Failed to load config.json: {e}")
        sys.exit(1)

CONFIG = load_config()

# --- CONSTANTS FROM CONFIG ---
TARGET_PYTHON_VERSION = CONFIG["python"]["full_version"]
GLOBAL_CUDA_VERSION = CONFIG["cuda"]["global"]
MIN_CUDA_FOR_50XX = CONFIG["cuda"]["min_cuda_for_50xx"]
NODES_LIST_URL = CONFIG["url"]["custom_nodes"]
NODES_LIST_FILE = "custom_nodes.txt"

PRIORITY_PACKAGES = [
    "torch", 
    "torchvision", 
    "torchaudio",
    "numpy>=2.1.0,<=2.3.0", 
    "pillow>=11.0.0", 
    "pydantic>=2.10.0",
]

# --- COMMAND WRAPPERS ---
def run_cmd(cmd, env=None, shell=False, capture=False):
    return subprocess.run(cmd, check=True, env=env, shell=shell, capture_output=capture, text=True)

def get_venv_env(comfy_path):
    venv_path = comfy_path / "venv"
    full_env = os.environ.copy()
    full_env["VIRTUAL_ENV"] = str(venv_path)
    bin_dir = "Scripts" if IS_WIN else "bin"
    full_env["PATH"] = str(venv_path / bin_dir) + os.pathsep + full_env["PATH"]
    return full_env, bin_dir

# --- BOOTSTRAPS ---
def ensure_dependencies():
    """Ensures Python version and Git are present."""
    # Check Python
    current_py = platform.python_version()
    if not current_py.startswith(CONFIG["python"]["display_name"]):
        Logger.warn(f"Running on Python {current_py}, but {TARGET_PYTHON_VERSION} is preferred.")

    # Check Git
    try:
        run_cmd(["git", "--version"], capture=True)
    except:
        if IS_WIN:
            Logger.log("Downloading Git...", "info")
            url = CONFIG["urls"]["git_windows"]
            installer = Path.home() / "git_installer.exe"
            urllib.request.urlretrieve(url, installer)
            run_cmd(f'"{installer}" /VERYSILENT /NORESTART', shell=True)
            os.remove(installer)
        else:
            Logger.error("Git missing. Install via: sudo apt install git")
            sys.exit(1)

# --- CORE TASKS ---
def install_torch(env, hw):
    vendor, gpu_name = hw['vendor'], hw['name'].upper()
    target_cu, is_nightly = GLOBAL_CUDA_VERSION, False
    
    if vendor == "NVIDIA":
        if "RTX 50" in gpu_name:
            target_cu, is_nightly = MIN_CUDA_FOR_50XX, True
        elif any(x in gpu_name for x in ["GTX 10", "PASCAL"]):
            target_cu = "12.1"

    cmd = ["uv", "pip", "install"]
    if is_nightly: cmd += ["--pre"]
    
    # Specific versions for older CUDA fallback
    if target_cu == "12.1":
        cmd += ["torch==2.4.1", "torchvision==0.19.1", "torchaudio==2.4.1"]
    else:
        cmd += ["torch", "torchvision", "torchaudio"]
    
    whl_url = "https://download.pytorch.org/whl/"
    if vendor == "NVIDIA":
        cmd += ["--extra-index-url", f"{whl_url}cu{target_cu.replace('.', '')}"]
    elif vendor == "AMD":
        cmd += ["--index-url", f"{whl_url}rocm6.2"]
    
    Logger.log(f"Installing Torch for {vendor}...", "info")
    run_cmd(cmd, env=env)

def task_create_launchers(comfy_path, bin_dir):
    """Creates the batch/sh file to launch ComfyUI."""
    l_name = "run_comfyui.bat" if IS_WIN else "run_comfyui.sh"
    launcher_path = comfy_path / l_name
    venv_python = comfy_path / "venv" / bin_dir / ("python.exe" if IS_WIN else "python")
    
    args = "--enable-manager --preview-method auto"
    if IS_WIN:
        content = f"@echo off\ntitle DaSiWa ComfyUI\ncd /d \"%~dp0\"\nstart http://127.0.0.1:8188\n\"{venv_python}\" main.py {args}\npause"
    else:
        content = f"#!/bin/bash\ncd \"$(dirname \"\$0\")\"\n(sleep 5 && xdg-open http://127.0.0.1:8188) &\n\"{venv_python}\" main.py {args}"
    
    launcher_path.write_text(content)
    if not IS_WIN: os.chmod(launcher_path, 0o755)
    Logger.log(f"Launcher created at {launcher_path}", "ok")

# Ensures 'utils' is findable regardless of where the script is called from
SCRIPT_ROOT = Path(__file__).parent.absolute()
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.append(str(SCRIPT_ROOT))

# --- MAIN ENGINE ---
def main():
    start_time = time.time()
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", default="main", help="Installer branch")
    args = parser.parse_args()

    ensure_dependencies()
    hw = get_gpu_report(IS_WIN, Logger)
    
    # Define paths
    base_path = Path.cwd()
    comfy_path = base_path / "ComfyUI"

    # 1. Sync Repository
    if not comfy_path.exists():
        Logger.log("Cloning ComfyUI...", "info")
        run_cmd(["git", "clone", "https://github.com/comfyanonymous/ComfyUI", str(comfy_path)])
    
    os.chdir(comfy_path)

    # 2. Environment Setup
    Logger.log("Setting up Virtual Environment (UV)...", "info")
    run_cmd(["uv", "venv", "venv", "--python", TARGET_PYTHON_VERSION, "--clear"])
    venv_env, bin_dir = get_venv_env(comfy_path)

    # 3. Installation Steps
    node_results = None  # Initialize so Reporter doesn't crash if install fails early
    
    try:
        # A. Install Core Engine
        install_torch(venv_env, hw)
        
        Logger.log("Installing ComfyUI base requirements...", "info")
        run_cmd(["uv", "pip", "install", "-r", "requirements.txt"], env=venv_env)
        
        # B. Install Stability Fixes
        Logger.log("Installing stability packages...", "info")
        run_cmd(["uv", "pip", "install"] + PRIORITY_PACKAGES, env=venv_env)
        
        # C. Install Custom Nodes and capture the stats
        node_results = task_custom_nodes(venv_env, NODES_LIST_URL, NODES_LIST_FILE, run_cmd)
        
    except Exception as e:
        Logger.error(f"Critical installation step failed: {e}")
        # We don't exit here; we proceed to try and create the launcher anyway

    # 4. Finalize
    # Create the launcher first
    task_create_launchers(comfy_path, bin_dir)
    
    # Show the summary ONCE with all gathered data
    Reporter.show_summary(hw, venv_env, start_time, node_stats=node_results)
    
    Logger.success("Process Finished!")

if __name__ == "__main__":
    main()