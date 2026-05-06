"""
RadialAttention installer.

RadialAttention is a sparse-attention add-on that runs on top of SpargeAttention
(also known as SparseSageAttention; pypi name `spas_sage_attn`). It is exposed
to ComfyUI via the woct0rdho/ComfyUI-RadialAttn custom node.

Install layout:
  Windows: prebuilt ABI3 wheel from woct0rdho/SpargeAttn releases.
  Linux:   source build of woct0rdho/SpargeAttn (same fork, ABI3 + torch.compile
           support not present in upstream thu-ml/SpargeAttn).
  Both:    git clone ComfyUI-RadialAttn into ComfyUI/custom_nodes/.

The official ComfyUI-RadialAttn README also recommends installing SageAttention
alongside as a fallback. The wizard in setup_logic.py forces want_sage = True
when want_radial is selected, so by the time this module runs Sage is already
installed (or attempted) by SageInstaller.
"""

import json
import os
import platform
import re
import subprocess
import time
import urllib.request
from pathlib import Path

from utils.logger import Logger
from utils import cuda_host


_DEFAULT_SPARGE_REPO = "https://github.com/woct0rdho/SpargeAttn.git"
_DEFAULT_RADIAL_NODE_REPO = "https://github.com/woct0rdho/ComfyUI-RadialAttn.git"
_SPARGE_RELEASES_API = (
    "https://api.github.com/repos/woct0rdho/SpargeAttn/releases?per_page=5"
)
# post4 is the newest as of early 2026. ABI3 + libtorch stable ABI:
# covers torch >= 2.9 and Python >= 3.9 with no version pinning.
_SPARGE_HARDCODED_WHEELS = {
    "cu128": (
        "https://github.com/woct0rdho/SpargeAttn/releases/download/"
        "v0.1.0-windows.post4/"
        "spas_sage_attn-0.1.0+cu128torch2.9.0andhigher.post4"
        "-cp39-abi3-win_amd64.whl"
    ),
    "cu130": (
        "https://github.com/woct0rdho/SpargeAttn/releases/download/"
        "v0.1.0-windows.post4/"
        "spas_sage_attn-0.1.0+cu130torch2.9.0andhigher.post4"
        "-cp39-abi3-win_amd64.whl"
    ),
}


