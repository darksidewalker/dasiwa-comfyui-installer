import platform
import subprocess
import os
import shutil
import sys

def run_cmd(cmd, shell=False, capture=False):
    """Internal helper to run commands without crashing on failure."""
    return subprocess.run(cmd, check=False, shell=shell, capture_output=capture, text=True)

def get_gpu_report(is_win, logger):
    """
    Identifies GPUs and selects the most capable hardware.
    Mandatory manual selection if automatic detection fails.
    Aborts setup if no compatible GPU is available.
    """
    gpus = []
    
    if is_win:
        try:
            # Windows: Get Name and VRAM via PowerShell
            ps_cmd = 'powershell -NoProfile -Command "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM | ConvertTo-Csv -NoTypeInformation"'
            res = run_cmd(ps_cmd, shell=True, capture=True)
            lines = res.stdout.strip().splitlines()
            if len(lines) > 1:
                for line in lines[1:]:
                    parts = line.replace('"', '').split(',')
                    if len(parts) >= 2:
                        name = parts[0].strip()
                        raw_vram = parts[1].strip()
                        vram = abs(int(raw_vram)) // (1024**2) if raw_vram else 0
                        gpus.append({"name": name, "vram": vram})
        except Exception: pass
    else:
        # Linux Check 1: nvidia-smi (NVIDIA dGPUs)
        if shutil.which("nvidia-smi"):
            try:
                res = run_cmd(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], capture=True)
                if res.returncode == 0:
                    for line in res.stdout.strip().splitlines():
                        name, vram = line.split(',')
                        gpus.append({"name": name.strip(), "vram": int(vram.strip())})
            except Exception: pass

        # Linux Check 2: lspci (Fallback)
        try:
            res = run_cmd(["lspci"], capture=True)
            for line in res.stdout.splitlines():
                if any(x in line.upper() for x in ["VGA", "3D", "DISPLAY"]):
                    weight = 0
                    if "NVIDIA" in line.upper(): weight = 8192
                    elif "AMD" in line.upper() or "RADEON" in line.upper(): weight = 4096
                    
                    if not any(name in line for name in [g['name'] for g in gpus]):
                        gpus.append({"name": line.split(":")[-1].strip(), "vram": weight})
        except Exception: pass

    # Sort by potency (VRAM)
    gpus.sort(key=lambda x: x.get('vram', 0), reverse=True)
    
    vendor = "UNKNOWN"
    name = "Generic Device"

    if gpus:
        name = gpus[0]['name']
        name_up = name.upper()
        if "NVIDIA" in name_up: vendor = "NVIDIA"
        elif "AMD" in name_up or "RADEON" in name_up: vendor = "AMD"
        elif "INTEL" in name_up: vendor = "INTEL"

    # --- ENFORCED SELECTION & ABORT LOGIC ---
    while vendor == "UNKNOWN":
        logger.warn("Automated GPU detection failed.")
        print(f"\n{logger.BOLD}{logger.CYAN}--- MANDATORY HARDWARE SELECTION ---{logger.END}")
        print(" 1. NVIDIA (Modern: RTX 20/30/40/50 series)")
        print(" 2. NVIDIA Legacy (GTX 10 / Pascal / 12.1 Fallback)")
        print(" 3. AMD (Radeon / ROCm 6.2)")
        print(" 4. INTEL (Arc / iGPU)")
        print(" 5. [ABORT] No compatible GPU")
        
        choice = input("\nSelect (1-5): ").strip()
        
        if choice == "5":
            logger.error("Installation aborted: CPU-only is not supported.")
            sys.exit(1)
            
        mapping = {
            "1": ("NVIDIA", "Manual: NVIDIA Modern"),
            "2": ("NVIDIA", "Manual: NVIDIA GTX 10"),
            "3": ("AMD", "Manual: AMD"),
            "4": ("INTEL", "Manual: INTEL")
        }
        
        if choice in mapping:
            vendor, name = mapping[choice]
        else:
            logger.error("Invalid selection.")

    logger.log(f"Final Hardware Profile: {name} (Vendor: {vendor})", "ok")
    return {"vendor": vendor, "name": name}