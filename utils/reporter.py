import os
import time
import subprocess
from pathlib import Path
from utils.logger import Logger

class Reporter:
    @staticmethod
    def show_summary(hw, venv_env, start_time, node_stats=None):
        """Generates a clean overview of the installation results."""
        elapsed = round(time.time() - start_time, 1)
        is_win = os.name == 'nt'
        
        # Header
        print("\n" + f"{Logger.BOLD}{Logger.CYAN}━" * 50 + f"{Logger.END}")
        Logger.log("INSTALLATION SUMMARY", "info", bold=True)
        print(f"{Logger.BOLD}{Logger.CYAN}━" * 50 + f"{Logger.END}")
        
        # 1. Hardware Info
        print(f"{Logger.CYAN}{Logger.BOLD}GPU:{Logger.END}       {hw['name']}")
        
        # 2. Virtual Environment
        env_path = Path(venv_env.get("VIRTUAL_ENV", "Unknown")).absolute()
        print(f"{Logger.CYAN}{Logger.BOLD}Venv Path:{Logger.END} {env_path}")

        # 3. Package Version (Engine check)
        try:
            bin_dir = "Scripts" if is_win else "bin"
            python_exe = env_path / bin_dir / ("python.exe" if is_win else "python")
            
            torch_v = subprocess.run([str(python_exe), "-c", "import torch; print(torch.__version__)"], 
                                    capture_output=True, text=True).stdout.strip()
            print(f"{Logger.CYAN}{Logger.BOLD}PyTorch:{Logger.END}   {torch_v}")
        except:
            print(f"{Logger.CYAN}{Logger.BOLD}Status:{Logger.END}    Environment Ready")

        # 4. Custom Nodes Count 
        if node_stats:
            total = node_stats.get('total', 0)
            success = node_stats.get('success', 0)
            failed_nodes = node_stats.get('failed', [])
            failed_count = len(failed_nodes)
        
            print(f"{Logger.CYAN}{Logger.BOLD}Nodes:{Logger.END}     {success}/{total} installed successfully")
            
            if failed_count > 0:
                print(f"{Logger.RED}{Logger.BOLD}Skipped:{Logger.END}   {failed_count} nodes failed (check logs for details)")
                for name in failed_nodes:
                    print(f"         - {name}")
        else:
            # Fallback if the node task never ran or crashed
            print(f"{Logger.CYAN}{Logger.BOLD}Nodes:{Logger.END}     Check logs for synchronization status")

        # 5. Launcher Path
        launcher_file = "run_comfyui.bat" if is_win else "run_comfyui.sh"
        full_launcher_path = Path(launcher_file).absolute()
        print(f"{Logger.CYAN}{Logger.BOLD}Launcher:{Logger.END}  {full_launcher_path}")

        # 6. Speed Metrics
        print(f"{Logger.CYAN}{Logger.BOLD}Time:{Logger.END}      {elapsed}s")
        print(f"{Logger.BOLD}{Logger.CYAN}━" * 50 + f"{Logger.END}")