class RadialInstaller:

    # ------------------------------------------------------------------ #
    #  Public helpers                                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def is_kernel_installed(python_exe):
        """Return True if spas_sage_attn is importable in the target venv."""
        try:
            res = subprocess.run(
                [str(python_exe), "-c", "import spas_sage_attn"],
                capture_output=True, text=True, timeout=30,
            )
            return res.returncode == 0
        except Exception:
            return False

    @staticmethod
    def is_node_installed(comfy_path):
        """Return True if ComfyUI-RadialAttn is already cloned."""
        node_dir = Path(comfy_path) / "custom_nodes" / "ComfyUI-RadialAttn"
        return node_dir.exists() and (node_dir / "__init__.py").exists()

    @classmethod
    def is_installed(cls, python_exe, comfy_path):
        """RadialAttention is considered installed when both the kernel
        backend and the node repo are present."""
        return cls.is_kernel_installed(python_exe) and cls.is_node_installed(comfy_path)

    # ------------------------------------------------------------------ #
    #  Main public entry point                                             #
    # ------------------------------------------------------------------ #

    @classmethod
    def install(cls, venv_env, comfy_path, config_urls):
        """Install SpargeAttention kernel + ComfyUI-RadialAttn node."""
        is_win = platform.system() == "Windows"
        venv_root = Path(venv_env.get("VIRTUAL_ENV", ""))
        python_exe = venv_root / ("Scripts/python.exe" if is_win else "bin/python")
        uv_exe     = venv_root / ("Scripts/uv.exe"    if is_win else "bin/uv")

        if not python_exe.exists():
            Logger.error(f"Could not find venv Python at {python_exe}")
            return

        # 1. Kernel: SpargeAttention
        if cls.is_kernel_installed(python_exe):
            Logger.log("SpargeAttention already installed - skipping kernel.", "ok")
        else:
            if is_win:
                cls._install_sparge_windows(python_exe, uv_exe, venv_env)
            else:
                cls._install_sparge_linux(venv_env, comfy_path, config_urls, python_exe)

        # 2. Custom node: ComfyUI-RadialAttn
        cls._install_radial_node(venv_env, comfy_path, config_urls)

    # ------------------------------------------------------------------ #
    #  Windows: prebuilt SpargeAttention wheel                             #
    # ------------------------------------------------------------------ #

    @classmethod
    def _install_sparge_windows(cls, python_exe, uv_exe, venv_env):
        """Install SpargeAttention on Windows using the prebuilt ABI3 wheel
        from woct0rdho/SpargeAttn. Strategy mirrors SageInstaller._install_windows.
        """
        # 1. Probe installed torch
        torch_ver, torch_cuda, py_mm = cls._probe_torch(python_exe)
        if not torch_ver:
            Logger.error("Could not determine installed torch version. "
                         "Cannot select SpargeAttention wheel.")
            return

        torch_tuple = cls._parse_ver(torch_ver)
        Logger.log(
            f"Detected: torch {torch_ver}, CUDA {torch_cuda}, Python {py_mm}", "info"
        )

        if torch_tuple < (2, 9):
            Logger.warn(
                f"Torch {torch_ver} is older than 2.9. The prebuilt ABI3 "
                f"SpargeAttention wheel requires torch >= 2.9. Skipping."
            )
            return

        cu_tag = "cu" + torch_cuda.replace(".", "")

        # 2. Resolve wheel URL (live API first, hardcoded fallback)
        sparge_url = cls._resolve_sparge_wheel_url(cu_tag)
        if not sparge_url:
            return

        # 3. Install wheel
        Logger.log("Installing SpargeAttention from prebuilt wheel...", "info")
        Logger.log(f"  {sparge_url.rsplit('/', 1)[-1]}", "debug")

        install_env = venv_env.copy()
        # uv rejects the 'torch2.9.0andhigher' token in the wheel filename
        # as invalid PEP 427 - this flag bypasses that check.
        install_env["UV_SKIP_WHEEL_FILENAME_CHECK"] = "1"

        cmd = [
            str(uv_exe) if uv_exe.exists() else "uv",
            "pip", "install",
            "--force-reinstall",
            "--no-cache",
            "--python", str(python_exe),
            sparge_url,
        ]
        try:
            subprocess.run(cmd, env=install_env, check=True)
            Logger.success("SpargeAttention installed.")
        except subprocess.CalledProcessError as e:
            Logger.error(
                f"SpargeAttention wheel install failed (exit {e.returncode})."
            )
            Logger.log(
                "The wheel download may have been blocked by AV/firewall. "
                "Try disabling real-time protection temporarily and re-run.", "info"
            )
            return

        if cls.is_kernel_installed(python_exe):
            Logger.success("SpargeAttention verified importable in venv.")
        else:
            Logger.warn(
                "SpargeAttention wheel was installed but failed to import. "
                "This usually means a vcredist DLL is missing. Install from:\n"
                "  https://aka.ms/vs/17/release/vc_redist.x64.exe"
            )

    @classmethod
    def _resolve_sparge_wheel_url(cls, cu_tag):
        """Return the best SpargeAttention wheel URL for the given CUDA tag.

        Priority:
          1. Latest release from woct0rdho's GitHub API (always current).
          2. Hardcoded URLs (works if GitHub API is rate-limited / blocked).
        """
        url = cls._fetch_latest_sparge_wheel_url(cu_tag)
        if url:
            return url

        url = _SPARGE_HARDCODED_WHEELS.get(cu_tag)
        if url:
            Logger.log(
                f"Using hardcoded fallback URL for {cu_tag} (GitHub API unavailable).",
                "info"
            )
            return url

        Logger.error(
            f"No SpargeAttention wheel found for {cu_tag}. "
            f"Supported: cu128 (CUDA 12.8) and cu130 (CUDA 13.0).\n"
            f"If you have a different CUDA version, check:\n"
            f"  https://github.com/woct0rdho/SpargeAttn/releases"
        )
        return None

    @staticmethod
    def _fetch_latest_sparge_wheel_url(cu_tag):
        """Query the woct0rdho/SpargeAttn GitHub releases API and return
        the URL of the most recent 'andhigher' ABI3 wheel matching cu_tag.
        Returns None on any failure."""
        headers = {
            "User-Agent": "DaSiWa-Installer/1.0",
            "Accept": "application/vnd.github+json",
            "Connection": "close",
        }
        # Pattern: ABI3 'andhigher' wheel - works for any torch >= 2.9 unpinned.
        pat = re.compile(
            rf"spas_sage_attn-.*\+{re.escape(cu_tag)}torch.*andhigher.*"
            rf"-cp39-abi3-win_amd64\.whl",
            re.IGNORECASE,
        )
        for attempt in range(1, 4):
            try:
                req = urllib.request.Request(_SPARGE_RELEASES_API, headers=headers)
                with urllib.request.urlopen(req, timeout=20) as r:
                    releases = json.loads(r.read().decode())
                for rel in releases:
                    for asset in rel.get("assets", []):
                        if pat.match(asset.get("name", "")):
                            Logger.log(
                                f"Latest SpargeAttention wheel: {asset['name']}", "ok"
                            )
                            return asset["browser_download_url"]
                Logger.warn(
                    f"No matching ABI3 '{cu_tag}' wheel found in latest releases."
                )
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
    #  Linux: source build of SpargeAttention                              #
    # ------------------------------------------------------------------ #

    @classmethod
    def _install_sparge_linux(cls, venv_env, comfy_path, config_urls, python_exe):
        sparge_dir = Path(comfy_path) / "SpargeAttn"
        repo_url = config_urls.get("sparge_repo", _DEFAULT_SPARGE_REPO)

        if not sparge_dir.exists():
            Logger.log("Cloning SpargeAttention...", "info")
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", repo_url, str(sparge_dir)],
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                Logger.error(f"git clone failed: {e}")
                return
        else:
            Logger.log("Updating SpargeAttention clone...", "info")
            subprocess.run(
                ["git", "-C", str(sparge_dir), "fetch", "--all", "--tags"],
                check=False,
            )
            subprocess.run(
                ["git", "-C", str(sparge_dir), "reset", "--hard", "origin/HEAD"],
                check=False,
            )

        build_env = venv_env.copy()
        cpu = os.cpu_count() or 4
        build_env["MAX_JOBS"] = str(min(cpu, 4))
        build_env["EXT_PARALLEL"] = "2"

        # Resolve nvcc/host-compiler mismatch (same as Sage source build).
        status, info_a, info_b = cuda_host.apply_host_compiler_to_env(build_env)
        if status == "incompatible":
            cuda_host.print_host_compiler_hint(
                cuda_host.probe_nvcc_version(), info_a, info_b,
            )
            Logger.error(
                "Aborting SpargeAttention source build to avoid a guaranteed "
                "compile failure."
            )
            return

        orig = os.getcwd()
        os.chdir(sparge_dir)
        try:
            Logger.log("Building SpargeAttention from source...", "info")
            subprocess.run(
                ["uv", "pip", "install",
                 "--python", str(python_exe),
                 "--no-build-isolation", "."],
                env=build_env, check=True,
            )
            Logger.success("SpargeAttention built and installed from source.")
        except subprocess.CalledProcessError as e:
            Logger.error(f"Source build failed (exit {e.returncode}).")
        finally:
            os.chdir(orig)

    # ------------------------------------------------------------------ #
    #  Custom node: ComfyUI-RadialAttn                                     #
    # ------------------------------------------------------------------ #

    @classmethod
    def _install_radial_node(cls, venv_env, comfy_path, config_urls):
        repo_url = config_urls.get("radial_node_repo", _DEFAULT_RADIAL_NODE_REPO)
        nodes_dir = Path(comfy_path) / "custom_nodes"
        nodes_dir.mkdir(parents=True, exist_ok=True)
        node_dir = nodes_dir / "ComfyUI-RadialAttn"

        git_env = venv_env.copy()
        git_env["GIT_TERMINAL_PROMPT"] = "0"

        try:
            if not node_dir.exists():
                Logger.log("Cloning ComfyUI-RadialAttn...", "info")
                subprocess.run(
                    ["git", "clone", "--recursive", repo_url, str(node_dir)],
                    env=git_env, check=True,
                )
            else:
                Logger.log("Updating ComfyUI-RadialAttn...", "info")
                subprocess.run(
                    ["git", "-C", str(node_dir), "pull"],
                    env=git_env, check=False,
                )
            Logger.success("ComfyUI-RadialAttn ready.")
        except subprocess.CalledProcessError as e:
            Logger.error(f"ComfyUI-RadialAttn clone failed (exit {e.returncode}).")

    # ------------------------------------------------------------------ #
    #  Torch probe (shared with SageInstaller pattern; kept local to     #
    #  avoid a cross-module dependency on a private method)              #
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
