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
