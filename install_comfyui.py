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
REPO_BRANCH = "testing"  # The branch we are targeting
LOGIC_FILE = "setup_logic.py"
HASH_STORAGE = ".version_hash"

# Dynamically find the name of THIS script for self-updates
LAUNCHER_PATH = Path(sys.argv[0])
LAUNCHER_NAME = LAUNCHER_PATH.name

# GitHub Raw URLs (Branch-specific)
BASE_RAW_URL = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{REPO_BRANCH}"
REMOTE_LOGIC_URL = f"{BASE_RAW_URL}/{LOGIC_FILE}"
REMOTE_LAUNCHER_URL = f"{BASE_RAW_URL}/{LAUNCHER_NAME}"

def get_remote_hash(filename):
    """Fetches the unique commit SHA for a specific file from the targeted branch."""
    # Added ?sha=REPO_BRANCH so the API looks at the testing branch
    api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits?sha={REPO_BRANCH}&path={filename}&page=1&per_page=1"
    try:
        req = urllib.request.Request(api_url, headers={'User-Agent': 'Python-Installer'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            return data[0]['sha']
    except Exception:
        return None

def main():
    Logger.init()
    Logger.log(f"DaSiWa ComfyUI Launcher ({REPO_BRANCH})", "info", bold=True)
    
    # 1. Self-Update Check (Launcher updates itself)
    remote_launcher_hash = get_remote_hash(LAUNCHER_NAME)
    local_launcher_hash_file = f".{LAUNCHER_NAME}.hash"
    local_launcher_hash = Path(local_launcher_hash_file).read_text().strip() if Path(local_launcher_hash_file).exists() else ""

    if remote_launcher_hash and remote_launcher_hash != local_launcher_hash:
        Logger.log(f"New Launcher version found ({remote_launcher_hash[:8]}). Self-updating...", "warn")
        try:
            urllib.request.urlretrieve(REMOTE_LAUNCHER_URL, LAUNCHER_PATH)
            Path(local_launcher_hash_file).write_text(remote_launcher_hash)
            Logger.log("Launcher updated. Restarting...", "ok")
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            Logger.error(f"Self-update failed: {e}")

    # 2. Update Check (Download the Logic Script)
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

    # 3. Execution (Hand off control to setup_logic.py)
    try:
        # We pass the branch name as an argument so setup_logic knows which branch to clone
        subprocess.run([sys.executable, LOGIC_FILE, "--branch", REPO_BRANCH], check=True)
    except Exception as e:
        Logger.error(f"\n[!] Error during installation: {e}")

if __name__ == "__main__":
    main()