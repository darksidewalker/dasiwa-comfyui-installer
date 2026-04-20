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
REPO_BRANCH = "main"
LOGIC_FILE = "setup_logic.py"
HASH_STORAGE = ".version_hash"

LAUNCHER_PATH = Path(sys.argv[0])
LAUNCHER_NAME = LAUNCHER_PATH.name

BASE_RAW_URL = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{REPO_BRANCH}"
REMOTE_LOGIC_URL = f"{BASE_RAW_URL}/{LOGIC_FILE}"
REMOTE_LAUNCHER_URL = f"{BASE_RAW_URL}/{LAUNCHER_NAME}"


def get_remote_hash(filename):
    """Fetch the commit SHA of the last change to `filename` on REPO_BRANCH."""
    api_url = (f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
               f"/commits?sha={REPO_BRANCH}&path={filename}&page=1&per_page=1")
    try:
        req = urllib.request.Request(api_url, headers={'User-Agent': 'DaSiWa-Installer'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data:
                return data[0]['sha']
    except Exception:
        pass
    return None


def _atomic_download(url, dest):
    """Download to <dest>.new, then atomically rename over <dest>."""
    tmp = dest.with_suffix(dest.suffix + ".new")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(dest)  # atomic on POSIX and on Windows for same-volume renames


def main():
    Logger.init()
    Logger.banner("DaSiWa ComfyUI Launcher", f"branch: {REPO_BRANCH}")

    # 1. Self-update (launcher)
    remote_launcher_hash = get_remote_hash(LAUNCHER_NAME)
    local_launcher_hash_file = Path(f".{LAUNCHER_NAME}.hash")
    local_launcher_hash = (
        local_launcher_hash_file.read_text().strip()
        if local_launcher_hash_file.exists() else ""
    )

    if remote_launcher_hash and remote_launcher_hash != local_launcher_hash:
        Logger.log(f"New launcher version ({remote_launcher_hash[:8]}). Self-updating...",
                   "warn")
        try:
            _atomic_download(REMOTE_LAUNCHER_URL, LAUNCHER_PATH)
            local_launcher_hash_file.write_text(remote_launcher_hash)
            Logger.log("Launcher updated. Restarting...", "ok")
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            Logger.error(f"Self-update failed: {e}")

    # 2. Logic update
    remote_logic_hash = get_remote_hash(LOGIC_FILE)
    local_logic_hash = (
        Path(HASH_STORAGE).read_text().strip() if Path(HASH_STORAGE).exists() else ""
    )

    if remote_logic_hash and (
        remote_logic_hash != local_logic_hash or not Path(LOGIC_FILE).exists()
    ):
        Logger.log(f"New logic detected ({remote_logic_hash[:8]}). Updating...", "info")
        try:
            _atomic_download(REMOTE_LOGIC_URL, Path(LOGIC_FILE))
            Path(HASH_STORAGE).write_text(remote_logic_hash)
            Logger.log("Core logic synchronized.", "ok")
        except Exception as e:
            Logger.log(f"Logic update failed, using local: {e}", "fail")

    # 3. Execute
    try:
        subprocess.run([sys.executable, LOGIC_FILE, "--branch", "master"])
    except Exception as e:
        Logger.error(f"\n[!] Error during installation: {e}")


if __name__ == "__main__":
    main()
