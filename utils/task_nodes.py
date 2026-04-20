import os
import urllib.request
import time
import platform
import stat
from pathlib import Path

from utils.logger import Logger


def remove_readonly(func, path, excinfo=None):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def fetch_node_list(source, retries=3, delay=2):
    """Load nodes either from a local file path or a remote URL."""
    local_path = Path(source)
    if local_path.exists() and local_path.is_file():
        try:
            return local_path.read_text(encoding="utf-8").splitlines()
        except Exception as e:
            Logger.error(f"Failed to read local node list: {e}")
            return []

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                source, headers={'User-Agent': 'DaSiWa-Installer/1.0'}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.read().decode('utf-8').splitlines()
        except Exception as e:
            if attempt < retries - 1:
                Logger.warn(f"Node list fetch failed: {e}. "
                            f"Retrying {attempt + 2}/{retries}...")
                time.sleep(delay)
            else:
                Logger.error(f"Could not fetch remote node list: {e}")
                return []
    return []


def _parse_node_line(line):
    """
    Parse `url | flag1 | flag2:value | ...` safely — tolerant of stray spaces.
    Returns (url, custom_req_filename, is_pkg).
    """
    parts = [p.strip() for p in line.split("|")]
    url = parts[0]
    is_pkg = False
    custom_req = "requirements.txt"
    for p in parts[1:]:
        if not p:
            continue
        lowered = p.lower()
        if lowered == "pkg":
            is_pkg = True
        elif lowered == "sub":
            pass  # flag is informational — recursive clone is default below
        elif lowered.startswith("req:"):
            custom_req = p[4:].strip() or "requirements.txt"
    return url, custom_req, is_pkg


def task_custom_nodes(env, nodes_source, nodes_list_file, run_cmd_func, comfy_path):
    """
    Sync custom nodes. Supports:
        <url>                             -> standard clone
        <url> | sub                       -> recursive submodule clone
        <url> | pkg                       -> editable (pip install -e .)
        <url> | req:custom-reqs.txt       -> custom requirements file
        combinations separated by `|`.
    """
    stats = {"total": 0, "success": 0, "failed": [], "skipped": 0}
    nodes_dir = Path(comfy_path).absolute() / "custom_nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)

    lines = fetch_node_list(nodes_source)
    if not lines:
        return stats

    clean = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
    stats["total"] = len(clean)

    py_suffix = "Scripts/python.exe" if platform.system() == "Windows" else "bin/python"
    venv_python = Path(env.get("VIRTUAL_ENV", "")) / py_suffix

    # Never hang on a credential prompt
    git_env = env.copy()
    git_env["GIT_TERMINAL_PROMPT"] = "0"

    for line in clean:
        repo_url, custom_req_name, is_pkg = _parse_node_line(line)

        if not repo_url or "comfyui-manager" in repo_url.lower():
            stats["skipped"] += 1
            continue

        name = repo_url.split("/")[-1].replace(".git", "").strip()
        node_path = nodes_dir / name

        try:
            # 1. Git sync
            if not node_path.exists():
                Logger.log(f"Cloning {name}...", "info")
                run_cmd_func(
                    ["git", "clone", "--recursive", repo_url, str(node_path)],
                    env=git_env,
                )
            else:
                Logger.log(f"Updating {name}...", "info")
                run_cmd_func(
                    ["git", "-C", str(node_path), "pull"],
                    env=git_env,
                )

            # 2. Dependencies via uv
            req_file = node_path / custom_req_name
            if req_file.exists():
                Logger.log(f"Installing deps via {custom_req_name}...", "info")
                if is_pkg:
                    run_cmd_func(
                        ["uv", "pip", "install", "-e", ".", "-r", str(req_file)],
                        env=env, cwd=str(node_path),
                    )
                else:
                    run_cmd_func(
                        ["uv", "pip", "install", "-r", str(req_file)], env=env,
                    )
            elif is_pkg:
                run_cmd_func(
                    ["uv", "pip", "install", "-e", "."], env=env, cwd=str(node_path),
                )
            else:
                Logger.debug(f"{name} has no requirements.txt — nothing extra to install.")

            # 3. Legacy install.py script
            install_script = node_path / "install.py"
            if install_script.exists():
                Logger.log(f"Running install.py for {name}...", "info")
                run_cmd_func(
                    [str(venv_python), str(install_script)],
                    env=env, cwd=str(node_path),
                )

            stats["success"] += 1
        except Exception as node_err:
            Logger.error(f"Error syncing node {name}: {node_err}")
            stats["failed"].append(name)

    return stats
