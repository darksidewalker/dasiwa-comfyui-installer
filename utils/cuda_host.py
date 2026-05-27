"""
Shared helpers for resolving the host C/C++ compiler that nvcc will use when
building CUDA extensions from source.

Used by:
  - utils.task_sageattention   (SageAttention source build on Linux)
  - utils.task_radialattention (SpargeAttention source build on Linux)

Why this exists
---------------
Modern Linux distributions (e.g. CachyOS, Arch with current rolling toolchain)
ship GCC 16, whose libstdc++ uses C++23 explicit-object-parameter syntax that
nvcc's host parser cannot handle. Each CUDA toolkit version has a documented
maximum supported GCC. When the system default exceeds that, we redirect nvcc
to a side-by-side older g++ via the CC/CXX/NVCC_CCBIN environment variables
(PyTorch's torch.utils.cpp_extension forwards $CC to nvcc as -ccbin).
"""

import os
from pathlib import Path
import re
import shutil
import subprocess

from utils.logger import Logger


# Maximum GCC major version supported by each CUDA major.minor.
# Sources: NVIDIA CUDA Installation Guide for Linux (current and archived).
# Lookup is "latest <= cuda" so newer minors that we don't list inherit
# from the closest known release.
_CUDA_MAX_GCC = {
    (11, 0): 9,  (11, 1): 10, (11, 4): 11,
    (12, 0): 12, (12, 4): 13, (12, 8): 14,
    (13, 0): 15, (13, 1): 15, (13, 2): 15,
}


def max_gcc_for_cuda(cuda_mm):
    """Return max supported GCC major for cuda_mm tuple (major, minor),
    or None if CUDA version unknown."""
    if not cuda_mm:
        return None
    candidates = sorted(k for k in _CUDA_MAX_GCC if k <= cuda_mm)
    if not candidates:
        return None
    return _CUDA_MAX_GCC[candidates[-1]]


def probe_nvcc_version():
    """Return CUDA (major, minor) tuple from `nvcc --version`, or None."""
    try:
        res = subprocess.run(
            ["nvcc", "--version"], capture_output=True, text=True,
            check=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired):
        return None
    m = re.search(r"release\s+(\d+)\.(\d+)", res.stdout)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def probe_gcc_major(executable):
    """Return GCC major version (int) for the given g++ executable, or None."""
    try:
        res = subprocess.run(
            [executable, "-dumpfullversion", "-dumpversion"],
            capture_output=True, text=True, check=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired):
        return None
    for line in res.stdout.splitlines():
        line = line.strip()
        if line and line[0].isdigit():
            try:
                return int(line.split(".")[0])
            except ValueError:
                continue
    return None


def find_host_compiler_for_cuda():
    """Decide whether we need to override the host C/C++ compiler so that
    nvcc accepts it.

    Returns one of:
      ("ok",        None,        None)     -- default toolchain is fine
      ("override",  "/path/gcc", "/path/g++") -- use these via CC/CXX
      ("incompatible", default_gcc_major, max_gcc_major) -- nothing usable found
    """
    cuda_mm = probe_nvcc_version()
    if cuda_mm is None:
        return ("ok", None, None)

    max_gcc = max_gcc_for_cuda(cuda_mm)
    if max_gcc is None:
        return ("ok", None, None)

    default_major = probe_gcc_major("g++")
    if default_major is None:
        return ("ok", None, None)

    if default_major <= max_gcc:
        return ("ok", None, None)

    Logger.warn(
        f"Default g++ is version {default_major}, but CUDA "
        f"{cuda_mm[0]}.{cuda_mm[1]} supports up to GCC {max_gcc}. "
        f"Searching for a compatible toolchain..."
    )

    # Try versioned binaries from highest acceptable downwards.
    for major in range(max_gcc, 10, -1):
        gcc_path  = shutil.which(f"gcc-{major}")
        gxx_path  = shutil.which(f"g++-{major}")
        if gcc_path and gxx_path:
            if probe_gcc_major(gxx_path) == major:
                Logger.log(
                    f"Using gcc-{major} / g++-{major} as nvcc host compiler.",
                    "ok",
                )
                return ("override", gcc_path, gxx_path)

    return ("incompatible", default_major, max_gcc)


def print_host_compiler_hint(cuda_mm, default_major, max_gcc):
    """Tell the user how to install a compatible toolchain."""
    Logger.error(
        f"No compatible host C++ compiler found. Default g++ is "
        f"{default_major}; CUDA {cuda_mm[0]}.{cuda_mm[1]} supports "
        f"up to GCC {max_gcc}."
    )
    Logger.log(
        "Install an older GCC alongside your default and re-run:",
        "info",
    )
    Logger.log(
        f"  Arch / CachyOS:   yay -S gcc{max_gcc}    (or paru -S, AUR)",
        "info",
    )
    Logger.log(
        f"  Ubuntu / Debian:  sudo apt install gcc-{max_gcc} g++-{max_gcc}",
        "info",
    )
    Logger.log(
        f"  Fedora:           sudo dnf install gcc-toolset-{max_gcc}",
        "info",
    )
    Logger.log(
        f"  After install, the binaries 'gcc-{max_gcc}' and 'g++-{max_gcc}' "
        f"must be on PATH.",
        "info",
    )


