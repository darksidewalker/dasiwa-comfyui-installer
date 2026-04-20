import platform
import subprocess
import shutil
import sys

from utils.logger import Logger


def _run_cmd(cmd, shell=False, capture=False):
    """Internal helper to run commands without crashing on failure."""
    try:
        return subprocess.run(
            cmd, check=False, shell=shell, capture_output=capture, text=True
        )
    except (FileNotFoundError, OSError):
        # Fake a failed-result so callers can keep going
        class _Dummy:
            returncode = 127
            stdout = ""
            stderr = ""
        return _Dummy()


def _vendor_weight(name_up):
    """Rank GPUs so a discrete NVIDIA always beats an Intel iGPU next to it."""
    if "NVIDIA" in name_up:
        return 3
    if "AMD" in name_up or "RADEON" in name_up:
        return 2
    if "ARC" in name_up:
        return 2  # Intel Arc dGPU — on par with AMD
    if "INTEL" in name_up:
        return 1  # Intel iGPU / HD Graphics
    return 0


def _parse_windows_gpus():
    """Query Win32_VideoController. AdapterRAM is a signed int32 that wraps for ≥4GB VRAM."""
    gpus = []
    ps_cmd = (
        'powershell -NoProfile -Command '
        '"Get-CimInstance Win32_VideoController | '
        'Select-Object Name, AdapterRAM | ConvertTo-Csv -NoTypeInformation"'
    )
    res = _run_cmd(ps_cmd, shell=True, capture=True)
    lines = (res.stdout or "").strip().splitlines()
    if len(lines) < 2:
        return gpus
    for line in lines[1:]:
        parts = line.replace('"', '').split(',')
        if len(parts) < 2:
            continue
        name = parts[0].strip()
        raw_vram = parts[1].strip()
        # Win32_VideoController AdapterRAM is int32, wraps negative for ≥4GB VRAM
        try:
            vram = abs(int(raw_vram)) // (1024 ** 2) if raw_vram else 0
        except ValueError:
            vram = 0
        gpus.append({"name": name, "vram": vram})
    return gpus


def _parse_linux_gpus():
    gpus = []
    # Primary: nvidia-smi (precise VRAM for NVIDIA dGPUs)
    if shutil.which("nvidia-smi"):
        res = _run_cmd(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"], capture=True
        )
        if res.returncode == 0 and res.stdout:
            for line in res.stdout.strip().splitlines():
                if "," in line:
                    name, vram = line.split(",", 1)
                    try:
                        gpus.append({"name": name.strip(), "vram": int(vram.strip())})
                    except ValueError:
                        pass

    # Fallback: lspci (for AMD/Intel and anything nvidia-smi missed)
    if shutil.which("lspci"):
        res = _run_cmd(["lspci"], capture=True)
        if res.returncode == 0:
            for line in (res.stdout or "").splitlines():
                if any(tag in line.upper() for tag in ("VGA", "3D", "DISPLAY")):
                    upper = line.upper()
                    weight = 0
                    if "NVIDIA" in upper:
                        weight = 8192
                    elif "AMD" in upper or "RADEON" in upper:
                        weight = 4096
                    elif "INTEL" in upper:
                        weight = 2048
                    name = line.split(":", 2)[-1].strip()
                    if not any(name in g["name"] or g["name"] in name for g in gpus):
                        gpus.append({"name": name, "vram": weight})
    return gpus


def get_gpu_report(is_win, logger=None):
    """
    Detect GPUs and pick the most capable one. Falls back to manual selection
    if detection is ambiguous. Aborts setup if user picks 'no compatible GPU'.
    """
    logger = logger or Logger

    gpus = _parse_windows_gpus() if is_win else _parse_linux_gpus()

    # Sort: vendor tier first, then VRAM
    gpus.sort(
        key=lambda g: (_vendor_weight(g["name"].upper()), g.get("vram", 0)),
        reverse=True,
    )

    vendor = "UNKNOWN"
    name = "Generic Device"
    if gpus:
        name = gpus[0]["name"]
        name_up = name.upper()
        if "NVIDIA" in name_up:
            vendor = "NVIDIA"
        elif "AMD" in name_up or "RADEON" in name_up:
            vendor = "AMD"
        elif "INTEL" in name_up:
            vendor = "INTEL"

    # Manual override loop when detection is inconclusive
    while vendor == "UNKNOWN":
        logger.warn("Automated GPU detection was inconclusive.")
        idx = logger.ask_choice(
            "Select your primary GPU vendor",
            [
                ("NVIDIA (Modern)",  "RTX 20/30/40/50 series — default CUDA path"),
                ("NVIDIA (Legacy)",  "GTX 10 / Pascal — forces CUDA 12.1 + Torch 2.4.1"),
                ("AMD",              "Radeon RX 6000/7000/9000 — ROCm builds"),
                ("Intel",            "Arc / iGPU — XPU builds"),
                ("Abort",            "No compatible GPU present"),
            ],
            default_index=0,
        )
        if idx == 4:
            logger.error("Installation aborted: CPU-only is not supported.")
            sys.exit(1)
        mapping = {
            0: ("NVIDIA", "Manual: NVIDIA Modern"),
            1: ("NVIDIA", "Manual: NVIDIA GTX 10"),
            2: ("AMD",    "Manual: AMD"),
            3: ("INTEL",  "Manual: INTEL"),
        }
        vendor, name = mapping[idx]

    logger.log(f"Final Hardware Profile: {name} (Vendor: {vendor})", "ok")
    return {"vendor": vendor, "name": name}
