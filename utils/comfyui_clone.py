import subprocess
import os
from pathlib import Path
from utils.logger import Logger

def sync_comfyui(comfy_path, target_version="latest", fallback_branch="master"):
    """
    Syncs ComfyUI to a specific tag or the absolute latest release.
    """
    repo_url = "https://github.com/comfyanonymous/ComfyUI.git"
    comfy_path = Path(comfy_path).absolute()

    if not comfy_path.exists():
        Logger.log(f"Cloning ComfyUI...", "info")
        subprocess.run(["git", "clone", repo_url, str(comfy_path)], check=True)
    
    original_cwd = os.getcwd()
    os.chdir(comfy_path)

    try:
        Logger.log("Fetching updates and tags...", "info")
        subprocess.run(["git", "fetch", "--tags", "--all"], check=True, capture_output=True)

        if target_version.lower() == "latest":
            # Get the absolute newest tag name
            selection = subprocess.check_output(
                "git describe --tags $(git rev-list --tags --max-count=1)",
                shell=True, text=True
            ).strip()
            Logger.log(f"Identified latest release: {selection}", "ok")
        else:
            # Use the specific tag from config
            selection = target_version
            Logger.log(f"Targeting specific version: {selection}", "info")

        # Checkout the selection (Tag or Branch)
        subprocess.run(["git", "checkout", selection], check=True, capture_output=True)
        Logger.success(f"ComfyUI is now at {selection}")
        
    except Exception as e:
        Logger.warn(f"Failed to checkout '{target_version}': {e}. Using {fallback_branch}.")
        subprocess.run(["git", "checkout", fallback_branch], check=True, capture_output=True)
    
    finally:
        os.chdir(original_cwd)