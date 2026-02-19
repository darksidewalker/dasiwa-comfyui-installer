import urllib.request
import subprocess
import sys
import os
import json
from pathlib import Path
from utils.logger import Logger

# --- CONFIGURATION ---
REPO_OWNER = "darksidewalker"
REPO_NAME = "dasiwa-comfyui-installer"
LAUNCHER_FILE = sys.argv[0]  # The name of this script
LOGIC_FILE = "setup_logic.py"
HASH_STORAGE = ".version_hash"

# GitHub Raw URLs
BASE_RAW_URL = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main"
REMOTE_LAUNCHER_URL = f"{BASE_RAW_URL}/{os.path.basename(LAUNCHER_FILE)}"
REMOTE_LOGIC_URL = f"{BASE_RAW_URL}/{LOGIC_FILE}"

def get_remote_hash(filename):
    """Fetches the unique commit SHA for a specific file from GitHub API."""
    api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits?path={filename}&page=1&per_page=1"
    try:
        req = urllib.request.Request(api_url, headers={'User-Agent': 'Python-Installer'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            return data[0]['sha']
    except Exception:
        return None

def main():
    Logger.init()
    Logger.log("DaSiWa ComfyUI Launcher", "info", bold=True)
    
    # 1. Self-Update Check (Launcher)
    launcher_name = os.path.basename(LAUNCHER_FILE)
    remote_launcher_hash = get_remote_hash(launcher_name)
    local_launcher_hash_file = f".{launcher_name}.hash"
    local_launcher_hash = Path(local_launcher_hash_file).read_text().strip() if Path(local_launcher_hash_file).exists() else ""

    if remote_launcher_hash and remote_launcher_hash != local_launcher_hash:
        Logger.log(f"New Launcher version found ({remote_launcher_hash[:8]}). Self-updating...", "warn")
        try:
            urllib.request.urlretrieve(REMOTE_LAUNCHER_URL, LAUNCHER_FILE)
            Path(local_launcher_hash_file).write_text(remote_launcher_hash)
            Logger.log("Launcher updated. Restarting...", "ok")
            # Re-run the script and exit this process
            os.execv(sys.executable, ['python'] + sys.argv)
        except Exception as e:
            Logger.error(f"Self-update failed: {e}")

    # 2. Update Check (Setup Logic)
    remote_logic_hash = get_remote_hash(LOGIC_FILE)
    local_logic_hash = Path(HASH_STORAGE).read_text().strip() if Path(HASH_STORAGE).exists() else ""
    
    if remote_logic_hash and (remote_logic_hash != local_logic_hash or not Path(LOGIC_FILE).exists()):
        Logger.log(f"New Logic detected ({remote_logic_hash[:8]}). Updating...", "info")
        try:
            urllib.request.urlretrieve(REMOTE_LOGIC_URL, LOGIC_FILE)
            Path(HASH_STORAGE).write_text(remote_logic_hash)
            Logger.log("Core logic synchronized.", "ok")
        except Exception as e:
            Logger.log(f"Logic update failed, using local: {e}", "fail")

    # 3. Execution
    success = False
    try:
        # We don't use Logger here because setup_logic.py has its own Logger calls
        subprocess.run([sys.executable, LOGIC_FILE], check=True)
        success = True
    except Exception as e:
        Logger.error(f"Error during installation: {e}")

    # 4. Final Launch Prompt
    if success:
        print("\n" + "="*40)
        Logger.log("ComfyUI installation/repair complete.", "done", bold=True)
        print("="*40)
        
        choice = input(f"\n{Logger.CYAN}[?]{Logger.END} Launch now? [Y/n]: ").strip().lower()
        
        if choice in ('y', ''):
            if Path.cwd().name != "ComfyUI":
                comfy_path = Path.cwd() / "ComfyUI"
                if comfy_path.exists():
                    os.chdir(comfy_path)
            
            l = "run_comfyui.bat" if os.name == 'nt' else "./run_comfyui.sh"
            
            if not Path(l).exists():
                Logger.error(f"Launcher {l} not found in {Path.cwd()}")
                return

            Logger.log(f"Launching {l}...", "info")
            
            if os.name == 'nt':
                subprocess.Popen([l], creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                subprocess.Popen(["/bin/bash", l], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            Logger.log("ComfyUI started in the background. You can close this window.", "ok")

if __name__ == "__main__":
    main()