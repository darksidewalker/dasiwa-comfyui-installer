import os
import shutil
import urllib.request
from pathlib import Path
from utils.logger import Logger

def remove_readonly(func, path, excinfo=None):
    import stat
    os.chmod(path, stat.S_IWRITE)
    func(path)

def task_custom_nodes(env, nodes_list_url, nodes_list_file, run_cmd_func, comfy_path):
    """
    Syncs all custom nodes from the remote list into ComfyUI/custom_nodes.
    Returns a dictionary of stats for the Reporter.
    """
    stats = {"total": 0, "success": 0, "failed": [], "skipped": 0}
    
    # 1. Force the path to be inside ComfyUI/custom_nodes (Absolute)
    nodes_dir = Path(comfy_path).absolute() / "custom_nodes"
    nodes_dir.mkdir(exist_ok=True)

    # 2. Download and Parse the nodes list
    try:
        Logger.log(f"Fetching node list from {nodes_list_url}...", "info")
        urllib.request.urlretrieve(nodes_list_url, nodes_list_file)
        
        with open(nodes_list_file, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        
        stats["total"] = len(lines)
        
        for line in lines:
            # Parse line: handle simple URLs or pipe-delimited flags
            repo_url = line.split("|")[0].strip()
            
            # Skip manager as it's usually handled separately/first
            if "comfyui-manager" in repo_url.lower():
                stats["skipped"] += 1
                continue
            
            # Derive node folder name from URL
            name = repo_url.split("/")[-1].replace(".git", "")
            node_path = nodes_dir / name
            
            try:
                if not node_path.exists():
                    Logger.log(f"Cloning {name}...", "info")
                    # Explicitly target the node_path inside ComfyUI/custom_nodes
                    run_cmd_func(["git", "clone", "--recursive", repo_url, str(node_path)])
                else:
                    Logger.log(f"Updating {name}...", "info")
                    run_cmd_func(["git", "-C", str(node_path), "pull"])

                # Install requirements for the node using UV
                req = node_path / "requirements.txt"
                if req.exists():
                    Logger.log(f"Installing dependencies for {name}...", "info")
                    # str(req) ensures the path is handled correctly on Linux/Windows
                    run_cmd_func(["uv", "pip", "install", "-r", str(req)], env=env)
                
                stats["success"] += 1

            except Exception as node_err:
                Logger.error(f"Error syncing node {name}: {node_err}")
                stats["failed"].append(name)
                continue 

    except Exception as e:
        Logger.error(f"Custom node list processing failed: {e}")
    
    return stats