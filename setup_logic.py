import subprocess
import os
import sys
import platform
import urllib.request
import shutil
from pathlib import Path

# --- CONFIGURATION ---
VERSION = 3.1
TARGET_PYTHON_VERSION = "3.12.10"
GLOBAL_CUDA_VERSION = "13.0"
MIN_CUDA_FOR_50XX = "12.8"
NODES_LIST_URL = "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/custom_nodes.txt"
NODES_LIST_FILE = "custom_nodes.txt"

IS_WIN = platform.system() == "Windows"

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
            res = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True)
            if "RTX 50" in res.stdout:
                target_cu = MIN_CUDA_FOR_50XX
                is_nightly = True
        except: pass

    cmd = ["uv", "pip", "install"]
    if is_nightly: cmd += ["--pre"]
    cmd += ["torch", "torchvision", "torchaudio"]
    
    base_url = "https://download.pytorch.org/whl/"
    if vendor == "NVIDIA": cmd += ["--extra-index-url", f"{base_url}cu{target_cu.replace('.', '')}"]
    elif vendor == "AMD": cmd += ["--index-url", f"{base_url}rocm6.2"]
    elif vendor == "INTEL": cmd += ["--index-url", f"{base_url}xpu"]
    
    print(f"[*] Installing Torch for {vendor}...")
    run_cmd(cmd, env=env)

def task_custom_nodes(env):
    os.makedirs("custom_nodes", exist_ok=True)
    print("[*] Updating Custom Nodes...")
    try:
        urllib.request.urlretrieve(NODES_LIST_URL, NODES_LIST_FILE)
        with open(NODES_LIST_FILE, "r") as f:
            repos = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        for repo in repos:
            name = repo.split("/")[-1].replace(".git", "")
            node_dir = Path("custom_nodes") / name
            
            if node_dir.exists() and not (node_dir / "__init__.py").exists() and not (node_dir / "setup.py").exists():
                shutil.rmtree(node_dir)
            
            if not node_dir.exists():
                run_cmd(["git", "clone", "--recursive", repo, str(node_dir)])
            else:
                subprocess.run(["git", "-C", str(node_dir), "pull"], check=False, capture_output=True)

            if (node_dir / "requirements.txt").exists():
                run_cmd(["uv", "pip", "install", "-r", str(node_dir / "requirements.txt")], env=env)
            if (node_dir / "setup.py").exists() or (node_dir / "pyproject.toml").exists():
                run_cmd(["uv", "pip", "install", "-e", str(node_dir)], env=env)
        os.remove(NODES_LIST_FILE)
    except Exception as e: print(f"[!] Node error: {e}")

def task_create_launchers(bin_dir):
    l_name = "run_comfyui.bat" if IS_WIN else "run_comfyui.sh"
    cmd_str = f".\\venv\\{bin_dir}\\python.exe" if IS_WIN else f"./venv/{bin_dir}/python"
    args = "--enable-manager --front-end-version Comfy-Org/ComfyUI_frontend@latest"
    if IS_WIN:
        content = f"@echo off\ntitle ComfyUI\nstart http://127.0.0.1:8188\n\"{cmd_str}\" main.py {args}\npause"
    else:
        content = f"#!/bin/bash\n(sleep 5 && xdg-open http://127.0.0.1:8188) &\n{cmd_str} main.py {args}"
    Path(l_name).write_text(content)
    if not IS_WIN: os.chmod(l_name, 0o755)

# --- MAIN ---
def main():
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

    print(f"=== DaSiWa ComfyUI Installer v{VERSION} ===")
    base_path = Path.cwd().resolve()
    target_input = input(f"Target path (Default {base_path}): ").strip()
    install_base = Path(target_input) if target_input else base_path
    comfy_path = install_base / "ComfyUI"

    mode = "install"
    if comfy_path.exists():
        c = input(f"\n[!] Folder exists. [U]pdate / [O]verwrite / [A]bort: ").strip().lower()
        if c == 'o':
            shutil.rmtree(comfy_path)
        elif c == 'u':
            mode = "update"
        else: sys.exit(0)

    os.makedirs(install_base, exist_ok=True)
    os.chdir(install_base)

    if mode == "install":
        print("[*] Performing fresh clone...")
        run_cmd(["git", "clone", "https://github.com/comfyanonymous/ComfyUI"])
        os.chdir("ComfyUI")
    else:
        print("[*] Updating existing installation...")
        os.chdir("ComfyUI")
        run_cmd(["git", "remote", "set-url", "origin", "https://github.com/comfyanonymous/ComfyUI"])
        run_cmd(["git", "fetch", "--all", "--quiet"])
        try:
            subprocess.run(["git", "reset", "--hard", "origin/main"], check=True, capture_output=True)
        except:
            run_cmd(["git", "reset", "--hard", "origin/master"])

    print("[*] Setting up environment...")
    try: subprocess.run(["uv", "--version"], capture_output=True, check=True)
    except:
        if IS_WIN: run_cmd("powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\"", shell=True)
        else: run_cmd("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
        os.environ["PATH"] += os.pathsep + os.path.expanduser("~/.cargo/bin")

    run_cmd(["uv", "venv", "venv", "--python", TARGET_PYTHON_VERSION, "--clear"])
    venv_env, bin_name = get_venv_env()
    
    install_torch(venv_env)
    run_cmd(["uv", "pip", "install", "-r", "requirements.txt"], env=venv_env)
    task_custom_nodes(venv_env)
    task_create_launchers(bin_name)

    print("\n" + "="*30 + "\nINSTALLATION COMPLETE\n" + "="*30)

if __name__ == "__main__":
    main()
