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
from utils.comfyui_clone import sync_comfyui
from utils.task_sageattention import SageInstaller
from utils.task_ffmpeg import FFmpegInstaller

IS_WIN = platform.system() == "Windows"
Logger.init()

def load_config():
    config_file = Path.cwd() / "config.json"
    try:
        with open(config_file, "r", encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        Logger.error(f"Failed to load config.json at {config_file}: {e}")
        sys.exit(1)

CONFIG = load_config()

# --- CONSTANTS FROM CONFIG ---
TARGET_PYTHON_VERSION = CONFIG["python"].get("display_name", "3.12")
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
    "setuptools==81.0.0"

]

# --- COMMAND WRAPPERS ---
def run_cmd(cmd, env=None, **kwargs):
    """Run a command and log output, supporting flexible arguments like cwd."""
    try:
        # Pass all extra arguments (like cwd) into subprocess.run
        subprocess.run(
            cmd, 
            env=env, 
            check=True, 
            capture_output=True, 
            text=True, 
            **kwargs 
        )
    except subprocess.CalledProcessError as e:
        # Enhanced error logging for debugging builds
        Logger.error(f"Command failed: {' '.join(cmd)}")
        if e.stderr:
            Logger.log(e.stderr, "error")
        raise e

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
    # Check Python - Compare against display_name (e.g., 3.13) to allow micro-version flexibility
    current_py = platform.python_version()
    if not current_py.startswith(TARGET_PYTHON_VERSION):
        Logger.warn(f"Running on Python {current_py}, but {TARGET_PYTHON_VERSION} is preferred.")

    # Check Git
    try:
        run_cmd(["git", "--version"])
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
    
    # Respect versions from config.json
    target_cu = CONFIG.get("cuda", {}).get("global", "13.0")
    min_50xx_cu = CONFIG.get("cuda", {}).get("min_cuda_for_50xx", "12.8")
    
    is_nightly = False
    whl_url = "https://download.pytorch.org/whl/"
    cmd = ["uv", "pip", "install"]

    if vendor == "NVIDIA":
        # 1. Respect 'Manual: NVIDIA GTX 10' or Legacy cards from hardware.py
        if "GTX 10" in gpu_name or any(x in gpu_name for x in ["PASCAL", "LEGACY"]):
            target_cu = "12.1"
            
        # 2. Check for RTX 50-series (Requires 12.8+ and --pre)
        elif "RTX 50" in gpu_name:
            target_cu = min_50xx_cu
            is_nightly = True
        
        if is_nightly: cmd += ["--pre"]
        
        # Version locking for the legacy 12.1 path
        if target_cu == "12.1":
            cmd += ["torch==2.4.1", "torchvision==0.19.1", "torchaudio==2.4.1"]
        else:
            cmd += ["torch", "torchvision", "torchaudio"]
            
        cmd += ["--extra-index-url", f"{whl_url}cu{target_cu.replace('.', '')}"]

    elif vendor == "AMD":
        # Supports the ROCm 6.2/7.1 labels from hardware.py
        if any(x in gpu_name for x in ["GFX110", "RX 7000"]):
            cmd += ["--pre", "torch", "torchvision", "torchaudio", "--index-url", "https://rocm.nightlies.amd.com/v2/gfx110X-all/"]
        elif any(x in gpu_name for x in ["GFX1151", "STRIX"]):
            cmd += ["--pre", "torch", "torchvision", "torchaudio", "--index-url", "https://rocm.nightlies.amd.com/v2/gfx1151/"]
        elif any(x in gpu_name for x in ["GFX120", "RX 9000"]):
            cmd += ["--pre", "torch", "torchvision", "torchaudio", "--index-url", "https://rocm.nightlies.amd.com/v2/gfx120X-all/"]
        else:
            # Fallback to standard ROCm 7.1 stable
            cmd += ["torch", "torchvision", "torchaudio", "--index-url", f"{whl_url}rocm7.1"]

    elif vendor == "INTEL":
        # Respects 'Manual: INTEL' or 'Arc' detection
        cmd += ["torch", "torchvision", "torchaudio", "--index-url", f"{whl_url}xpu"]
    
    Logger.log(f"Installing Torch for {vendor} ({gpu_name}) using Config v{target_cu}...", "info")
    run_cmd(cmd, env=env)

def task_create_launchers(comfy_path, bin_dir):
    """Creates startup scripts with FFmpeg path injection for portability."""
    ffmpeg_bin = comfy_path / "ffmpeg" / "bin"
    has_local_ffmpeg = ffmpeg_bin.exists()

    if os.name == "nt":
        venv_python = r"venv\Scripts\python.exe"
        args = "--enable-manager --preview-method auto"
        
        # Windows Injection: Use %~dp0 to stay relative to the launcher
        path_injection = "set PATH=%~dp0ffmpeg\\bin;%PATH%\n" if has_local_ffmpeg else ""
        
        content = (
            f"@echo off\n"
            f'cd /d "%~dp0"\n'
            f"{path_injection}"
            f"start http://127.0.0.1:8188\n"
            f'"{venv_python}" main.py {args}\n'
            f"pause"
        )
        launcher_path = comfy_path / "run_comfyui.bat"
    else:
        # Linux: Apt install is global, but we include an export check for consistency
        venv_python = "./venv/bin/python3"
        args = "--enable-manager --preview-method auto"
        content = (
            f"#!/bin/bash\n"
            f'cd "$(dirname "$0")"\n'
            f'(sleep 5 && xdg-open http://127.0.0.1:8188) &\n'
            f'"{venv_python}" main.py {args}\n'
        )
        launcher_path = comfy_path / "run_comfyui.sh"

    with open(launcher_path, "w", newline='\n') as f:
        f.write(content)
    
    if os.name != "nt":
        os.chmod(launcher_path, 0o755)
    
    Logger.log(f"Launcher created: {launcher_path}", "ok")

