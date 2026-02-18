import subprocess
import os
import sys
import platform
import urllib.request
import shutil
from pathlib import Path
import time
from datetime import datetime
#from utils.logger import Logger #not implemented yet

# --- CONFIGURATION ---
# Versioning is now handled automatically via GitHub Hash in the Bootstrap.
TARGET_PYTHON_VERSION = "3.12.10"
GLOBAL_CUDA_VERSION = "13.0"
MIN_CUDA_FOR_50XX = "12.8"
NODES_LIST_URL = "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/custom_nodes.txt"
NODES_LIST_FILE = "custom_nodes.txt"

# Stability Guard: Packages that custom nodes are NOT allowed to downgrade
PRIORITY_PACKAGES = [
    "pillow>=11.0.0",
    "pydantic>=2.10.0",
    "torch", 
    "torchvision",
    "torchaudio",
    "numpy==2.3",
]

IS_WIN = platform.system() == "Windows"

#Logger.init() # Run once at start; not implemented yet

def is_admin():
    try:
        if IS_WIN:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        return os.getuid() == 0
    except:
        return False

def run_cmd(cmd, env=None, shell=False):
    subprocess.run(cmd, check=True, env=env, shell=shell)

def get_venv_env():
    venv_path = Path.cwd() / "venv"
    full_env = os.environ.copy()
    full_env["VIRTUAL_ENV"] = str(venv_path)
    bin_dir = "Scripts" if IS_WIN else "bin"
    full_env["PATH"] = str(venv_path / bin_dir) + os.pathsep + full_env["PATH"]
    return full_env, bin_dir

# --- PREREQUISITE BOOTSTRAPS ---
def bootstrap_python():
    if not IS_WIN:
        print(f"[!] Python {TARGET_PYTHON_VERSION} missing. Please install it via your package manager.")
        sys.exit(1)
    print(f"\n[*] Downloading Python {TARGET_PYTHON_VERSION} installer...")
    url = f"https://www.python.org/ftp/python/{TARGET_PYTHON_VERSION}/python-{TARGET_PYTHON_VERSION}-amd64.exe"
    installer = Path.home() / "py_installer.exe"
    urllib.request.urlretrieve(url, installer)
    run_cmd(f'"{installer}" /quiet InstallAllUsers=1 PrependPath=1', shell=True)
    os.remove(installer)

def bootstrap_git():
    if not IS_WIN:
        print("[!] Git missing. Please install it (e.g., sudo apt install git).")
        sys.exit(1)
    print("\n[*] Downloading Git installer...")
    url = "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe"
    installer = Path.home() / "git_installer.exe"
    urllib.request.urlretrieve(url, installer)
    run_cmd(f'"{installer}" /VERYSILENT /NORESTART', shell=True)
    os.remove(installer)

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
                v_id = v_file.read_text().strip().lower()
                if "0x10de" in v_id: return "NVIDIA"
                if "0x1002" in v_id: return "AMD"
                if "0x8086" in v_id: return "INTEL"
            res = subprocess.run(["lspci"], capture_output=True, text=True)
            out = res.stdout.upper()
            if "NVIDIA" in out: return "NVIDIA"
            if "AMD" in out: return "AMD"
            if "INTEL" in out: return "INTEL"
        except: pass
    return "UNKNOWN"

