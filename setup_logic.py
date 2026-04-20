import subprocess
import os
import sys
import platform
import urllib.request
import shutil
import argparse
import time
from pathlib import Path
import json

# Ensure `utils` is importable regardless of cwd
SCRIPT_ROOT = Path(__file__).parent.absolute()
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.append(str(SCRIPT_ROOT))

from utils.logger import Logger
from utils.reporter import Reporter
from utils.hardware import get_gpu_report
from utils.task_nodes import task_custom_nodes
from utils.downloader import Downloader
from utils.comfyui_clone import sync_comfyui
from utils.task_sageattention import SageInstaller
from utils.task_ffmpeg import FFmpegInstaller

IS_WIN = platform.system() == "Windows"
Logger.init()

# --- CONSTANTS ---
PRIORITY_PACKAGES = [
    "torch",
    "torchvision",
    "torchaudio",
    "numpy>=2.1.0,<=2.3.0",
    "pillow>=11.0.0",
    "pydantic>=2.12.5",
    "setuptools==81.0.0",
]

# Minimum disk space we want before starting (GB)
MIN_DISK_GB = 20


# ============================================================================
#  COMMAND WRAPPERS
# ============================================================================

def run_cmd(cmd, env=None, stream=False, **kwargs):
    """
    Run a command and raise on failure. When `stream=True`, inherit stdio so the
    user can see progress (used for long-running installs). Otherwise capture
    output and surface it only on failure.
    """
    if stream:
        subprocess.run(cmd, env=env, check=True, **kwargs)
        return
    try:
        subprocess.run(cmd, env=env, check=True,
                       capture_output=True, text=True, **kwargs)
    except subprocess.CalledProcessError as e:
        Logger.error(f"Command failed: {' '.join(map(str, cmd))}")
        if e.stdout:
            Logger.log(e.stdout, "info")
        if e.stderr:
            Logger.log(e.stderr, "fail")
        raise


def get_venv_env(comfy_path):
    venv_path = comfy_path / "venv"
    full_env = os.environ.copy()
    full_env["VIRTUAL_ENV"] = str(venv_path)
    bin_dir = "Scripts" if IS_WIN else "bin"
    full_env["PATH"] = str(venv_path / bin_dir) + os.pathsep + full_env["PATH"]
    return full_env, bin_dir


# ============================================================================
#  PRE-FLIGHT CHECKS
# ============================================================================