# Ensures 'utils' is findable regardless of where the script is called from
SCRIPT_ROOT = Path(__file__).parent.absolute()
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.append(str(SCRIPT_ROOT))

# --- MAIN ENGINE ---
def main():
    start_time = time.time()
    
    # 1. Define anchor paths
    CURRENT_RUN_DIR = Path.cwd().absolute()
    CONFIG_PATH = CURRENT_RUN_DIR / "config.json"
    LOCAL_CONFIG_PATH = CURRENT_RUN_DIR / "config.local.json"
    LOCAL_NODES_PATH = CURRENT_RUN_DIR / "custom_nodes.local.txt"

    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", default="master", help="Branch of ComfyUI to clone")
    args = parser.parse_args()

    # Pre-flight: Git and Version checks
    ensure_dependencies()
    hw = get_gpu_report(IS_WIN, Logger)
    
    # 2. Load Base Config
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config_data = json.load(f)

    # 3. Handle Local Overrides (Config & Nodes)
    # --- Config Override (Deep Merge) ---
    if LOCAL_CONFIG_PATH.exists():
        Logger.log("Applying local configuration overrides...", "magenta")
        try:
            with open(LOCAL_CONFIG_PATH, 'r', encoding='utf-8') as f:
                local_data = json.load(f)
            
            # Deep merge logic for nested dictionaries
            for section in ["python", "comfyui", "cuda", "urls"]:
                if section in local_data and isinstance(local_data[section], dict):
                    config_data.setdefault(section, {}).update(local_data[section])
                elif section in local_data:
                    config_data[section] = local_data[section]
        except Exception as e:
            Logger.warn(f"Failed to parse config.local.json: {e}. Using defaults.")

    # --- Node Override Logic ---
    if LOCAL_NODES_PATH.exists():
        Logger.log("Manual Override: Using custom_nodes.local.txt", "magenta")
        final_nodes_source = str(LOCAL_NODES_PATH)
    else:
        # Fallback to the URL in config.json (or local override)
        final_nodes_source = config_data.get("urls", {}).get("custom_nodes", NODES_LIST_URL)

    # --- VERSION LOGIC: The "Latest is Master" Bridge ---
    comfy_prefs = config_data.get("comfyui", {})
    raw_version = comfy_prefs.get("version", "latest")

    # If config says "latest", we explicitly target the master branch
    if raw_version.lower() == "latest":
        TARGET_VERSION = "master"
    else:
        TARGET_VERSION = raw_version

    FALLBACK_BRANCH = comfy_prefs.get("fallback_branch", args.branch)
    
    # Global assignments
    global TARGET_PYTHON_VERSION, GLOBAL_CUDA_VERSION, CONFIG
    CONFIG = config_data
    
    TARGET_PYTHON_VERSION = config_data["python"].get("display_name", "3.12")
    GLOBAL_CUDA_VERSION = config_data["cuda"].get("global", GLOBAL_CUDA_VERSION)

    # 4. ComfyUI Setup
    comfy_path = CURRENT_RUN_DIR / "ComfyUI"
    sync_comfyui(comfy_path, target_version=TARGET_VERSION, fallback_branch=FALLBACK_BRANCH)
    
    # 5. Environment Setup
    # IV handles the requirements.txt and creates a venv
    Logger.log(f"Setting up Virtual Environment (UV) with Python {TARGET_PYTHON_VERSION}...", "info")
    run_cmd(["uv", "venv", str(comfy_path / "venv"), "--python", TARGET_PYTHON_VERSION, "--clear"])
    venv_env, bin_dir = get_venv_env(comfy_path)

    # 6. Model Management
    if "optional_downloads" in config_data:
        try:
            Downloader.show_cli_menu(config_data["optional_downloads"], comfy_path)
        except Exception as e:
            Logger.error(f"Download menu encountered an error: {e}")

    # 7. Core Installation & Custom Nodes
    os.chdir(comfy_path)
    node_stats = None 
    try:
        # Hardware-specific Torch
        install_torch(venv_env, hw)
        
        # ComfyUI Core requirements using uv
        Logger.log("Installing core requirements...", "info")
        run_cmd(["uv", "pip", "install", "-r", "requirements.txt"], env=venv_env)

        # FFmpeg Task
        if input("\nInstall FFmpeg for Video Support? (y/n): ").lower() == 'y':
            FFmpegInstaller.run(comfy_path, CONFIG.get("urls", {}))

        # SageAttention
        if input("\nDo you want to build SageAttention? (y/n): ").lower() == 'y':
            SageInstaller.build_sage(venv_env, comfy_path, config_data.get("urls", {}))

        # Custom Node synchronization
        Logger.log("Synchronizing Custom Nodes...", "info")
        node_stats = task_custom_nodes(
            venv_env, 
            final_nodes_source, 
            NODES_LIST_FILE, 
            run_cmd, 
            comfy_path
        )

        # FINAL STEP: The "Enforcer"
        Logger.log("Enforcing Priority Packages & ComfyUI-Manager...", "info")
        
        # Install Manager requirements via UV
        run_cmd(["uv", "pip", "install", "-r", "manager_requirements.txt"], env=venv_env)
        
        # Apply version locks for priority packages
        run_cmd(["uv", "pip", "install", "--upgrade"] + PRIORITY_PACKAGES, env=venv_env)

    except Exception as e:
        Logger.error(f"Installation failed: {e}")

    # 8. Finalize
    os.chdir(CURRENT_RUN_DIR)
    task_create_launchers(comfy_path, bin_dir)
    
    Reporter.show_summary(hw, venv_env, start_time, node_stats=node_stats)
    Logger.success("Process Finished!")
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