def check_nvcc(bin_dir=None):
    """Return True if nvcc is on PATH or in standard Arch location."""
    exe_name = "nvcc.exe" if os.name == "nt" else "nvcc"

    # 1. Check local bin_dir (usually the venv bin)
    if bin_dir:
        nvcc_local = Path(bin_dir) / exe_name
        if nvcc_local.exists():
            return True

    # 2. Check PATH first
    if probe_nvcc_version() is not None:
        return True

    # 3. Check environment variables
    for var in ("CUDA_HOME", "CUDA_PATH"):
        val = os.environ.get(var)
        if val:
            p = Path(val) / "bin" / exe_name
            if p.exists():
                return True

    # 4. Fallback for standard system locations
    if os.name == "nt":
        # Windows default: C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\vX.Y\bin
        base = Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA")
        if base.exists():
            # Check for any vXX.X subfolders
            for v_dir in base.glob("v*"):
                if (v_dir / "bin" / "nvcc.exe").exists():
                    return True
    else:
        # Common Linux fallbacks (/opt/cuda is Arch, /usr/local/cuda is Ubuntu/standard)
        fallbacks = ["/opt/cuda/bin/nvcc", "/usr/local/cuda/bin/nvcc"]
        for f in fallbacks:
            if Path(f).exists():
                return True

    return False


def check_cpp_compiler():
    """Return True if g++ or clang++ is on PATH."""
    for compiler in ("g++", "clang++"):
        try:
            subprocess.run(
                [compiler, "--version"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=True
            )
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return False


def install_system_dependencies(component_name, bin_dir=None):
    """Detect distro and offer/install build dependencies.
    Ensures 'cuda' (toolkit) is included for Arch Linux.
    """
    is_win = os.name == "nt"
    has_nvcc = check_nvcc(bin_dir)
    has_cpp  = check_cpp_compiler()
    if has_nvcc and has_cpp:
        return True

    Logger.section(f"{component_name}: missing build dependencies")
    if not has_nvcc: Logger.warn(f"nvcc (CUDA Toolkit) NOT found.{' Source builds require the full NVIDIA CUDA Toolkit on Windows.' if is_win else ''}")
    if not has_cpp:  Logger.warn("g++ / clang++ NOT found.")

    options = [
        ("[Ubuntu/Debian] sudo apt install build-essential cmake nvidia-cuda-toolkit", "apt"),
        ("[Arch/CachyOS] sudo pacman -S base-devel cmake cuda", "pacman"),
        ("Skip check and try building anyway", "risky"),
        (f"Cancel {component_name}", "cancel"),
    ]
    
    if is_win:
        options.insert(0, ("View NVIDIA CUDA Toolkit Download Page", "win_cuda"))
        
    idx = Logger.ask_choice("How do you want to resolve build dependencies?", options, default_index=len(options)-1)
    choice_key = options[idx][1]

    try:
        if choice_key == "apt":
            subprocess.run(["sudo", "apt", "update"], check=True)
            subprocess.run(["sudo", "apt", "install", "-y", "build-essential", "cmake", "git", "nvidia-cuda-toolkit"], check=True)
            return True
        elif choice_key == "pacman":
            subprocess.run(["sudo", "pacman", "-S", "--needed", "base-devel", "cmake", "git", "cuda"], check=True)
            return True
        elif choice_key == "win_cuda":
            import webbrowser
            webbrowser.open("https://developer.nvidia.com/cuda-downloads")
            Logger.info("Please install the toolkit and restart the installer.")
            return False
        elif choice_key == "risky":
            return True
    except subprocess.CalledProcessError as e:
        Logger.error(f"Package install failed: {e}")

    return False


def apply_host_compiler_to_env(build_env):
    """Mutate `build_env` in place with CC/CXX/NVCC_CCBIN if a host-compiler
    override is needed. Returns the status string from
    find_host_compiler_for_cuda() so the caller can short-circuit on
    'incompatible'.

    On status == 'incompatible', the caller must surface the hint and abort.
    """
    status, info_a, info_b = find_host_compiler_for_cuda()
    if status == "override":
        build_env["CC"]  = info_a
        build_env["CXX"] = info_b
        build_env["NVCC_CCBIN"] = info_b
        return ("override", info_a, info_b)
    if status == "incompatible":
        return ("incompatible", info_a, info_b)
    return ("ok", None, None)