def _get_git_version_tuple(git_exe="git"):
    """Return the installed git version as an integer tuple, e.g. (2, 53, 2).
    Returns None if git is not found or the version string is unparseable."""
    try:
        res = subprocess.run(
            [git_exe, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        # Output: "git version 2.53.2.windows.1"
        parts = res.stdout.strip().split()
        if len(parts) >= 3:
            # Take only the numeric segments before any platform suffix
            ver_str = parts[2].split(".windows")[0].split("-")[0]
            return tuple(int(x) for x in ver_str.split(".") if x.isdigit())
    except Exception:
        pass
    return None


def _fetch_latest_git_windows_url():
    """Query the GitHub releases API for the newest Git for Windows 64-bit installer.
    Returns the browser_download_url string, or None on failure."""
    api = "https://api.github.com/repos/git-for-windows/git/releases/latest"
    try:
        req = urllib.request.Request(api, headers={"User-Agent": "DaSiWa-Installer/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            # Target the standard 64-bit setup exe; skip portable and arm64 builds
            if name.endswith("64-bit.exe") and "arm" not in name.lower():
                Logger.log(f"Latest Git for Windows: {name}", "info")
                return asset["browser_download_url"]
    except Exception as e:
        Logger.warn(f"Could not fetch latest Git release from GitHub API: {e}")
    return None


def _install_git_windows():
    """Download and silently install the latest Git for Windows.
    Only called when git is genuinely absent. Returns True on success."""
    url = _fetch_latest_git_windows_url()
    if not url:
        # Fallback: winget is present on all modern Windows 10/11 installs
        if shutil.which("winget"):
            Logger.log("GitHub API unavailable — trying winget...", "info")
            try:
                subprocess.run(
                    ["winget", "install", "--id", "Git.Git",
                     "-e", "--source", "winget", "--silent"],
                    check=True,
                )
                Logger.log("Git installed via winget.", "ok")
                return True
            except subprocess.CalledProcessError:
                pass
        Logger.error(
            "Could not download Git. Install manually from https://gitforwindows.org/ "
            "then re-run the installer."
        )
        return False

    installer = Path.home() / "git_installer.exe"
    try:
        Logger.log("Downloading Git for Windows...", "info")
        urllib.request.urlretrieve(url, installer)

        # Full silent flag set per https://gitforwindows.org/silent-or-unattended-installation.html
        # /CLOSEAPPLICATIONS — silently closes blocking processes (e.g. MSYS2) instead of prompting
        # /NOCANCEL         — removes the Cancel button so the installer cannot be aborted mid-run
        # /NORESTART        — suppresses the post-install reboot dialog
        # /SP-              — suppresses the "This will install..." splash prompt
        subprocess.run(
            [str(installer),
             "/VERYSILENT", "/NORESTART", "/NOCANCEL",
             "/SP-", "/CLOSEAPPLICATIONS"],
            check=True,
        )
        Logger.log("Git installed successfully.", "ok")
        return True
    except subprocess.CalledProcessError as e:
        Logger.error(f"Git installer exited with code {e.returncode}.")
        return False
    except Exception as e:
        Logger.error(f"Git install failed: {e}")
        return False
    finally:
        installer.unlink(missing_ok=True)


def ensure_dependencies(target_python_version, urls):
    """Pre-flight: Python version check, Git presence check, disk space."""
    Logger.section("Pre-flight checks")

    # Python version
    current_py = platform.python_version()
    try:
        cur_mm = tuple(int(x) for x in current_py.split(".")[:2])
        tgt_mm = tuple(int(x) for x in str(target_python_version).split(".")[:2])
        if cur_mm != tgt_mm:
            Logger.warn(f"Running on Python {current_py}, but "
                        f"{target_python_version} is preferred.")
        else:
            Logger.log(f"Python {current_py} ✓", "ok")
    except ValueError:
        Logger.warn(f"Could not parse Python version: {current_py}")

    # Git — check presence AND version; only install if truly missing
    installed_ver = _get_git_version_tuple()
    if installed_ver:
        ver_str = ".".join(str(x) for x in installed_ver)
        Logger.log(f"Git {ver_str} ✓", "ok")
    else:
        # Git is genuinely absent from PATH
        if IS_WIN:
            Logger.log("Git not found — installing...", "info")
            if not _install_git_windows():
                sys.exit(1)
            # Verify it's now reachable (the installer updates PATH in the registry;
            # we need to refresh it for the current process)
            new_git = _get_git_version_tuple()
            if not new_git:
                Logger.warn(
                    "Git was installed but is not yet on this session's PATH. "
                    "Please close and reopen your terminal, then re-run the installer."
                )
                sys.exit(1)
            Logger.log("Git is now available ✓", "ok")
        else:
            Logger.error(
                "Git is not installed. Run: sudo apt install git  "
                "(or the equivalent for your distro)"
            )
            sys.exit(1)

    # Disk space
    try:
        free_gb = shutil.disk_usage(Path.cwd()).free / (1024 ** 3)
        if free_gb < MIN_DISK_GB:
            Logger.warn(f"Only {free_gb:.1f} GB free — a full setup "
                        f"typically needs {MIN_DISK_GB}+ GB.")
            if not Logger.ask_yes_no("Continue anyway?", default=False):
                sys.exit(1)
        else:
            Logger.log(f"Disk space: {free_gb:.1f} GB free ✓", "ok")
    except Exception:
        pass


# ============================================================================
#  PRE-FLIGHT WIZARD  (the main UX addition)
# ============================================================================

def _detect_existing_state(current_dir):
    """Return a dict describing what's already on disk, for confirmation logic."""
    comfy_path = current_dir / "ComfyUI"
    venv_path = comfy_path / "venv"
    bin_dir = "Scripts" if IS_WIN else "bin"
    python_exe = venv_path / bin_dir / ("python.exe" if IS_WIN else "python")

    state = {
        "comfy_exists": comfy_path.exists() and (comfy_path / "main.py").exists(),
        "venv_exists": python_exe.exists(),
        "sage_installed": False,
        "ffmpeg_local": (comfy_path / "ffmpeg" / "bin").exists(),
        "torch_installed": False,
        "torch_version": None,
        "torch_cuda": None,
        "comfy_path": comfy_path,
        "python_exe": python_exe,
    }

    if python_exe.exists():
        try:
            r = subprocess.run(
                [str(python_exe), "-c",
                 "import torch;"
                 "print(torch.__version__);"
                 "print(torch.version.cuda or '')"],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0:
                lines = r.stdout.strip().splitlines()
                state["torch_installed"] = True
                state["torch_version"] = lines[0] if lines else None
                state["torch_cuda"] = lines[1] if len(lines) > 1 else None
        except Exception:
            pass
        state["sage_installed"] = SageInstaller.is_installed(python_exe)

    return state


def _resolve_cuda_target(config_data, want_sage):
    """
    Apply the Windows downgrade rule: if SageAttention is requested and
    config says cuda 13.x, offer to downgrade *in-memory* to 12.8 for this
    install. config.json is not touched.
    """
    global_cuda = config_data["cuda"].get("global", "13.0")
    if not (IS_WIN and want_sage):
        return global_cuda, False

    try:
        major = int(str(global_cuda).split(".")[0])
    except (ValueError, IndexError):
        return global_cuda, False

    if major < 13:
        return global_cuda, False

    Logger.warn(f"Windows + SageAttention + CUDA {global_cuda} is a known-flaky "
                f"combination.")
    Logger.log("Upstream PyTorch 2.9+ has a header bug that breaks the MSVC "
               "build of SageAttention.", "info")
    Logger.log("Recommendation: temporarily downgrade to CUDA 12.8 for this install.",
               "info")

    if Logger.ask_yes_no("Downgrade CUDA target to 12.8 for this install only? "
                         "(config.json stays untouched)", default=True):
        Logger.log(f"CUDA target downgraded: {global_cuda} → 12.8 (this run only)", "ok")
        return "12.8", True
    Logger.warn("Proceeding with CUDA 13.x — SageAttention may fail to build on Windows.")
    return global_cuda, False


def preflight_wizard(config_data, current_dir, hw):
    """
    Ask every interactive question up front and return a plan dict. The rest of
    the install runs without further prompts. On user cancel: exit cleanly.
    """
    Logger.banner("Setup Wizard", "Configure the install, confirm once, then walk away")

    state = _detect_existing_state(current_dir)

    # ----- 1. Handle existing install -----
    install_mode = "fresh"
    if state["comfy_exists"]:
        Logger.section("Existing installation detected")
        Logger.kv("ComfyUI:", state["comfy_path"])
        Logger.kv("Venv:", "yes" if state["venv_exists"] else "no")
        if state["torch_installed"]:
            Logger.kv("Torch:",
                      f"{state['torch_version']} (cuda {state['torch_cuda'] or 'cpu'})")
        Logger.kv("SageAttention:", "installed" if state["sage_installed"] else "not installed")
        Logger.kv("Local FFmpeg:", "yes" if state["ffmpeg_local"] else "no")

        idx = Logger.ask_choice(
            "What do you want to do?",
            [
                ("Update in place",
                 "pull ComfyUI changes, re-sync nodes, keep the venv"),
                ("Refresh environment",
                 "rebuild the venv and reinstall packages, keep models"),
                ("Full reinstall",
                 "wipe ComfyUI/ and rebuild from scratch (models deleted!)"),
                ("Cancel", "exit without touching anything"),
            ],
            default_index=0,
        )
        if idx == 0:
            install_mode = "update"
        elif idx == 1:
            install_mode = "refresh"
        elif idx == 2:
            if not Logger.ask_yes_no(
                "This will DELETE the existing ComfyUI folder and all models inside it. "
                "Are you sure?", default=False,
            ):
                Logger.log("Aborted.", "warn")
                sys.exit(0)
            install_mode = "wipe"
        else:
            Logger.log("Cancelled.", "info")
            sys.exit(0)

    # ----- 2. ComfyUI version -----
    comfy_prefs = config_data.get("comfyui", {})
    raw_version = comfy_prefs.get("version", "latest")
    target_version = "master" if str(raw_version).lower() == "latest" else raw_version

    # ----- 3. SageAttention -----
    Logger.section("Optional components")
    default_sage = hw["vendor"] == "NVIDIA"
    want_sage = Logger.ask_yes_no(
        "Install SageAttention? (faster attention kernels for NVIDIA GPUs)",
        default=default_sage,
    )
    if want_sage and hw["vendor"] != "NVIDIA":
        Logger.warn(f"SageAttention requires NVIDIA; detected vendor: {hw['vendor']}.")
        if not Logger.ask_yes_no("Try anyway?", default=False):
            want_sage = False

    # ----- 4. FFmpeg -----
    if FFmpegInstaller.is_installed() or state["ffmpeg_local"]:
        Logger.log("FFmpeg already present — will be reused.", "ok")
        want_ffmpeg = False
    else:
        want_ffmpeg = Logger.ask_yes_no(
            "Install FFmpeg? (needed by video nodes like VideoHelperSuite)",
            default=True,
        )

    # ----- 5. CUDA target (with conditional Windows downgrade) -----
    cuda_target, downgraded = _resolve_cuda_target(config_data, want_sage)

    # ----- 6. Optional downloads -----
    selected_downloads = []
    if config_data.get("optional_downloads") and install_mode != "wipe":
        # For 'wipe', we defer selection — no ComfyUI folder yet. We still ask.
        pass

    if config_data.get("optional_downloads"):
        Logger.section("Optional models & workflows")
        # For listing purposes, pretend comfy_path exists (only used for file checks)
        comfy_check_path = (
            state["comfy_path"] if state["comfy_exists"]
            else current_dir / "ComfyUI"
        )
        missing = Downloader.filter_missing(
            list(config_data["optional_downloads"]), comfy_check_path,
        )
        if not missing:
            Logger.log("All optional components already present.", "ok")
        else:
            for i, item in enumerate(missing, 1):
                print(f"  {Logger.DIM}{i}.{Logger.END} {item['name']}")
            print(f"\n  {Logger.DIM}Commands: numbers (e.g. 1,3), 'all', or empty "
                  f"to skip{Logger.END}")
            raw = Logger.ask("Which to download?", default="all")
            if raw:
                if raw.lower() == "all":
                    selected_downloads = missing
                else:
                    try:
                        indices = [int(x) - 1 for x
                                   in raw.replace(',', ' ').split()]
                        selected_downloads = [
                            missing[i] for i in indices
                            if 0 <= i < len(missing)
                        ]
                    except ValueError:
                        Logger.warn("Unrecognised selection — skipping downloads.")

    # ----- 7. Review & confirm -----
    Logger.banner("Configuration Summary", "Review before starting")
    Logger.kv("Mode:",        install_mode)
    Logger.kv("GPU:",         hw["name"])
    Logger.kv("Vendor:",      hw["vendor"])
    Logger.kv("Python:",      config_data["python"].get("display_name", "3.12"))
    cuda_label = f"{cuda_target}" + (" (downgraded for Sage compat)" if downgraded else "")
    Logger.kv("CUDA target:", cuda_label)
    Logger.kv("ComfyUI:",     target_version)
    Logger.kv("SageAttention:", "yes" if want_sage else "no")
    Logger.kv("FFmpeg:",      "yes" if want_ffmpeg else "no")
    Logger.kv("Downloads:",   f"{len(selected_downloads)} item(s)")
    Logger.rule()

    if not Logger.ask_yes_no("Proceed with these settings?", default=True):
        Logger.log("Cancelled by user.", "info")
        sys.exit(0)

    return {
        "install_mode":       install_mode,
        "state":              state,
        "target_version":     target_version,
        "fallback_branch":    comfy_prefs.get("fallback_branch", "master"),
        "want_sage":          want_sage,
        "want_ffmpeg":        want_ffmpeg,
        "cuda_target":        cuda_target,
        "cuda_downgraded":    downgraded,
        "selected_downloads": selected_downloads,
    }


# ============================================================================
#  TORCH INSTALL
# ============================================================================

def install_torch(env, hw, cuda_target, config):
    vendor, gpu_name = hw["vendor"], hw["name"].upper()
    min_50xx_cu = config.get("cuda", {}).get("min_cuda_for_50xx", "12.8")

    whl_url = "https://download.pytorch.org/whl/"
    cmd = ["uv", "pip", "install"]
    is_nightly = False

    if vendor == "NVIDIA":
        target_cu = cuda_target

        # Legacy overrides
        if "GTX 10" in gpu_name or any(x in gpu_name for x in ("PASCAL", "LEGACY")):
            target_cu = "12.1"
        elif "RTX 50" in gpu_name:
            target_cu = min_50xx_cu
            is_nightly = True

        if is_nightly:
            cmd += ["--pre"]

        if target_cu == "12.1":
            cmd += ["torch==2.4.1", "torchvision==0.19.1", "torchaudio==2.4.1"]
        else:
            cmd += ["torch", "torchvision", "torchaudio"]

        cmd += ["--extra-index-url", f"{whl_url}cu{target_cu.replace('.', '')}"]

    elif vendor == "AMD":
        if any(x in gpu_name for x in ("GFX110", "RX 7000")):
            cmd += ["--pre", "torch", "torchvision", "torchaudio",
                    "--index-url", "https://rocm.nightlies.amd.com/v2/gfx110X-all/"]
        elif any(x in gpu_name for x in ("GFX1151", "STRIX")):
            cmd += ["--pre", "torch", "torchvision", "torchaudio",
                    "--index-url", "https://rocm.nightlies.amd.com/v2/gfx1151/"]
        elif any(x in gpu_name for x in ("GFX120", "RX 9000")):
            cmd += ["--pre", "torch", "torchvision", "torchaudio",
                    "--index-url", "https://rocm.nightlies.amd.com/v2/gfx120X-all/"]
        else:
            cmd += ["torch", "torchvision", "torchaudio",
                    "--index-url", f"{whl_url}rocm7.1"]

    elif vendor == "INTEL":
        cmd += ["torch", "torchvision", "torchaudio",
                "--index-url", f"{whl_url}xpu"]

    Logger.log(f"Installing Torch for {vendor} ({gpu_name})...", "info")
    run_cmd(cmd, env=env, stream=True)


# ============================================================================
#  LAUNCHERS
# ============================================================================

def task_create_launchers(comfy_path, bin_dir):
    """Create run_comfyui.bat / .sh with FFmpeg PATH injection when present."""
    ffmpeg_bin = comfy_path / "ffmpeg" / "bin"
    has_local_ffmpeg = ffmpeg_bin.exists()

    if os.name == "nt":
        venv_python = r"venv\Scripts\python.exe"
        args = "--enable-manager --preview-method auto"
        path_injection = "set PATH=%~dp0ffmpeg\\bin;%PATH%\n" if has_local_ffmpeg else ""
        content = (
            f"@echo off\n"
            f'cd /d "%~dp0"\n'
            f"{path_injection}"
            f"start http://127.0.0.1:8188\n"
            f'"{venv_python}" main.py {args}\n'
            f"pause"
        )
        launcher_path = comfy_path / "run_comfyui.bat"
    else:
        venv_python = "./venv/bin/python3"
        args = "--enable-manager --preview-method auto"
        # Inject portable ffmpeg on Linux too if present
        path_injection = ""
        if has_local_ffmpeg:
            path_injection = 'export PATH="$(dirname "$0")/ffmpeg/bin:$PATH"\n'
        content = (
            f"#!/bin/bash\n"
            f'cd "$(dirname "$0")"\n'
            f"{path_injection}"
            f'(sleep 5 && xdg-open http://127.0.0.1:8188) &\n'
            f'"{venv_python}" main.py {args}\n'
        )
        launcher_path = comfy_path / "run_comfyui.sh"

    with open(launcher_path, "w", newline='\n') as f:
        f.write(content)

    if os.name != "nt":
        os.chmod(launcher_path, 0o755)

    Logger.log(f"Launcher created: {launcher_path}", "ok")


# ============================================================================
#  CONFIG LOADING (with deep-merge override)
# ============================================================================

def load_config(current_dir):
    config_path = current_dir / "config.json"
    local_config_path = current_dir / "config.local.json"

    if not config_path.exists():
        Logger.error(f"config.json not found at {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding='utf-8') as f:
        config_data = json.load(f)

    if local_config_path.exists():
        Logger.log("Applying local configuration overrides...", "magenta")
        try:
            with open(local_config_path, "r", encoding='utf-8') as f:
                local_data = json.load(f)
            for section in ("python", "comfyui", "cuda", "urls"):
                if section in local_data:
                    if isinstance(local_data[section], dict):
                        config_data.setdefault(section, {}).update(local_data[section])
                    else:
                        config_data[section] = local_data[section]
        except Exception as e:
            Logger.warn(f"Failed to parse config.local.json: {e}. Using defaults.")

    return config_data


def resolve_nodes_source(config_data, current_dir):
    """custom_nodes.local.txt > config urls.custom_nodes."""
    local_nodes = current_dir / "custom_nodes.local.txt"
    if local_nodes.exists():
        Logger.log("Using custom_nodes.local.txt (local override)", "magenta")
        return str(local_nodes)
    return config_data.get("urls", {}).get(
        "custom_nodes",
        "https://raw.githubusercontent.com/darksidewalker/"
        "dasiwa-comfyui-installer/main/custom_nodes.txt",
    )


# ============================================================================
#  MAIN
# ============================================================================

def main():
    start_time = time.time()
    CURRENT_RUN_DIR = Path.cwd().absolute()

    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", default="master",
                        help="Branch of ComfyUI to clone (fallback)")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Accept all defaults without prompting")
    args = parser.parse_args()

    # 1. Load config
    config_data = load_config(CURRENT_RUN_DIR)
    target_python = config_data["python"].get("display_name", "3.12")

    # 2. Pre-flight checks
    ensure_dependencies(target_python, config_data.get("urls", {}))

    # 3. Hardware detection
    hw = get_gpu_report(IS_WIN, Logger)

    # 4. Wizard (asks everything, then confirms)
    plan = preflight_wizard(config_data, CURRENT_RUN_DIR, hw)

    # 5. Execute plan
    comfy_path = CURRENT_RUN_DIR / "ComfyUI"
    node_stats = None
    sage_installed = False
    ffmpeg_installed = FFmpegInstaller.is_installed() or plan["state"]["ffmpeg_local"]

    # Define a helper for phase-isolated error handling:
    # If a phase raises, log it and continue with the next one instead of
    # aborting the entire install.
    def _phase(name, fn, *args, critical=False, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if critical:
                Logger.error(f"CRITICAL phase failed: {name}: {e}")
                raise
            Logger.error(f"Phase failed: {name}: {e}")
            Logger.warn(f"Continuing with remaining phases...")
            return None

    try:
        # Handle wipe: remove old folder
        if plan["install_mode"] == "wipe" and comfy_path.exists():
            Logger.log(f"Wiping {comfy_path} ...", "warn")
            shutil.rmtree(comfy_path, ignore_errors=True)

        # ComfyUI checkout is CRITICAL — without it, nothing else makes sense
        _phase("ComfyUI checkout", sync_comfyui,
               comfy_path,
               target_version=plan["target_version"],
               fallback_branch=plan["fallback_branch"],
               critical=True)

        # Venv creation is CRITICAL — everything downstream needs it
        need_new_venv = plan["install_mode"] in ("fresh", "refresh", "wipe") \
                        or not plan["state"]["venv_exists"]
        if need_new_venv:
            Logger.log(f"Setting up Virtual Environment (UV) with "
                       f"Python {target_python}...", "info")
            _phase("venv create", run_cmd,
                   ["uv", "venv", str(comfy_path / "venv"),
                    "--python", target_python, "--clear"],
                   stream=True, critical=True)
        else:
            Logger.log("Reusing existing virtual environment.", "ok")

        venv_env, bin_dir = get_venv_env(comfy_path)

        # Downloads — non-critical, failures here must not block torch/nodes/sage
        if plan["selected_downloads"]:
            _phase("optional downloads",
                   Downloader.install_selected,
                   plan["selected_downloads"], comfy_path)

        # Switch cwd to ComfyUI for subsequent operations
        os.chdir(comfy_path)

        # Torch — critical for everything downstream
        _phase("torch install", install_torch,
               venv_env, hw, plan["cuda_target"], config_data,
               critical=True)

        # ComfyUI requirements — critical
        Logger.log("Installing core requirements...", "info")
        _phase("ComfyUI requirements", run_cmd,
               ["uv", "pip", "install", "-r", "requirements.txt"],
               env=venv_env, stream=True, critical=True)

        # FFmpeg — non-critical
        if plan["want_ffmpeg"]:
            _phase("ffmpeg install",
                   FFmpegInstaller.run, comfy_path, config_data.get("urls", {}))
            ffmpeg_installed = (
                FFmpegInstaller.is_installed() or
                FFmpegInstaller.is_local_installed(comfy_path)
            )

        # Custom nodes — non-critical, individual node failures are already caught inside
        Logger.log("Synchronizing Custom Nodes...", "info")
        nodes_source = resolve_nodes_source(config_data, CURRENT_RUN_DIR)
        node_stats = _phase("custom nodes sync", task_custom_nodes,
                            venv_env, nodes_source, "custom_nodes.txt",
                            run_cmd, comfy_path)

        # ComfyUI-Manager requirements — non-critical
        Logger.log("Enforcing priority packages & ComfyUI-Manager...", "info")
        manager_req = comfy_path / "manager_requirements.txt"
        if manager_req.exists():
            _phase("manager requirements", run_cmd,
                   ["uv", "pip", "install", "-r", str(manager_req)],
                   env=venv_env, stream=True)

        # Priority package enforcement — non-critical (torch is already installed)
        _phase("priority package enforcement", run_cmd,
               ["uv", "pip", "install", "--upgrade"] + PRIORITY_PACKAGES,
               env=venv_env, stream=True)

        # SageAttention — non-critical, runs LAST (after torch is locked in)
        if plan["want_sage"]:
            _phase("SageAttention install",
                   SageInstaller.build_sage,
                   venv_env, comfy_path, config_data.get("urls", {}))
            # Re-check after attempt
            bin_suffix = "Scripts/python.exe" if IS_WIN else "bin/python"
            python_exe = comfy_path / "venv" / bin_suffix
            sage_installed = SageInstaller.is_installed(python_exe)

    except Exception as e:
        Logger.error(f"Installation aborted: {e}")

    # 6. Finalise
    os.chdir(CURRENT_RUN_DIR)
    task_create_launchers(comfy_path, bin_dir)

    Reporter.show_summary(
        hw, venv_env, start_time,
        node_stats=node_stats,
        sage_installed=sage_installed if plan["want_sage"] else None,
        ffmpeg_installed=ffmpeg_installed if plan["want_ffmpeg"] else None,
    )
    try:
        input("\nPress Enter to exit...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
