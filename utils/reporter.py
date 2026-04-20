import os
import time
import subprocess
from pathlib import Path

from utils.logger import Logger


class Reporter:
    @staticmethod
    def show_summary(hw, venv_env, start_time, node_stats=None, sage_installed=None,
                     ffmpeg_installed=None):
        """Clean overview of the installation result."""
        elapsed = round(time.time() - start_time, 1)
        is_win = os.name == 'nt'

        Logger.banner("INSTALLATION SUMMARY", f"Completed in {elapsed}s")

        # Hardware
        Logger.kv("GPU:", hw['name'])

        # Venv path
        env_path = Path(venv_env.get("VIRTUAL_ENV", "Unknown")).absolute()
        Logger.kv("Venv path:", env_path)

        # Package versions (engine check)
        bin_dir = "Scripts" if is_win else "bin"
        python_exe = env_path / bin_dir / ("python.exe" if is_win else "python")

        try:
            torch_v = subprocess.run(
                [str(python_exe), "-c",
                 "import torch;print(torch.__version__);"
                 "print(torch.version.cuda or 'cpu')"],
                capture_output=True, text=True, timeout=15,
            )
            out = (torch_v.stdout or "").strip().splitlines()
            if out:
                Logger.kv("PyTorch:", out[0])
            if len(out) > 1:
                Logger.kv("CUDA runtime:", out[1])
        except Exception:
            Logger.kv("Status:", "Environment Ready")

        # SageAttention
        if sage_installed is not None:
            Logger.kv("SageAttention:", "installed ✓" if sage_installed else "skipped")

        # FFmpeg
        if ffmpeg_installed is not None:
            Logger.kv("FFmpeg:", "installed ✓" if ffmpeg_installed else "skipped")

        # Custom nodes
        if node_stats:
            total = node_stats.get('total', 0)
            success = node_stats.get('success', 0)
            failed_nodes = node_stats.get('failed', [])
            Logger.kv("Nodes:", f"{success}/{total} installed")
            if failed_nodes:
                Logger.kv("Failed nodes:", f"{Logger.RED}{len(failed_nodes)}{Logger.END}")
                for name in failed_nodes:
                    print(f"    {Logger.RED}- {name}{Logger.END}")
        else:
            Logger.kv("Nodes:", "not synchronised")

        # Launcher
        launcher_file = "run_comfyui.bat" if is_win else "run_comfyui.sh"
        comfy_root = env_path.parent  # venv lives inside ComfyUI/
        launcher_path = comfy_root / launcher_file
        Logger.kv("Launcher:", launcher_path)

        Logger.rule()
        Logger.success("Process Finished!")