# --- CORE TASKS ---
def install_torch(env):
    vendor = get_gpu_vendor()
    if vendor == "UNKNOWN":
        print("\n[?] GPU detection failed. [1] NVIDIA | [2] AMD | [3] Intel | [A] Abort")
        c = input("Choice: ").strip().upper()
        vendor = {"1":"NVIDIA", "2":"AMD", "3":"INTEL"}.get(c, "ABORT")
        if vendor == "ABORT": sys.exit(0)

    target_cu = GLOBAL_CUDA_VERSION
    is_nightly = False
    
    if vendor == "NVIDIA":
        try:
            # 1. Check GPU Name
            res_name = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True)
            gpu_name = res_name.stdout.upper()
            
            # 2. Check Driver Version
            res_drv = subprocess.run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], capture_output=True, text=True)
            driver_ver = float(res_drv.stdout.split('.')[0])

            # --- LEGACY PASCAL LOGIC ---
            # GTX 1070, 1080, 1060, etc.
            if "GTX 10" in gpu_name or "PASCAL" in gpu_name:
                print(f"[*] Detected Pascal GPU: {gpu_name.strip()}")
                if driver_ver < 525:
                    print("[!] WARNING: Your NVIDIA driver is very old. Please update to 530+ for CUDA 12 support.")
                
                # CUDA 12.1 is the most compatible 'modern' target for Pascal kernels
                target_cu = "12.1"
            
            # --- 50-SERIES LOGIC ---
            elif "RTX 50" in gpu_name:
                target_cu = MIN_CUDA_FOR_50XX
                is_nightly = True
                
        except Exception as e:
            print(f"[*] Hardware detail check skipped: {e}")

    # Build the install command
    cmd = ["uv", "pip", "install"]
    if is_nightly: cmd += ["--pre"]
    
    # We force specific versions if on Pascal to ensure the kernels match
    if target_cu == "12.1":
        cmd += ["torch==2.4.1", "torchvision==0.19.1", "torchaudio==2.4.1"]
    else:
        cmd += ["torch", "torchvision", "torchaudio"]
    
    base_url = "https://download.pytorch.org/whl/"
    if vendor == "NVIDIA": 
        cu_tag = f"cu{target_cu.replace('.', '')}"
        cmd += ["--extra-index-url", f"{base_url}{cu_tag}"]
    elif vendor == "AMD": 
        cmd += ["--index-url", f"{base_url}rocm6.2"]
    elif vendor == "INTEL": 
        cmd += ["--index-url", f"{base_url}xpu"]
    
    print(f"[*] Installing Torch ({target_cu}) for {vendor}...")
    run_cmd(cmd, env=env)

def install_manager(env):
    print("[*] Installing/Updating ComfyUI-Manager (Package Mode)...")
    # Using --pre as requested by the Manager's own warning
    run_cmd(["uv", "pip", "install", "--pre", "comfyui_manager"], env=env)

def task_check_ffmpeg(venv_env=None):
    print("[*] Checking for FFmpeg...", flush=True)
    
    # 0. Check if it's already in the PATH
    if shutil.which("ffmpeg"):
        print("[+] FFmpeg is already installed.", flush=True)
        return

    # 1. First Attempt: System-wide via Winget (Windows only)
    if IS_WIN:
        try:
            print("[*] FFmpeg missing. Attempt 1: Installing system-wide via winget...", flush=True)
            # Use 'ffmpeg' as the ID for a broader search, with agreement bypass
            subprocess.run([
                "winget", "install", "ffmpeg", 
                "--accept-source-agreements", 
                "--accept-package-agreements"
            ], check=True, capture_output=True)
            print("[+] Winget installation successful.")
            return
        except Exception as e:
            print(f"[!] Winget attempt failed. Moving to failsafe...", flush=True)

    # 2. Second Attempt (Failsafe): Portable install via uv
    if venv_env:
        try:
            print("[*] Attempt 2: Installing portable FFmpeg via uv...", flush=True)
            # static-ffmpeg installs binaries directly into the venv
            subprocess.run(["uv", "pip", "install", "static-ffmpeg"], env=venv_env, check=True)
            print("[+] Portable FFmpeg installed successfully inside venv.", flush=True)
            return
        except Exception as e:
            print(f"[-] Portable install failed: {e}", flush=True)

    # 3. Final Fallback: Manual Instructions (Linux/Fallback)
    if not IS_WIN:
        managers = {
            "apt": "sudo apt update && sudo apt install ffmpeg -y",
            "dnf": "sudo dnf install ffmpeg -y",
            "pacman": "sudo pacman -S ffmpeg --noconfirm"
        }
        for mgr, install_script in managers.items():
            if shutil.which(mgr):
                print(f"[!] FFmpeg missing. Please run: {install_script}", flush=True)
                return
    
    print("[!] Critical: FFmpeg could not be installed automatically. Please install it manually.", flush=True)

