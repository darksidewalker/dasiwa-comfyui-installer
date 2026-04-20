import os
import platform
import subprocess
import shutil
import json
import re
import urllib.request
import ctypes
from pathlib import Path

from utils.logger import Logger


class SageInstaller:
    # ---------- Small helpers ----------

    @staticmethod
    def get_input(prompt):
        return input(prompt)

    @staticmethod
    def is_installed(python_exe):
        """Check whether sageattention is already importable in the target venv."""
        try:
            res = subprocess.run(
                [str(python_exe), "-c",
                 "import sageattention,sys; "
                 "print(getattr(sageattention,'__version__','installed'))"],
                capture_output=True, text=True, timeout=30,
            )
            return res.returncode == 0
        except Exception:
            return False

    # ---------- Dependency probes ----------

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
        """
        On Windows, a working MSVC environment requires more than cl.exe on PATH —
        we need vcvars64.bat to exist so nvcc can load the full env.
        """
        if platform.system() == "Windows":
            return SageInstaller._find_vcvars() is not None

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
    def _find_vcvars():
        """Locate vcvars64.bat across VS 2017/2019/2022 (Community/Pro/Enterprise/BuildTools)."""
        vswhere = (
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
        )
        if vswhere.exists():
            try:
                res = subprocess.run(
                    [str(vswhere), "-latest", "-products", "*",
                     "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                     "-property", "installationPath", "-format", "value"],
                    capture_output=True, text=True, check=True,
                )
                root = res.stdout.strip()
                if root:
                    candidate = Path(root) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
                    if candidate.exists():
                        return candidate
            except Exception:
                pass

        # Hard fallback: scan the usual install locations
        roots = [
            r"C:\Program Files\Microsoft Visual Studio",
            r"C:\Program Files (x86)\Microsoft Visual Studio",
        ]
        for root in roots:
            root_p = Path(root)
            if not root_p.exists():
                continue
            for year in ("2022", "2019", "2017"):
                for edition in ("Enterprise", "Professional", "Community", "BuildTools"):
                    candidate = (root_p / year / edition / "VC" / "Auxiliary"
                                 / "Build" / "vcvars64.bat")
                    if candidate.exists():
                        return candidate
        return None

    @staticmethod
    def _find_cuda_home():
        """Locate a working CUDA toolkit root."""
        for var in ("CUDA_HOME", "CUDA_PATH"):
            v = os.environ.get(var)
            if v and Path(v).exists():
                return Path(v)

        nvcc = shutil.which("nvcc")
        if nvcc:
            return Path(nvcc).parent.parent  # <cuda>/bin/nvcc(.exe) -> <cuda>

        standard = Path(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA")
        if standard.exists():
            versions = sorted(
                (d for d in standard.iterdir() if d.is_dir() and d.name.startswith("v")),
                key=lambda d: d.name, reverse=True,
            )
            if versions:
                return versions[0]
        return None

    @staticmethod
    def _load_msvc_env(vcvars_path):
        """Run vcvars64.bat in a subshell and capture the resulting env."""
        try:
            res = subprocess.run(
                f'cmd /s /c ""{vcvars_path}" >nul 2>&1 && set"',
                shell=True, capture_output=True, text=True, check=True,
            )
        except subprocess.CalledProcessError as e:
            Logger.warn(f"vcvars64.bat failed: {e}")
            return None

        env = os.environ.copy()
        for line in res.stdout.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                env[k] = v
        return env

    @staticmethod
    def _estimate_max_jobs():
        """Pick MAX_JOBS based on CPU AND RAM. Overridable via DASIWA_SAGE_MAX_JOBS."""
        if os.environ.get("DASIWA_SAGE_MAX_JOBS"):
            return os.environ["DASIWA_SAGE_MAX_JOBS"]
        cpu = os.cpu_count() or 4
        gb = 16.0
        try:
            if platform.system() == "Windows":
                class MEMSTAT(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]
                stat = MEMSTAT()
                stat.dwLength = ctypes.sizeof(MEMSTAT)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
                gb = stat.ullTotalPhys / (1024 ** 3)
            else:
                with open("/proc/meminfo") as f:
                    content = f.read()
                m = re.search(r"MemTotal:\s+(\d+)", content)
                if m:
                    gb = int(m.group(1)) / (1024 ** 2)
        except Exception:
            pass
        # Each linker job peaks ~2.5–3 GB; be conservative.
        jobs_by_ram = max(1, int(gb // 3))
        return str(min(cpu, jobs_by_ram))

    # ---------- Dependency menu ----------

    @staticmethod
    def install_system_dependencies(config_urls):
        os_type = platform.system()
        has_nvcc = SageInstaller.check_nvcc()
        has_cpp = SageInstaller.check_cpp_compiler()

        if has_nvcc and has_cpp:
            Logger.log("All build dependencies (NVCC & C++ Compiler) detected.", "ok")
            return True

        Logger.section("SageAttention Dependency Check")
        if not has_nvcc:
            Logger.warn("CUDA Toolkit (nvcc) NOT found.")
        if not has_cpp:
            Logger.warn("C++ Compiler (MSVC/GCC) NOT found.")

        options = []
        if os_type == "Windows":
            options.append(("[Windows] Open MSVC Build Tools download page", None))
        elif os_type == "Linux":
            options.append(("[Ubuntu/Debian] Install build-essential & cmake (sudo)", None))
            options.append(("[Arch] Install base-devel & cmake (sudo)", None))
        options.append(("Skip check and try building anyway", "Risky — may fail"))
        options.append(("Cancel SageAttention installation", None))

        idx = Logger.ask_choice("How do you want to resolve build dependencies?",
                                options, default_index=len(options) - 1)

        if os_type == "Windows":
            if idx == 0:
                import webbrowser
                webbrowser.open(config_urls.get("msvc_build_tools", ""))
                Logger.log("Install 'Desktop development with C++' and restart the terminal.",
                           "info")
                return False
            if idx == 1:  # skip
                return True
            return False  # cancel
        elif os_type == "Linux":
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
                if idx == 2:  # skip
                    return True
            except subprocess.CalledProcessError as e:
                Logger.error(f"Package install failed: {e}")
                return False
            return False  # cancel
        return False

    # ---------- Public entry point ----------

    @classmethod
    def build_sage(cls, venv_env, comfy_path, config_urls):
        """Install SageAttention: prefer prebuilt wheel, fall back to source build."""
        venv_root = Path(venv_env.get("VIRTUAL_ENV", ""))
        is_win = platform.system() == "Windows"
        python_exe = venv_root / ("Scripts/python.exe" if is_win else "bin/python")

        if not python_exe.exists():
            Logger.error(f"Could not find ComfyUI venv Python at {python_exe}")
            return

        if cls.is_installed(python_exe):
            Logger.log("SageAttention is already installed in the venv — skipping.", "ok")
            return

        # 1. Prebuilt wheel fast path (Windows only; no upstream wheels for Linux)
        if is_win and cls._try_prebuilt_wheel(python_exe, venv_env):
            return

        # 2. Source build (with hardened env on Windows)
        if not cls.install_system_dependencies(config_urls):
            Logger.log("Dependencies not resolved. Skipping SageAttention build.", "warn")
            return
        cls._source_build(venv_env, comfy_path, config_urls, python_exe, is_win)

    # ---------- Prebuilt wheel path (woct0rdho) ----------

    # Known-good Sage-compatible torch/cuda combos. Used as a fallback when
    # wildminder's wheels.json cannot be fetched (transient 10054 resets, AV TLS
    # inspection, corporate proxy, etc.). Keep this in sync with the newest
    # wheels published at https://huggingface.co/Wildminder/AI-windows-whl
    _FALLBACK_SAGE_COMBOS = {
        # (python_major_minor, cuda_major_minor) -> torch_version
        ("3.12", "12.8"): "2.10.0",
        ("3.12", "13.0"): "2.10.0",
        ("3.13", "12.8"): "2.10.0",
        ("3.13", "13.0"): "2.10.0",
        ("3.11", "12.8"): "2.8.0",
        ("3.10", "12.8"): "2.8.0",
    }

    @classmethod
    def plan_windows_torch(cls, python_display, cuda_target):
        """Called from setup_logic BEFORE torch install on Windows.
        Queries wildminder's wheels.json to find a (torch, cuda) combo that has
        a prebuilt SageAttention wheel for the target Python + cuda_target.
        Falls back to a hardcoded table if the API is unreachable.

        Returns (torch_version, cuda_tag) tuple or (None, None) if nothing matches.
        """
        py_mm = ".".join(str(python_display).split(".")[:2])
        try:
            cu_major_minor = ".".join(cuda_target.split(".")[:2])
        except Exception:
            cu_major_minor = cuda_target
        cu_tag = "cu" + cu_major_minor.replace(".", "")

        wheels = cls._fetch_wildminder_wheels()

        # Live path: query wheels.json and pick the newest matching combo
        if wheels:
            sage_pkg = next((p for p in wheels.get("packages", [])
                             if p.get("id") == "sageattention"), None)
            if sage_pkg:
                candidates = []
                for w in sage_pkg.get("wheels", []):
                    w_py = str(w.get("python_version", ""))
                    w_cu = str(w.get("cuda_version", ""))
                    w_torch = str(w.get("torch_version", ""))
                    py_ok = (w_py == py_mm) or w_py.startswith(">") or w_py == "3.9"
                    cu_ok = (w_cu == cu_major_minor)
                    if py_ok and cu_ok and w_torch:
                        clean_torch = w_torch.lstrip(">")
                        candidates.append((cls._parse_ver(clean_torch), clean_torch, w))

                if candidates:
                    candidates.sort(key=lambda t: t[0], reverse=True)
                    _, chosen_torch, _ = candidates[0]
                    Logger.log(f"Sage-compatible combo: torch {chosen_torch} + {cu_tag} "
                               f"(from wildminder wheels.json)", "ok")
                    return chosen_torch, cu_tag

        # Offline fallback: use the hardcoded known-good table
        fallback_torch = cls._FALLBACK_SAGE_COMBOS.get((py_mm, cu_major_minor))
        if fallback_torch:
            Logger.log(f"Using offline fallback: torch {fallback_torch} + {cu_tag} "
                       f"(known-good Sage combo for Python {py_mm})", "ok")
            return fallback_torch, cu_tag

        Logger.warn(f"No known Sage-compatible torch pin for Python {py_mm} + "
                    f"CUDA {cu_major_minor}. Torch will not be pinned, and Sage "
                    f"may fail to find a prebuilt wheel.")
        return None, None

    @staticmethod
    def _parse_ver(v):
        """Parse '2.8.0' -> (2, 8, 0). Handles garbage gracefully."""
        try:
            return tuple(int(x) for x in v.split(".") if x.isdigit())
        except Exception:
            return (0,)

    @staticmethod
    def _fetch_wildminder_wheels():
        """Fetch wildminder/AI-windows-whl wheels.json with retries and mirrors.
        Cached for this process."""
        import time
        if hasattr(SageInstaller, "_wheels_cache"):
            return SageInstaller._wheels_cache

        # Two mirrors for the same wheels.json — one or the other tends to work
        # when corporate firewalls / AV TLS inspection drop the first attempt.
        mirrors = [
            "https://raw.githubusercontent.com/wildminder/AI-windows-whl/main/wheels.json",
            "https://huggingface.co/Wildminder/AI-windows-whl/raw/main/wheels.json",
        ]
        headers = {
            "User-Agent": "DaSiWa-Installer/1.0",
            "Accept": "application/json, text/plain, */*",
            # Some AV/firewall proxies break HTTPS keep-alive; force a fresh
            # connection per request to avoid stale socket reuse.
            "Connection": "close",
        }

        last_err = None
        for mirror in mirrors:
            for attempt in range(1, 4):
                try:
                    req = urllib.request.Request(mirror, headers=headers)
                    with urllib.request.urlopen(req, timeout=30) as r:
                        data = json.loads(r.read().decode())
                    SageInstaller._wheels_cache = data
                    return data
                except Exception as e:
                    last_err = e
                    if attempt < 3:
                        Logger.debug(f"wheels.json fetch attempt {attempt}/3 failed "
                                     f"({type(e).__name__}); retrying in {attempt * 2}s...")
                        time.sleep(attempt * 2)
            Logger.debug(f"Mirror failed: {mirror}")

        Logger.warn(f"Could not fetch wildminder wheels.json after retries: {last_err}")
        Logger.log("This is usually a transient connection reset from AV/firewall "
                   "TLS inspection. SageAttention install will fall back to the "
                   "source-build path (slower but works offline).", "info")
        SageInstaller._wheels_cache = None
        return None

    @classmethod
    def _try_prebuilt_wheel(cls, python_exe, venv_env):
        """Find and install a matching prebuilt wheel. Tries wildminder's
        wheels.json first (handles torch 2.8–2.10+), then falls back to the
        woct0rdho GitHub releases API for older combos. Returns True on success."""
        # 1. Probe the installed torch
        try:
            probe = subprocess.run(
                [str(python_exe), "-c",
                 "import torch,sys;"
                 "print(torch.__version__);"
                 "print(torch.version.cuda or '')"],
                capture_output=True, text=True, check=True, timeout=30,
            )
            lines = probe.stdout.strip().splitlines()
            torch_ver = lines[0].strip() if lines else ""
            torch_cuda = lines[1].strip() if len(lines) > 1 else ""
        except Exception as e:
            Logger.warn(f"Could not probe torch version: {e}")
            return False

        if not torch_ver or not torch_cuda:
            Logger.log("Torch has no CUDA — skipping prebuilt SageAttention wheel.", "warn")
            return False

        # Get python major.minor from the venv Python
        try:
            py_probe = subprocess.run(
                [str(python_exe), "-c",
                 "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                capture_output=True, text=True, check=True, timeout=10,
            )
            py_mm = py_probe.stdout.strip()
        except Exception:
            py_mm = "3.12"

        # Normalise torch version: keep major.minor.patch (no +cuXXX suffix)
        torch_clean = torch_ver.split("+")[0]
        torch_mm = ".".join(torch_clean.split(".")[:2])

        # Normalise CUDA: '12.8' -> 'cu128'
        cu_tag = f"cu{torch_cuda.replace('.', '')}"
        cu_mm = ".".join(torch_cuda.split(".")[:2])

        Logger.log(f"Looking for prebuilt SageAttention wheel for "
                   f"Python {py_mm} + torch {torch_clean} + {cu_tag}...", "info")

        # 2. Try wildminder wheels.json (authoritative, covers newest combos)
        wheel_url = cls._select_from_wildminder(py_mm, torch_clean, torch_mm, cu_mm)

        # 3. Fall back to woct0rdho release API (uses api.github.com, different endpoint)
        if not wheel_url:
            wheel_url = cls._select_from_woct0rdho(torch_mm, cu_tag)

        # 4. Last-resort hardcoded table (works fully offline for common combos)
        if not wheel_url:
            wheel_url = cls._select_from_fallback_table(py_mm, torch_mm, cu_mm)

        if not wheel_url:
            Logger.warn(f"No prebuilt wheel found for torch {torch_clean} / {cu_tag} / Python {py_mm}. "
                        f"Will build from source.")
            return False

        Logger.log(f"Installing prebuilt wheel: {wheel_url.rsplit('/', 1)[-1].split('?')[0]}",
                   "info")
        try:
            subprocess.run(
                ["uv", "pip", "install", "--python", str(python_exe), wheel_url],
                env=venv_env, check=True,
            )
            Logger.success("SageAttention installed from prebuilt wheel.")
            return True
        except subprocess.CalledProcessError as e:
            Logger.warn(f"Prebuilt wheel install failed: {e}. Falling back to source build.")
            return False

    @classmethod
    def _select_from_wildminder(cls, py_mm, torch_full, torch_mm, cu_mm):
        """Return best-matching SageAttention wheel URL from wheels.json, or None.
        A wheel is only considered a match if BOTH the torch version family and
        the CUDA version match. Python match can be exact or ABI3."""
        wheels = cls._fetch_wildminder_wheels()
        if not wheels:
            return None
        sage = next((p for p in wheels.get("packages", [])
                     if p.get("id") == "sageattention"), None)
        if not sage:
            return None

        best = None
        best_score = -1
        for w in sage.get("wheels", []):
            w_py = str(w.get("python_version", ""))
            w_cu = str(w.get("cuda_version", ""))
            w_torch = str(w.get("torch_version", ""))

            # MANDATORY: CUDA must match exactly
            if w_cu != cu_mm:
                continue

            # MANDATORY: torch major.minor must match, OR wheel declares ">=installed"
            w_torch_clean = w_torch.lstrip(">")
            if w_torch_clean == torch_full:
                torch_score = 50
            elif w_torch_clean == torch_mm:
                torch_score = 40
            elif w_torch_clean.startswith(torch_mm + "."):
                torch_score = 30
            elif w_torch.startswith(">") and cls._parse_ver(torch_full) >= cls._parse_ver(w_torch_clean):
                # ">2.9.0" wheel accepts anything >= 2.9.0
                torch_score = 20
            else:
                continue  # torch mismatch — don't risk it

            # Python match: exact > ABI3 > skip
            if w_py == py_mm:
                py_score = 10
            elif w_py.startswith(">") or w_py == "3.9":
                # ABI3 wheels declare "3.9" or ">3.9" and work for 3.9+
                py_score = 5
            else:
                continue

            score = 100 + torch_score + py_score
            if score > best_score:
                best_score = score
                best = w

        return best["url"] if best else None

    # Last-resort hardcoded SageAttention wheel URLs when both wildminder
    # wheels.json and woct0rdho's GitHub API are unreachable. These URLs were
    # verified from wildminder's wheels.json and point at HuggingFace-hosted
    # wheels that do not require the GitHub API to resolve. Keep in sync with
    # https://huggingface.co/Wildminder/AI-windows-whl
    _FALLBACK_SAGE_WHEELS = {
        # (python_major_minor, torch_major_minor, cuda_major_minor) -> URL
        ("3.12", "2.10", "12.8"):
            "https://huggingface.co/Wildminder/AI-windows-whl/resolve/main/"
            "sageattention-2.2.0.post3+cu128torch2.10.0-cp312-cp312-win_amd64.whl",
        ("3.12", "2.10", "13.0"):
            "https://huggingface.co/Wildminder/AI-windows-whl/resolve/main/"
            "sageattention-2.2.0.post3+cu130torch2.10.0-cp312-cp312-win_amd64.whl",
        ("3.13", "2.10", "12.8"):
            "https://huggingface.co/Wildminder/AI-windows-whl/resolve/main/"
            "sageattention-2.2.0.post3+cu128torch2.10.0-cp313-cp313-win_amd64.whl",
        ("3.13", "2.10", "13.0"):
            "https://huggingface.co/Wildminder/AI-windows-whl/resolve/main/"
            "sageattention-2.2.0.post3+cu130torch2.10.0-cp313-cp313-win_amd64.whl",
        ("3.13", "2.9", "12.8"):
            "https://huggingface.co/Wildminder/AI-windows-whl/resolve/main/"
            "sageattention-2.2.0.post3+cu128torch2.9.0-cp313-cp313-win_amd64.whl",
    }

    @classmethod
    def _select_from_fallback_table(cls, py_mm, torch_mm, cu_mm):
        """Return a hardcoded wheel URL if one exists for this exact combo."""
        url = cls._FALLBACK_SAGE_WHEELS.get((py_mm, torch_mm, cu_mm))
        if url:
            Logger.log(f"Using offline fallback wheel URL (py{py_mm} torch{torch_mm} cu{cu_mm})",
                       "ok")
        return url

    @classmethod
    def _select_from_woct0rdho(cls, torch_mm, cu_tag):
        """Fallback: query GitHub releases API for woct0rdho/SageAttention."""
        api = "https://api.github.com/repos/woct0rdho/SageAttention/releases?per_page=10"
        try:
            req = urllib.request.Request(
                api, headers={"User-Agent": "DaSiWa-Installer/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                releases = json.loads(r.read().decode())
        except Exception as e:
            Logger.warn(f"GitHub API unreachable ({e}).")
            return None

        # Prefer ABI3 wheel, then any matching win_amd64 wheel
        abi3_pat = re.compile(
            rf"sageattention-.*\+{re.escape(cu_tag)}torch{re.escape(torch_mm)}\..*"
            rf"-cp39-abi3-win_amd64\.whl"
        )
        exact_pat = re.compile(
            rf"sageattention-.*\+{re.escape(cu_tag)}torch{re.escape(torch_mm)}\..*"
            rf"-win_amd64\.whl"
        )
        for pat in (abi3_pat, exact_pat):
            for rel in releases:
                for asset in rel.get("assets", []):
                    if pat.match(asset.get("name", "")):
                        return asset["browser_download_url"]
        return None

    # ---------- Source build ----------

    @classmethod
    def _source_build(cls, venv_env, comfy_path, config_urls, python_exe, is_win):
        sage_dir = Path(comfy_path) / "SageAttention"
        repo_url = config_urls.get("sage_repo")

        if not sage_dir.exists():
            Logger.log(f"Cloning SageAttention into {sage_dir}...", "info")
            subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(sage_dir)],
                check=True,
            )
        else:
            Logger.log("Updating existing SageAttention clone...", "info")
            subprocess.run(
                ["git", "-C", str(sage_dir), "fetch", "--all", "--tags"], check=False,
            )
            subprocess.run(
                ["git", "-C", str(sage_dir), "reset", "--hard", "origin/HEAD"],
                check=False,
            )

        build_env = venv_env.copy()

        if is_win:
            vcvars = cls._find_vcvars()
            if not vcvars:
                Logger.error("Could not locate vcvars64.bat. Install VS 2019/2022 Build Tools "
                             "with 'Desktop development with C++'.")
                return
            Logger.log(f"Loading MSVC environment from {vcvars}...", "info")
            msvc_env = cls._load_msvc_env(vcvars)
            if msvc_env is None:
                Logger.error("Failed to load MSVC environment. Aborting SageAttention build.")
                return
            build_env.update(msvc_env)
            # Re-assert the venv's PATH prefix so we use venv python, not system
            build_env["PATH"] = (
                venv_env.get("PATH", "") + os.pathsep + build_env.get("PATH", "")
            )

            cuda_home = cls._find_cuda_home()
            if not cuda_home:
                Logger.error("Could not locate CUDA Toolkit. Install CUDA 12.x or 13.x.")
                return
            build_env["CUDA_HOME"] = str(cuda_home)
            build_env["CUDA_PATH"] = str(cuda_home)
            build_env["PATH"] = str(cuda_home / "bin") + os.pathsep + build_env["PATH"]
            build_env["DISTUTILS_USE_SDK"] = "1"
            Logger.log(f"CUDA_HOME = {cuda_home}", "ok")

        # Tuning knobs (conservative defaults, overridable)
        build_env["EXT_PARALLEL"] = os.environ.get("DASIWA_SAGE_EXT_PARALLEL", "2")
        build_env["NVCC_APPEND_FLAGS"] = os.environ.get(
            "DASIWA_SAGE_NVCC_THREADS", "--threads 4"
        )
        build_env["MAX_JOBS"] = cls._estimate_max_jobs()
        Logger.log(
            f"Build parallelism: MAX_JOBS={build_env['MAX_JOBS']}, "
            f"EXT_PARALLEL={build_env['EXT_PARALLEL']}", "info",
        )

        original_cwd = os.getcwd()
        os.chdir(sage_dir)
        try:
            Logger.log("Starting SageAttention source build targeting ComfyUI venv...", "info")
            cmd = [
                "uv", "pip", "install",
                "--python", str(python_exe),
                "--no-build-isolation",
                ".",
            ]
            subprocess.run(cmd, env=build_env, check=True)
            Logger.success("SageAttention installed from source.")
        except subprocess.CalledProcessError as e:
            Logger.error(f"SageAttention build failed with exit code {e.returncode}.")
            Logger.log("Common causes on Windows:", "info")
            Logger.log("  - Torch 2.9 + CUDA 13 + MSVC has a known PyTorch header bug",
                       "info")
            Logger.log("    (std ambiguity in compiled_autograd.h). Downgrade cuda.global",
                       "info")
            Logger.log("    to 12.8 in config.local.json, or wait for the upstream fix.",
                       "info")
            Logger.log("  - VS 2025 / VS 17.13+ is unsupported by CUDA 12.x; use VS 2022.",
                       "info")
            Logger.log("  - Verify 'nvcc --version' matches your torch CUDA tag.", "info")
        finally:
            os.chdir(original_cwd)
