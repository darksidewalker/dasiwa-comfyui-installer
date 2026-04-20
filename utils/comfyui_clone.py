import subprocess
import os
from pathlib import Path

from utils.logger import Logger


def _git(args, cwd=None, check=True, capture=True):
    """Thin wrapper so we don't need shell=True for cross-platform calls."""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"  # never block on credential prompts
    return subprocess.run(
        args, cwd=cwd, check=check, env=env,
        capture_output=capture, text=True,
    )


def sync_comfyui(comfy_path, target_version="latest", fallback_branch="master"):
    """
    Clone (if missing) or sync an existing ComfyUI checkout to a specific
    tag or the newest release. Handles dirty working trees safely.
    """
    repo_url = "https://github.com/comfyanonymous/ComfyUI.git"
    comfy_path = Path(comfy_path).absolute()

    if not comfy_path.exists():
        Logger.log(f"Cloning ComfyUI into {comfy_path.name}/...", "info")
        _git(["git", "clone", repo_url, str(comfy_path)], check=True, capture=False)

    try:
        Logger.log("Fetching updates and tags...", "info")
        _git(["git", "fetch", "--tags", "--all", "--prune"], cwd=str(comfy_path), check=False)

        if target_version.lower() == "latest":
            # Cross-platform: get newest tag without shell substitution
            rev_res = _git(
                ["git", "rev-list", "--tags", "--max-count=1"],
                cwd=str(comfy_path), check=True,
            )
            rev = rev_res.stdout.strip()
            if not rev:
                raise RuntimeError("no tags found in ComfyUI repository")
            tag_res = _git(
                ["git", "describe", "--tags", rev],
                cwd=str(comfy_path), check=True,
            )
            selection = tag_res.stdout.strip()
            Logger.log(f"Identified latest release: {selection}", "ok")
        else:
            selection = target_version
            Logger.log(f"Targeting specific version: {selection}", "info")

        # Stash any local changes so checkout never fails on dirty tree
        stash_res = _git(
            ["git", "stash", "push", "--include-untracked", "-m", "dasiwa-autostash"],
            cwd=str(comfy_path), check=False,
        )
        stashed = "No local changes" not in (stash_res.stdout or "")

        _git(["git", "checkout", selection], cwd=str(comfy_path), check=True)
        Logger.success(f"ComfyUI is now at {selection}")

        if stashed:
            Logger.debug("Local changes were auto-stashed (see: git stash list)")

    except Exception as e:
        Logger.warn(f"Failed to checkout '{target_version}': {e}. Using {fallback_branch}.")
        try:
            _git(["git", "checkout", fallback_branch], cwd=str(comfy_path), check=True)
        except subprocess.CalledProcessError as err:
            Logger.error(f"Fallback checkout also failed: {err}")
            raise
