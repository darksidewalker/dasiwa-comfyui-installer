import os
import platform
import subprocess
import shutil
import json
import re
import urllib.request
import ctypes
import time
from pathlib import Path

from utils.logger import Logger


# Triton version matrix for Windows.
# Each entry: minimum torch (tuple) -> triton-windows version specifier for pip.
# Triton is on PyPI as 'triton-windows' so no GitHub URL needed.
# Source: https://github.com/triton-lang/triton-windows/releases
_TRITON_TORCH_MATRIX = [
    ((2, 10), "triton-windows>=3.6,<3.7"),
    ((2,  9), "triton-windows>=3.5,<3.6"),
    ((2,  8), "triton-windows>=3.4,<3.5"),
    ((2,  7), "triton-windows>=3.3,<3.4"),
]


def _triton_spec_for_torch(torch_ver_tuple):
    """Return the correct triton-windows version specifier for a given torch version."""
    for min_torch, spec in _TRITON_TORCH_MATRIX:
        if torch_ver_tuple >= min_torch:
            return spec
    # Very old torch — try latest triton anyway
    return "triton-windows"


class SageInstaller:

    # ------------------------------------------------------------------ #
    #  Public helpers                                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_input(prompt):
        return input(prompt)

    @staticmethod
    def is_installed(python_exe):
        """Return True if sageattention is importable in the target venv."""
        try:
            res = subprocess.run(
                [str(python_exe), "-c",
                 "import sageattention; "
                 "print(getattr(sageattention, '__version__', 'ok'))"],
                capture_output=True, text=True, timeout=30,
            )
            return res.returncode == 0
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    #  Pre-torch planning (called from setup_logic BEFORE torch install)   #
    # ------------------------------------------------------------------ #

    @classmethod
    def plan_windows_torch(cls, python_display, cuda_target):
        """Return the torch version to pin so that SageAttention prebuilt wheels
        will exist after install.

        The woct0rdho post4 ABI3 wheel supports torch >= 2.9, so any torch >= 2.9
        already works.  We simply query the latest available torch for the requested
        CUDA target and confirm it is >= 2.9.  If the live check fails we fall back
        to a safe known-good pin.

        Returns (torch_version_str, cu_tag_str) e.g. ('2.10.0', 'cu128'),
        or (None, None) if nothing appropriate can be determined.
        """
        if platform.system() != "Windows":
            return None, None

        try:
            cu_mm = ".".join(cuda_target.split(".")[:2])
        except Exception:
            cu_mm = cuda_target
        cu_tag = "cu" + cu_mm.replace(".", "")

        # The post4 ABI3 wheel covers torch >= 2.9.  We try to install the
        # latest torch for the requested CUDA — if it turns out to be >= 2.9
        # the Sage wheel will work without any extra pinning.
        # We always pin to a concrete version so the environment is reproducible.
        # Fallback table: last known-good torch per (python, cuda).
        _FALLBACK = {
            ("3.12", "12.8"): "2.10.0",
            ("3.12", "13.0"): "2.10.0",
            ("3.13", "12.8"): "2.10.0",
            ("3.13", "13.0"): "2.10.0",
            ("3.11", "12.8"): "2.9.1",
            ("3.10", "12.8"): "2.9.1",
        }
        py_mm = ".".join(str(python_display).split(".")[:2])
        pin = _FALLBACK.get((py_mm, cu_mm), "2.9.1")
        Logger.log(
            f"Torch target for Sage compatibility: {pin} + {cu_tag} "
            f"(ABI3 wheel supports torch >= 2.9)", "ok"
        )
        return pin, cu_tag

    # ------------------------------------------------------------------ #
    #  Main public entry point                                             #
    # ------------------------------------------------------------------ #

    @classmethod
    def build_sage(cls, venv_env, comfy_path, config_urls):
        """Install SageAttention + triton-windows on Windows (prebuilt wheels),
        or build from source on Linux."""
        is_win = platform.system() == "Windows"
        venv_root = Path(venv_env.get("VIRTUAL_ENV", ""))
        python_exe = venv_root / ("Scripts/python.exe" if is_win else "bin/python")
        uv_exe     = venv_root / ("Scripts/uv.exe"    if is_win else "bin/uv")

        if not python_exe.exists():
            Logger.error(f"Could not find venv Python at {python_exe}")
            return

        if cls.is_installed(python_exe):
            Logger.log("SageAttention already installed — skipping.", "ok")
            return

        if is_win:
            cls._install_windows(python_exe, uv_exe, venv_env)
        else:
            if not cls._install_system_dependencies(config_urls):
                Logger.log("Build dependencies missing. Skipping SageAttention.", "warn")
                return
            cls._source_build(venv_env, comfy_path, config_urls, python_exe)

    # ------------------------------------------------------------------ #
    #  Windows: prebuilt wheel + triton-windows                           #
    # ------------------------------------------------------------------ #

    @classmethod
    def _install_windows(cls, python_exe, uv_exe, venv_env):
        """Install SageAttention on Windows using the prebuilt ABI3 wheel from
        woct0rdho and then install the matching triton-windows from PyPI.

        Strategy (in order):
          1. Detect installed torch version and CUDA tag.
          2. Build the direct GitHub release URL for the ABI3 'andhigher' wheel —
             this wheel covers any torch >= 2.9 and any Python >= 3.9, so no
             version matching complexity is needed.
          3. Install with UV_SKIP_WHEEL_FILENAME_CHECK=1 because uv rejects the
             non-standard 'torch2.9.0andhigher' token in the wheel filename.
          4. Install the matching triton-windows from PyPI.

        Returns True if installed successfully, False otherwise.
        """
        # 1. Probe installed torch
        torch_ver, torch_cuda, py_mm = cls._probe_torch(python_exe)
        if not torch_ver:
            Logger.error("Could not determine installed torch version. "
                         "Cannot select SageAttention wheel.")
            return False

        torch_tuple = cls._parse_ver(torch_ver)
        Logger.log(
            f"Detected: torch {torch_ver}, CUDA {torch_cuda}, Python {py_mm}", "info"
        )

        if torch_tuple < (2, 9):
            Logger.warn(
                f"Torch {torch_ver} is older than 2.9. The prebuilt ABI3 SageAttention "
                f"wheel requires torch >= 2.9. Falling back to source build."
            )
            # Source build on Windows is still attempted for completeness
            # but will likely fail without MSVC — inform the user clearly.
            Logger.log(
                "To fix: run the installer again after upgrading torch to >= 2.9, "
                "or set cuda.global to 12.8 in config.local.json and reinstall.", "info"
            )
            return False

        cu_tag = "cu" + torch_cuda.replace(".", "")

        # 2. Determine the right Sage release URL
        sage_url = cls._resolve_sage_wheel_url(cu_tag, uv_exe, venv_env, python_exe)
        if not sage_url:
            return False

        # 3. Install SageAttention wheel
        Logger.log(f"Installing SageAttention from prebuilt wheel...", "info")
        Logger.log(f"  {sage_url.rsplit('/', 1)[-1]}", "debug")

        install_env = venv_env.copy()
        # Required: uv rejects the 'torch2.9.0andhigher' token in the wheel
        # filename as invalid PEP 427 — this flag bypasses that check.
        install_env["UV_SKIP_WHEEL_FILENAME_CHECK"] = "1"

        cmd = [
            str(uv_exe) if uv_exe.exists() else "uv",
            "pip", "install",
            "--force-reinstall",
            "--no-cache",
            "--python", str(python_exe),
            sage_url,
        ]
        try:
            subprocess.run(cmd, env=install_env, check=True)
            Logger.success("SageAttention installed.")
        except subprocess.CalledProcessError as e:
            Logger.error(f"SageAttention wheel install failed (exit {e.returncode}).")
            Logger.log(
                "The wheel download may have been blocked by AV/firewall. "
                "Try disabling real-time protection temporarily and re-run.", "info"
            )
            return False

        # 4. Install triton-windows from PyPI
        triton_spec = _triton_spec_for_torch(torch_tuple)
        Logger.log(f"Installing {triton_spec} from PyPI...", "info")
        triton_cmd = [
            str(uv_exe) if uv_exe.exists() else "uv",
            "pip", "install",
            "--no-cache",
            "--python", str(python_exe),
            triton_spec,
        ]
        try:
            subprocess.run(triton_cmd, env=venv_env, check=True)
            Logger.success(f"triton-windows installed.")
        except subprocess.CalledProcessError:
            Logger.warn(
                "triton-windows install failed. SageAttention may still work but "
                "performance will be reduced. You can install it manually later with:\n"
                f"  <venv>\\Scripts\\uv.exe pip install \"{triton_spec}\""
            )

        # Final verification
        if cls.is_installed(python_exe):
            Logger.success("SageAttention verified importable in venv.")
        else:
            Logger.warn(
                "SageAttention wheel was installed but failed to import. "
                "This usually means a vcredist DLL is missing. Install from:\n"
                "  https://aka.ms/vs/17/release/vc_redist.x64.exe"
            )
            return False
        return True

    @classmethod
    def _resolve_sage_wheel_url(cls, cu_tag, uv_exe, venv_env, python_exe):
        """Return the best SageAttention wheel URL for the given CUDA tag.

        Priority:
          1. Latest release from woct0rdho's GitHub API (always current).
          2. Known hardcoded URLs (works if GitHub API is rate-limited / blocked).
        """
        # Hardcoded stable URLs — post4 is the newest as of early 2026.
        # These ABI3 wheels cover torch >= 2.9 and Python >= 3.9 with no pinning.
        _HARDCODED = {
            "cu128": (
                "https://github.com/woct0rdho/SageAttention/releases/download/"
                "v2.2.0-windows.post4/"
                "sageattention-2.2.0+cu128torch2.9.0andhigher.post4"
                "-cp39-abi3-win_amd64.whl"
            ),
            "cu130": (
                "https://github.com/woct0rdho/SageAttention/releases/download/"
                "v2.2.0-windows.post4/"
                "sageattention-2.2.0+cu130torch2.9.0andhigher.post4"
                "-cp39-abi3-win_amd64.whl"
            ),
        }

        # 1. Try the GitHub releases API to get the newest wheel
        url = cls._fetch_latest_sage_wheel_url(cu_tag)
        if url:
            return url

        # 2. Fall back to hardcoded URLs
        url = _HARDCODED.get(cu_tag)
        if url:
            Logger.log(
                f"Using hardcoded fallback URL for {cu_tag} (GitHub API unavailable).",
                "info"
            )
            return url

        Logger.error(
            f"No SageAttention wheel found for {cu_tag}. "
            f"Supported: cu128 (CUDA 12.8) and cu130 (CUDA 13.0).\n"
            f"If you have a different CUDA version, check:\n"
            f"  https://github.com/woct0rdho/SageAttention/releases"
        )
        return None

    @staticmethod
    def _fetch_latest_sage_wheel_url(cu_tag):
        """Query the woct0rdho/SageAttention GitHub releases API and return
        the URL of the most recent 'andhigher' ABI3 wheel matching cu_tag.
        Returns None on any failure."""
        api = "https://api.github.com/repos/woct0rdho/SageAttention/releases?per_page=5"
        headers = {
            "User-Agent": "DaSiWa-Installer/1.0",
            "Accept": "application/vnd.github+json",
            "Connection": "close",
        }
        # Target pattern: the ABI3 'andhigher' wheel — this is the one that works
        # for any torch >= 2.9 without version pinning.
        pat = re.compile(
            rf"sageattention-.*\+{re.escape(cu_tag)}torch.*andhigher.*-cp39-abi3-win_amd64\.whl",
            re.IGNORECASE,
        )
        for attempt in range(1, 4):
            try:
                req = urllib.request.Request(api, headers=headers)
                with urllib.request.urlopen(req, timeout=20) as r:
                    releases = json.loads(r.read().decode())
                for rel in releases:
                    for asset in rel.get("assets", []):
                        if pat.match(asset.get("name", "")):
                            Logger.log(
                                f"Latest SageAttention wheel: {asset['name']}", "ok"
                            )
                            return asset["browser_download_url"]
                Logger.warn(f"No matching ABI3 '{cu_tag}' wheel found in latest releases.")
                return None
            except Exception as e:
                if attempt < 3:
                    Logger.debug(
                        f"GitHub API attempt {attempt}/3 failed ({type(e).__name__}); "
                        f"retrying in {attempt * 2}s..."
                    )
                    time.sleep(attempt * 2)
        Logger.warn("Could not reach GitHub releases API after 3 attempts.")
        return None

    # ------------------------------------------------------------------ #
    #  Torch probe helper                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _probe_torch(python_exe):
        """Return (torch_version, cuda_version, python_mm) from the venv.
        All values are strings like '2.10.0', '12.8', '3.12'.
        Returns (None, None, None) on failure."""
        try:
            res = subprocess.run(
                [str(python_exe), "-c",
                 "import torch, sys; "
                 "print(torch.__version__.split('+')[0]); "
                 "print(torch.version.cuda or ''); "
                 "print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                capture_output=True, text=True, check=True, timeout=30,
            )
            lines = res.stdout.strip().splitlines()
            if len(lines) < 3:
                return None, None, None
            return lines[0].strip(), lines[1].strip(), lines[2].strip()
        except Exception as e:
            Logger.warn(f"torch probe failed: {e}")
            return None, None, None

    @staticmethod
    def _parse_ver(v):
        """'2.10.0' -> (2, 10, 0). Tolerant of extra suffixes."""
        try:
            return tuple(int(x) for x in v.split(".") if x.isdigit())
        except Exception:
            return (0,)

    # ------------------------------------------------------------------ #
    #  Linux source build (unchanged)                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def check_nvcc():
        try:
            subprocess.run(["nvcc", "--version"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False

    @staticmethod
    def check_cpp_compiler():
        for compiler in ("g++", "clang++"):
            try:
                subprocess.run([compiler, "--version"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               check=True)
                return True
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
        return False

    @staticmethod
    def _install_system_dependencies(config_urls):
        has_nvcc = SageInstaller.check_nvcc()
        has_cpp  = SageInstaller.check_cpp_compiler()
        if has_nvcc and has_cpp:
            Logger.log("Build dependencies (nvcc + g++) detected.", "ok")
            return True

        Logger.section("SageAttention: missing build dependencies")
        if not has_nvcc: Logger.warn("nvcc (CUDA Toolkit) NOT found.")
        if not has_cpp:  Logger.warn("g++ / clang++ NOT found.")

        options = [
            ("[Ubuntu/Debian] sudo apt install build-essential cmake", None),
            ("[Arch] sudo pacman -Sy base-devel cmake", None),
            ("Skip check and try building anyway", "risky"),
            ("Cancel SageAttention", None),
        ]
        idx = Logger.ask_choice(
            "How do you want to resolve build dependencies?",
            options, default_index=len(options) - 1,
        )
        try:
            if idx == 0:
                subprocess.run(["sudo", "apt", "update"], check=True)
                subprocess.run(
                    ["sudo", "apt", "install", "-y", "build-essential", "cmake", "git"],
                    check=True,
                )
                return True
            if idx == 1:
                subprocess.run(
                    ["sudo", "pacman", "-Sy", "--needed", "base-devel", "cmake", "git"],
                    check=True,
                )
                return True
            if idx == 2:
                return True   # skip check
        except subprocess.CalledProcessError as e:
            Logger.error(f"Package install failed: {e}")
        return False

    @classmethod
    def _source_build(cls, venv_env, comfy_path, config_urls, python_exe):
        sage_dir = Path(comfy_path) / "SageAttention"
        repo_url = config_urls.get("sage_repo", "https://github.com/thu-ml/SageAttention.git")

        if not sage_dir.exists():
            Logger.log(f"Cloning SageAttention...", "info")
            subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(sage_dir)],
                check=True,
            )
        else:
            Logger.log("Updating SageAttention clone...", "info")
            subprocess.run(
                ["git", "-C", str(sage_dir), "fetch", "--all", "--tags"], check=False,
            )
            subprocess.run(
                ["git", "-C", str(sage_dir), "reset", "--hard", "origin/HEAD"],
                check=False,
            )

        build_env = venv_env.copy()
        cpu = os.cpu_count() or 4
        build_env["MAX_JOBS"] = str(min(cpu, 4))
        build_env["EXT_PARALLEL"] = "2"

        orig = os.getcwd()
        os.chdir(sage_dir)
        build_ok = False
        try:
            Logger.log("Building SageAttention from source...", "info")
            subprocess.run(
                ["uv", "pip", "install",
                 "--python", str(python_exe),
                 "--no-build-isolation", "."],
                env=build_env, check=True,
            )
            Logger.success("SageAttention built and installed from source.")
            build_ok = True
        except subprocess.CalledProcessError as e:
            Logger.error(f"Source build failed (exit {e.returncode}).")
        finally:
            os.chdir(orig)

        # Remove the source clone — it's only needed for the build, not at runtime.
        # Skip on failure so the user can inspect or retry manually.
        if build_ok and sage_dir.exists():
            try:
                shutil.rmtree(sage_dir, ignore_errors=True)
                Logger.debug("SageAttention source clone removed (no longer needed).")
            except Exception as e:
                Logger.debug(f"Could not remove SageAttention source clone: {e}")
