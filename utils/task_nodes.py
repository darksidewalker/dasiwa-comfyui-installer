import os
import shutil
import urllib.request
from pathlib import Path
from utils.logger import Logger

def remove_readonly(func, path, excinfo=None):
    import stat
    os.chmod(path, stat.S_IWRITE)
    func(path)

def task_custom_nodes(env, nodes_list_url, nodes_list_file, run_cmd_func):
    stats = {"total": 0, "success": 0, "failed": [], "skipped": 0}
    # ... (existing setup code) ...

    try:
        urllib.request.urlretrieve(nodes_list_url, nodes_list_file)
        with open(nodes_list_file, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        
        stats["total"] = len(lines)
        
        for line in lines:
            # ... (parsing logic) ...
            try:
                # (cloning/pulling logic)
                stats["success"] += 1
            except Exception as node_err:
                Logger.error(f"Error syncing node {name}: {node_err}")
                stats["failed"].append(name)
                continue 

    except Exception as e:
        Logger.error(f"Custom node list processing failed: {e}")
    
    return stats # <--- Return this dictionary

    # 2. Download and Parse the nodes list
    try:
        urllib.request.urlretrieve(nodes_list_url, nodes_list_file)
        with open(nodes_list_file, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        
        for line in lines:
            repo_url = line.split("|")[0].strip()
            if "comfyui-manager" in repo_url.lower(): continue
            
            name = repo_url.split("/")[-1].replace(".git", "")
            node_path = nodes_dir / name
            
            try:
                if not node_path.exists():
                    Logger.log(f"Cloning {name}...", "info")
                    run_cmd_func(["git", "clone", "--recursive", repo_url, str(node_path)])
                else:
                    run_cmd_func(["git", "-C", str(node_path), "pull"])

                # Install requirements for the node
                req = node_path / "requirements.txt"
                if req.exists():
                    Logger.log(f"Installing dependencies for {name}...", "info")
                    run_cmd_func(["uv", "pip", "install", "-r", str(req)], env=env)
            except Exception as node_err:
                Logger.error(f"Error syncing node {name}: {node_err}")
                continue # Move to next node if one fails

    except Exception as e:
        Logger.error(f"Custom node list processing failed: {e}")