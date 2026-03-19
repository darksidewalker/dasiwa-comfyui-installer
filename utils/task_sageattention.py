import os
import platform
import subprocess
import shutil
from pathlib import Path
from utils.logger import Logger

class SageInstaller:
    @staticmethod
    def get_input(prompt):
        return input(prompt)

    @staticmethod
    def check_nvcc():
        """Checks if the CUDA Toolkit (nvcc) is accessible in the PATH."""
        try:
            subprocess.run(["nvcc", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except FileNotFoundError:
            return False

    @staticmethod
    def install_system_dependencies(config_urls):
        """Menu to help users install C++ compilers using URLs from config."""
        os_type = platform.system()
        print(f"\n{Logger.BOLD}{Logger.CYAN}--- SAGEATTENTION SYSTEM DEPENDENCIES ---{Logger.END}")
        
        if os_type == "Windows":
            print(f"1. [Windows] MSVC & Build Tools (Manual Download)")
        elif os_type == "Linux":
            print("2. [Ubuntu/Debian] Install build-essential & cmake")
            print("3. [Arch Linux] Install base-devel & cmake")
        
        print("s. Skip / Already installed")
        choice = SageInstaller.get_input("\nSelect an option: ").lower()

        if choice == '1':
            import webbrowser
            webbrowser.open(config_urls.get("msvc_build_tools"))
            Logger.log("Install 'Desktop development with C++' and restart.", "info")
        elif choice == '2':
            subprocess.run(["sudo", "apt", "update"], check=True)
            subprocess.run(["sudo", "apt", "install", "-y", "build-essential", "cmake", "git"], check=True)
        elif choice == '3':
            subprocess.run(["sudo", "pacman", "-Sy", "--needed", "base-devel", "cmake", "git"], check=True)
        
        return choice != 's'

    @staticmethod
    def build_sage(venv_env, comfy_path, config_urls):
        """Clones and builds SageAttention using the repo URL from config."""
        if not SageInstaller.check_nvcc():
            Logger.error("CUDA Toolkit (nvcc) not found!")
            SageInstaller.install_system_dependencies(config_urls)
            if not SageInstaller.check_nvcc():
                return

        sage_dir = Path(comfy_path).parent / "SageAttention"
        repo_url = config_urls.get("sage_repo")
        
        if not sage_dir.exists():
            Logger.log(f"Cloning SageAttention from {repo_url}...", "info")
            subprocess.run(["git", "clone", repo_url, str(sage_dir)], check=True)
        
        # 2. Setup Build Environment
        build_env = venv_env.copy()
        build_env["EXT_PARALLEL"] = "4"
        build_env["NVCC_APPEND_FLAGS"] = "--threads 8"
        build_env["MAX_JOBS"] = "32"

        # 3. Execution
        original_cwd = os.getcwd()
        os.chdir(sage_dir)
        try:
            Logger.log("Starting SageAttention build process (Source)...", "info")
            
            # Identify the python executable inside the venv
            is_win = platform.system() == "Windows"
            venv_path = Path(venv_env.get("VIRTUAL_ENV", ""))
            python_exe = venv_path / ("Scripts/python.exe" if is_win else "bin/python")

            if not python_exe.exists():
                Logger.error(f"Venv Python not found at {python_exe}")
                return

            # Run the build
            subprocess.run([str(python_exe), "setup.py", "install"], env=build_env, check=True)
            Logger.success("SageAttention installed successfully from source.")
        except Exception as e:
            Logger.error(f"SageAttention build failed: {e}")
        finally:
            os.chdir(original_cwd)