def task_custom_nodes(env):
    os.makedirs("custom_nodes", exist_ok=True)
    
    # --- 1. OFFICIAL COMFYUI-MANAGER INSTALL (METHOD 1) ---
    manager_dir = Path("custom_nodes") / "comfyui-manager"
    
    # 1. Force remove any "fake" or "pip-style" manager folders
    if manager_dir.exists():
        # If it doesn't have a .git folder, it's not a real clone
        if not (manager_dir / ".git").exists():
            print("[!] Invalid Manager folder detected (likely Pip-style). Wiping for Git clone...")
            shutil.rmtree(manager_dir)

    # 2. Re-clone or Update using official Method 1
    if not manager_dir.exists():
        print("[*] Cloning official ComfyUI-Manager...")
        run_cmd(["git", "clone", "https://github.com/ltdrdata/ComfyUI-Manager", str(manager_dir)])
    else:
        print("[*] Updating ComfyUI-Manager...")
        # Force remove the CLI-only flag if it exists (prevents hidden UI)
        cli_flag = manager_dir / ".enable-cli-only-mode"
        if cli_flag.exists(): cli_flag.unlink()
        subprocess.run(["git", "-C", str(manager_dir), "pull"], check=False)

    # 3. Cleanup: Uninstall Pip version & fix casing conflicts
    try:
        run_cmd(["uv", "pip", "uninstall", "comfyui_manager"], env=env)
    except:
        pass

    wrong_case = Path("custom_nodes") / "ComfyUI-Manager"
    if wrong_case.exists() and wrong_case.resolve() != manager_dir.resolve():
        print(f"[!] Removing conflicting casing folder: {wrong_case}")
        shutil.rmtree(wrong_case)

    # 4. Install requirements (using the modern replacement for pynvml)
    print("[*] Ensuring Manager dependencies...")
    run_cmd(["uv", "pip", "install", "matrix-client", "nvidia-ml-py", "GitPython"], env=env)

    # --- 2. DYNAMIC CUSTOM NODES LIST ---
    print("\n=== Updating Custom Nodes List ===")
    try:
        urllib.request.urlretrieve(NODES_LIST_URL, NODES_LIST_FILE)
        with open(NODES_LIST_FILE, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        
        for line in lines:
            parts = [p.strip() for p in line.split("|")]
            repo_url = parts[0]
            
            # Skip Manager if it's in the text file (we already handled it above)
            if "ComfyUI-Manager" in repo_url or "comfyui-manager" in repo_url:
                continue

            flags = [f.lower() for f in parts[1:]]
            is_package = "pkg" in flags
            needs_submodules = "sub" in flags
            
            # Preserve case sensitivity for the rest of the nodes
            name = repo_url.split("/")[-1].replace(".git", "")
            node_dir = Path("custom_nodes") / name
            
            # --- Clone/Update ---
            if not node_dir.exists():
                print(f"\n[*] Cloning: {name}")
                run_cmd(["git", "clone", "--recursive", repo_url, str(node_dir)])
            else:
                print(f"[*] Pulling: {name}")
                subprocess.run(["git", "-C", str(node_dir), "pull"], check=False)

            # --- Submodule Sync (CosyVoice & MMAudio) ---
            if needs_submodules or (node_dir / ".gitmodules").exists():
                print(f"[*] Syncing submodules for {name}...")
                for i in range(3):
                    try:
                        run_cmd(["git", "-C", str(node_dir), "submodule", "update", "--init", "--recursive"])
                        break 
                    except Exception:
                        if i == 2: print(f"[X] Failed submodules for {name}")

            # --- Editable Package & Shim (MMAudio Crash Prevention) ---
            if is_package:
                if (node_dir / "setup.py").exists() or (node_dir / "pyproject.toml").exists():
                    print(f"[*] Installing package: {name}")
                    run_cmd(["uv", "pip", "install", "-e", str(node_dir)], env=env)
                
                # Add __init__.py shim if it's a library without a node entry point
                init_file = node_dir / "__init__.py"
                if not init_file.exists():
                    init_file.write_text("NODE_CLASS_MAPPINGS = {}\nNODE_DISPLAY_NAME_MAPPINGS = {}\n")

            # --- Standard Node Requirements ---
            req_file = node_dir / "requirements.txt"
            if req_file.exists():
                run_cmd(["uv", "pip", "install", "-r", str(req_file)], env=env)
        
        if os.path.exists(NODES_LIST_FILE): 
            os.remove(NODES_LIST_FILE)
            
    except Exception as e: 
        print(f"\n[!] Critical error in task_custom_nodes: {e}")

def task_create_launchers(bin_dir):
    l_name = "run_comfyui.bat" if IS_WIN else "run_comfyui.sh"
    base_path = Path.cwd()
    venv_python = base_path / "venv" / bin_dir / ("python.exe" if IS_WIN else "python")
    
    # Standard args + stability flags
    args = "--enable-manager --front-end-version Comfy-Org/ComfyUI_frontend@latest --preview-method auto"
    
    if IS_WIN:
        content = (
            "@echo off\n"
            "title ComfyUI\n"
            # Cleanup old log to keep things fresh
            "if exist user\\comfyui.log del user\\comfyui.log\n"
            f"set VIRTUAL_ENV={base_path}\\venv\n"
            f"set PATH={base_path}\\venv\\{bin_dir};%PATH%\n"
            "start http://127.0.0.1:8188\n"
            f"\"{venv_python}\" main.py {args}\n"
            "pause"
        )
    else:
        content = (
            "#!/bin/bash\n"
            "# Move to script directory\n"
            "cd \"$(dirname \"$0\")\"\n"
            # Cleanup old log
            "rm -f user/comfyui.log\n"
            f"export VIRTUAL_ENV=\"{base_path}/venv\"\n"
            f"export PATH=\"$VIRTUAL_ENV/{bin_dir}:$PATH\"\n"
            "(sleep 5 && xdg-open http://127.0.0.1:8188) &\n"
            f"\"{venv_python}\" main.py {args}\n"
        )
        
    Path(l_name).write_text(content)
    if not IS_WIN: 
        os.chmod(l_name, 0o755)
    print(f"[*] Created stabilized launcher: {l_name}")

def remove_readonly(func, path, excinfo=None):
    """Windows-specific: Helper to force-delete read-only Git files."""
    import stat
    os.chmod(path, stat.S_IWRITE)
    func(path)

# --- MAIN ---
def main():
    # 1. System & Bootstrap Checks
    try:
        res = subprocess.run(["python", "-c", "import sys; print(sys.prefix)"], capture_output=True, text=True)
        if "WindowsApps" in res.stdout: raise Exception()
    except:
        bootstrap_python()
        sys.exit(0)

    try: subprocess.run(["git", "--version"], capture_output=True)
    except:
        bootstrap_git()
        sys.exit(0)

    # 2. Setup Paths
    build_hash = ""
    if os.path.exists(".version_hash"):
        build_hash = f" (Build: {Path('.version_hash').read_text()[:8]})"
    print(f"=== DaSiWa ComfyUI Installer{build_hash} ===")

    if IS_WIN and not is_admin():
        print("\n" + "!"*50)
        print("WARNING: Script is NOT running as Administrator.")
        print("Installation into 'C:\\Program Files' or environment")
        print("modifications may fail.")
        print("!"*50 + "\n")
        if input("Continue anyway? (y/N): ").strip().lower() != 'y':
            sys.exit(1)
    
    base_path = Path.cwd().resolve()
    target_input = input(f"Target path (Default {base_path}): ").strip()
    install_base = Path(target_input) if target_input else base_path
    comfy_path = install_base / "ComfyUI"

    mode = "install"
    
    # 3. Handle Existing Installation
    if comfy_path.exists():
        print(f"\n[!] Existing installation found at: {comfy_path}")
        print("  [U] Update    - Keep everything, just pull latest code.")
        print("  [O] Overwrite - Wipe environment/nodes, but KEEP models/outputs.")
        print("  [A] Abort     - Do nothing.")
        c = input(f"\nChoose action [U/O/A]: ").strip().lower()

        if c == 'o':
            print("[*] Performing Soft Overwrite (Preserving Models/Outputs)...")
            temp_models = install_base / "_temp_models"
            temp_output = install_base / "_temp_output"
            
            # Move data out of the line of fire
            if (comfy_path / "models").exists():
                if temp_models.exists(): shutil.rmtree(temp_models, onexc=remove_readonly)
                os.rename(comfy_path / "models", temp_models)
            if (comfy_path / "output").exists():
                if temp_output.exists(): shutil.rmtree(temp_output, onexc=remove_readonly)
                os.rename(comfy_path / "output", temp_output)
            
            # Wipe the broken parts
            shutil.rmtree(comfy_path, onexc=remove_readonly)
            
            # Re-clone the base
            os.makedirs(install_base, exist_ok=True)
            run_cmd(["git", "clone", "https://github.com/comfyanonymous/ComfyUI"], cwd=install_base)
            
            # Move data back
            if temp_models.exists():
                if (comfy_path / "models").exists(): shutil.rmtree(comfy_path / "models", onexc=remove_readonly)
                os.rename(temp_models, comfy_path / "models")
            if temp_output.exists():
                if (comfy_path / "output").exists(): shutil.rmtree(comfy_path / "output", onexc=remove_readonly)
                os.rename(temp_output, comfy_path / "output")
            
            mode = "install"
            os.chdir(comfy_path)

        elif c == 'u':
            mode = "update"
            os.chdir(comfy_path)
        else:
            sys.exit(0)
    else:
        # Fresh Install path
        os.makedirs(install_base, exist_ok=True)
        os.chdir(install_base)
        print("[*] Performing fresh clone...")
        run_cmd(["git", "clone", "https://github.com/comfyanonymous/ComfyUI"])
        os.chdir("ComfyUI")

    # 4. Core Update Logic (for 'U' mode)
    if mode == "update":
        print("[*] Updating existing installation...")
        run_cmd(["git", "remote", "set-url", "origin", "https://github.com/comfyanonymous/ComfyUI"])
        run_cmd(["git", "fetch", "--all", "--quiet"])
        try:
            subprocess.run(["git", "reset", "--hard", "origin/main"], check=True, capture_output=True)
        except:
            run_cmd(["git", "reset", "--hard", "origin/master"])

    # 5. Environment and Dependencies
    task_check_ffmpeg()

    print("[*] Checking for UV...")
    try: subprocess.run(["uv", "--version"], capture_output=True, check=True)
    except:
        if IS_WIN: run_cmd("powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\"", shell=True)
        else: run_cmd("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
        os.environ["PATH"] += os.pathsep + os.path.expanduser("~/.cargo/bin")

    print("[*] Setting up Virtual Environment...")
    run_cmd(["uv", "venv", "venv", "--python", TARGET_PYTHON_VERSION, "--clear"])
    venv_env, bin_name = get_venv_env()

    print("[*] Finalizing Pip environment...")
    run_cmd(["uv", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], env=venv_env)
    
    install_torch(venv_env)
    run_cmd(["uv", "pip", "install", "-r", "requirements.txt"], env=venv_env)
    task_custom_nodes(venv_env)

    # 6. Final Stability Sync
    print("[*] Performing Final Sync of Core Dependencies...")
    run_cmd(["uv", "pip", "install", "-r", "requirements.txt"] + PRIORITY_PACKAGES, env=venv_env)
    
    task_create_launchers(bin_name)

    print("\n" + "="*40 + "\nINSTALLATION COMPLETE\n" + "="*40)
    
    ans = input("\nLaunch ComfyUI now? [Y/n]: ").strip().lower()
    if ans in ('y', ''):
        l = "run_comfyui.bat" if IS_WIN else "./run_comfyui.sh"
        if IS_WIN:
            subprocess.Popen([l], creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen(["/bin/bash", l], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if __name__ == "__main__":
    main()
