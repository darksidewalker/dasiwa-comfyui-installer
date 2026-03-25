import os
import shutil
import urllib.request
import time
from pathlib import Path
from utils.logger import Logger

def remove_readonly(func, path, excinfo=None):
    import stat
    os.chmod(path, stat.S_IWRITE)
    func(path)

def fetch_node_list(source, retries=3, delay=2):
    """Safely fetches nodes from either a local file or a URL."""
    # 1. Check if source is a local file
    local_path = Path(source)
    if local_path.exists() and local_path.is_file():
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                return f.read().splitlines()
        except Exception as e:
            Logger.error(f"Local file read error: {e}")
            return []

    # 2. Otherwise, treat as a URL
    for attempt in range(retries):
        try:
            req = urllib.request.Request(source, headers={'User-Agent': 'Python-Installer'})
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.read().decode('utf-8').splitlines()
        except Exception as e:
            if attempt < retries - 1:
                Logger.warn(f"Retry {attempt + 2}/{retries} for node list...")
                time.sleep(delay)
            else:
                Logger.error(f"Failed to fetch remote node list: {e}")
                return []
    return []

def task_custom_nodes(env, nodes_source, nodes_list_file, run_cmd_func, comfy_path):
    stats = {"total": 0, "success": 0, "failed": [], "skipped": 0}
    nodes_dir = Path(comfy_path).absolute() / "custom_nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)

    lines = fetch_node_list(nodes_source)
    if not lines:
        Logger.error("No custom nodes found to process.")
        return stats

    clean_lines = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
    stats["total"] = len(clean_lines)
    
    for line in clean_lines:
        # Standardize repo URL
        repo_url = line.split("|")[0].strip()
        if not repo_url or "comfyui-manager" in repo_url.lower():
            stats["skipped"] += 1
            continue
        
        name = repo_url.split("/")[-1].replace(".git", "").strip()
        node_path = nodes_dir / name
        
        try:
            if not node_path.exists():
                Logger.log(f"Cloning {name}...", "info")
                run_cmd_func(["git", "clone", "--recursive", repo_url, str(node_path)])
            else:
                Logger.log(f"Updating {name}...", "info")
                run_cmd_func(["git", "-C", str(node_path), "pull"])

            # Install dependencies
            for req_name in ["requirements.txt", "install.py"]:
                req_file = node_path / req_name
                if req_file.exists():
                    if req_name == "requirements.txt":
                        run_cmd_func(["uv", "pip", "install", "-r", str(req_file)], env=env)
                    else:
                        run_cmd_func([env.get("VIRTUAL_ENV", "") + "/bin/python", str(req_file)], env=env)
            
            stats["success"] += 1
        except Exception as node_err:
            Logger.error(f"Error syncing node {name}: {node_err}")
            stats["failed"].append(name)

    return stats