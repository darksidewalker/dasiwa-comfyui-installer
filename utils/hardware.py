import platform
import subprocess
import os

def run_cmd(cmd, shell=False, capture=False):
    # Simple internal helper for the utility
    return subprocess.run(cmd, check=True, shell=shell, capture_output=capture, text=True)

def get_gpu_report(is_win, logger):
    """Identifies GPUs and selects the most capable vendor."""
    gpus = []
    try:
        if is_win:
            ps_cmd = 'powershell -NoProfile -Command "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM | ConvertTo-Csv -NoTypeInformation"'
            res = run_cmd(ps_cmd, shell=True, capture=True)
            lines = res.stdout.strip().splitlines()
            if len(lines) > 1:
                for line in lines[1:]:
                    parts = line.replace('"', '').split(',')
                    if len(parts) >= 2:
                        name = parts[0].strip()
                        raw_vram = parts[1].strip()
                        vram = int(raw_vram) if raw_vram else 0
                        gpus.append({"name": name, "vram": abs(vram)})
        else:
            res = run_cmd(["lspci"], capture=True)
            for line in res.stdout.splitlines():
                if any(x in line.upper() for x in ["VGA", "3D", "DISPLAY"]):
                    gpus.append({"name": line, "vram": 0})
    except:
        pass

    if not gpus:
        return {"vendor": "UNKNOWN", "name": "Generic"}

    gpus.sort(key=lambda x: x.get('vram', 0), reverse=True)
    winner = gpus[0]
    name_up = winner['name'].upper()
    
    vendor = "UNKNOWN"
    if "NVIDIA" in name_up: vendor = "NVIDIA"
    elif "AMD" in name_up or "RADEON" in name_up: vendor = "AMD"
    elif "INTEL" in name_up: vendor = "INTEL"

    logger.log(f"Primary GPU: {winner['name']} (Vendor: {vendor})", "ok")
    return {"vendor": vendor, "name": winner['name']}