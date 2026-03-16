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
from utils.downloader import Downloader

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
NODES_LIST_URL = CONFIG["urls"]["custom_nodes"]
NODES_LIST_FILE = "custom_nodes.txt"

PRIORITY_PACKAGES = [
    "torch", 
    "torchvision", 
    "torchaudio",
    "numpy>=2.1.0,<=2.3.0", 
    "pillow>=11.0.0", 
    "pydantic>=2.12.5",
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
    """Creates the startup scripts for Linux and Windows."""
    # Use paths relative to the ComfyUI folder
    if os.name == "nt":
        venv_python = r"venv\Scripts\python.exe"
        args = "--enable-manager --preview-method auto"
        content = f'@echo off\ncd /d "%~dp0"\nstart http://127.0.0.1:8188\n"{venv_python}" main.py {args}\npause'
        launcher_path = comfy_path / "run_comfyui.bat"
    else:
        # For Linux, use venv/bin/python3
        venv_python = "./venv/bin/python3"
        args = "--enable-manager --preview-method auto"
        content = f"""#!/bin/bash
cd "$(dirname "$0")"
(sleep 5 && xdg-open http://127.0.0.1:8188) &
"{venv_python}" main.py {args}
"""
        launcher_path = comfy_path / "run_comfyui.sh"

    with open(launcher_path, "w", newline='\n') as f:
        f.write(content)
    
    if os.name != "nt":
        os.chmod(launcher_path, 0o755)
    
    Logger.log(f"Launcher created at: {launcher_path}", "ok")

# Ensures 'utils' is findable regardless of where the script is called from
SCRIPT_ROOT = Path(__file__).parent.absolute()
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.append(str(SCRIPT_ROOT))

# --- MAIN ENGINE ---
def main():
    start_time = time.time()
    
    # 1. Define anchor paths at the very top to prevent NameErrors
    CURRENT_RUN_DIR = Path.cwd().absolute()
    CONFIG_PATH = CURRENT_RUN_DIR / "config.json"

    # Handle arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", default="main", help="Installer branch")
    args = parser.parse_args()

    # Pre-flight checks
    ensure_dependencies()
    hw = get_gpu_report(IS_WIN, Logger)

    # 2. Load Config with Absolute Path
    if not CONFIG_PATH.exists():
        Logger.error(f"Critical Error: config.json not found at {CONFIG_PATH}")
        return
    
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config_data = json.load(f)

    # 3. ComfyUI Repository Setup
    comfy_path = CURRENT_RUN_DIR / "ComfyUI"
    if not comfy_path.exists():
        Logger.log(f"Cloning ComfyUI into {comfy_path}...", "info")
        run_cmd(["git", "clone", "https://github.com/comfyanonymous/ComfyUI", str(comfy_path)])
    
    # 4. Environment Setup
    Logger.log("Setting up Virtual Environment (UV)...", "info")
    # Using 'uv' to manage the venv and requirements
    run_cmd(["uv", "venv", str(comfy_path / "venv"), "--python", TARGET_PYTHON_VERSION, "--clear"])
    venv_env, bin_dir = get_venv_env(comfy_path)

    # 5. Model/Workflow Management
    # We run the Downloader before changing directories to keep paths relative to root
    if "optional_downloads" in config_data:
        Downloader.show_cli_menu(config_data["optional_downloads"], comfy_path)

    # 6. Core Installation & Custom Nodes
    # Move into ComfyUI folder to run pip and git commands locally
    os.chdir(comfy_path)
    node_stats = None 

    try:
        # A. Install Hardware-specific Torch
        install_torch(venv_env, hw)
        
        # B. Install Base Requirements
        Logger.log("Installing core ComfyUI requirements...", "info")
        run_cmd(["uv", "pip", "install", "-r", "requirements.txt"], env=venv_env)
        
        # C. Synchronize Custom Nodes
        Logger.log("Synchronizing Custom Nodes...", "info")
        node_stats = task_custom_nodes(
            venv_env, 
            NODES_LIST_URL, 
            NODES_LIST_FILE, 
            run_cmd, 
            comfy_path
        )

    except Exception as e:
        Logger.error(f"Installation process failed: {e}")

    # 7. Finalize & Cleanup
    # Crucial: Return to the original directory so launchers are created in the right spot
    os.chdir(CURRENT_RUN_DIR)
    
    task_create_launchers(comfy_path, bin_dir)
    
    # Provide the final report using the collected stats
    Reporter.show_summary(hw, venv_env, start_time, node_stats=node_stats)
    
    Logger.success("Process Finished!")
    input("\nPress Enter to exit...")