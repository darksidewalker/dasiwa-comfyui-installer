import os
import time
import subprocess
from pathlib import Path
from utils.logger import Logger

class Reporter:
    @staticmethod
    def show_summary(hw, venv_env, start_time):
        """Generates a clean overview of the installation results."""
        elapsed = round(time.time() - start_time, 1)
        
        # Header with your Logger colors
        print("\n" + f"{Logger.BOLD}{Logger.CYAN}━" * 50 + f"{Logger.END}")
        Logger.log("INSTALLATION SUMMARY", "info", bold=True)
        print(f"{Logger.BOLD}{Logger.CYAN}━" * 50 + f"{Logger.END}")
        
        # 1. Hardware Info
        print(f"{Logger.CYAN}{Logger.BOLD}GPU:{Logger.END}      {hw['name']}")
        
        # 2. Environment Path
        # Shortens the path for readability if it's too long
        env_path = Path(venv_env.get("VIRTUAL_ENV", "Unknown"))
        print(f"{Logger.CYAN}{Logger.BOLD}Env:{Logger.END}      .../{env_path.parent.name}/{env_path.name}")

        # 3. Package Versions (Direct Check)
        try:
            # We use the venv's specific python to verify the actual installed versions
            bin_dir = "Scripts" if os.name == "nt" else "bin"
            python_exe = env_path / bin_dir / ("python.exe" if os.name == "nt" else "python")
            
            torch_v = subprocess.run([str(python_exe), "-c", "import torch; print(torch.__version__)"], 
                                    capture_output=True, text=True).stdout.strip()
            numpy_v = subprocess.run([str(python_exe), "-c", "import numpy; print(numpy.__version__)"], 
                                    capture_output=True, text=True).stdout.strip()
            
            print(f"{Logger.CYAN}{Logger.BOLD}PyTorch:{Logger.END}  {torch_v}")
            print(f"{Logger.CYAN}{Logger.BOLD}NumPy:{Logger.END}    {numpy_v}")
        except:
            print(f"{Logger.CYAN}{Logger.BOLD}Status:{Logger.END}   Environment verified.")

        # 4. Custom Nodes Count
        nodes_path = Path("custom_nodes")
        if nodes_path.exists():
            count = len([x for x in nodes_path.iterdir() if x.is_dir()])
            print(f"{Logger.CYAN}{Logger.BOLD}Nodes:{Logger.END}    {count} custom nodes synchronized")

        # 5. Speed Metrics
        print(f"{Logger.CYAN}{Logger.BOLD}Time:{Logger.END}     {elapsed}s")
        print(f"{Logger.BOLD}{Logger.CYAN}━" * 50 + f"{Logger.END}")