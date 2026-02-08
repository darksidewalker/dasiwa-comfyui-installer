import urllib.request
import subprocess
import sys
import os
import json
from pathlib import Path

# --- CONFIGURATION ---
REPO_OWNER = "darksidewalker"
REPO_NAME = "dasiwa-comfyui-installer"
LOGIC_FILE = "setup_logic.py"
REMOTE_URL = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/{LOGIC_FILE}"
HASH_STORAGE = ".version_hash"

def get_remote_hash():
    """Fetches the unique commit SHA from GitHub API."""
    api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits?path={LOGIC_FILE}&page=1&per_page=1"
    try:
        req = urllib.request.Request(api_url, headers={'User-Agent': 'Python-Installer'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            return data[0]['sha']
    except Exception as e:
        print(f"[!] Update check skipped (API Offline or Rate-Limited).")
        return None

def main():
    print(f"--- DaSiWa ComfyUI Stand-alone Installer (Hash-Aware) ---")
    
    # 1. Path Safety
    if Path.cwd().name == "dasiwa-comfyui-installer":
        os.chdir("..")

    # 2. Update Check
    remote_hash = get_remote_hash()
    local_hash = Path(HASH_STORAGE).read_text().strip() if Path(HASH_STORAGE).exists() else ""
    
    if remote_hash and (remote_hash != local_hash or not Path(LOGIC_FILE).exists()):
        print(f"[*] New version detected ({remote_hash[:8]}). Updating...")
        try:
            urllib.request.urlretrieve(REMOTE_URL, LOGIC_FILE)
            Path(HASH_STORAGE).write_text(remote_hash)
        except Exception as e:
            print(f"[-] Update failed, using local version: {e}")

    # 3. Execution
    success = False
    try:
        subprocess.run([sys.executable, LOGIC_FILE], check=True)
        success = True
    except Exception as e:
        print(f"\n[!] Error during installation: {e}")

# 4. Final Launch Prompt
    if success:
        print("\n" + "="*40 + "\nDONE! ComfyUI is installed.\n" + "="*40)
        
        # Adding [Y/n] indicates Y is the default
        choice = input("\nLaunch now? [Y/n]: ").strip().lower()
        
        # If choice is 'y' OR the user just pressed Enter (empty string)
        if choice in ('y', ''):
            
            # --- FIXED PATH LOGIC ---
            if Path.cwd().name != "ComfyUI":
                comfy_path = Path.cwd() / "ComfyUI"
                if comfy_path.exists():
                    os.chdir(comfy_path)
            
            l = "run_comfyui.bat" if os.name == 'nt' else "./run_comfyui.sh"
            
            if not Path(l).exists():
                print(f"[!] Launcher {l} not found in {Path.cwd()}")
                return

            print(f"[*] Launching {l}...")
            
            if os.name == 'nt':
                # Opens in a new command window
                subprocess.Popen([l], creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                # 'nohup' or setsid ensures ComfyUI stays open even if the setup terminal is closed
                # We use the full path to bash to ensure shell scripts execute correctly
                subprocess.Popen(["/bin/bash", l], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            print("[*] ComfyUI started in the background. You can close this window.")

if __name__ == "__main__":
    main()
