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
    def check_cpp_compiler():
        """Checks if a C++ compiler is present based on the OS."""
        os_type = platform.system()
        try:
            if os_type == "Windows":
                # Check for MSVC compiler (cl.exe)
                subprocess.run(["cl"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                # Check for g++ or clang++
                subprocess.run(["g++", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except FileNotFoundError:
            return False

    @staticmethod
    def install_system_dependencies(config_urls):
        """Smart dependency menu: only prompts if tools are missing."""
        os_type = platform.system()
        has_nvcc = SageInstaller.check_nvcc()
        has_cpp = SageInstaller.check_cpp_compiler()

        if has_nvcc and has_cpp:
            Logger.log("All build dependencies (NVCC & C++ Compiler) detected.", "ok")
            return True

        print(f"\n{Logger.BOLD}{Logger.CYAN}--- SAGEATTENTION DEPENDENCY CHECK ---{Logger.END}")
        if not has_nvcc: Logger.warn("[-] CUDA Toolkit (nvcc) NOT found.")
        if not has_cpp: Logger.warn("[-] C++ Compiler (MSVC/GCC) NOT found.")
        
        print("\nOptions to fix dependencies:")
        if os_type == "Windows":
            print(f" 1. [Windows] Open MSVC Build Tools Download Page")
        elif os_type == "Linux":
            print(" 2. [Ubuntu/Debian] Install build-essential & cmake (sudo)")
            print(" 3. [Arch Linux] Install base-devel & cmake (sudo)")
        
        print(" s. Skip check and try building anyway")
        print(" q. Cancel SageAttention installation")
        
        choice = SageInstaller.get_input("\nSelect an option: ").lower()

        if choice == '1' and os_type == "Windows":
            import webbrowser
            webbrowser.open(config_urls.get("msvc_build_tools"))
            Logger.log("Install 'Desktop development with C++' and restart the terminal.", "info")
            return False
        elif choice == '2' and os_type == "Linux":
            subprocess.run(["sudo", "apt", "update"], check=True)
            subprocess.run(["sudo", "apt", "install", "-y", "build-essential", "cmake", "git"], check=True)
            return True
        elif choice == '3' and os_type == "Linux":
            subprocess.run(["sudo", "pacman", "-Sy", "--needed", "base-devel", "cmake", "git"], check=True)
            return True
        elif choice == 's':
            return True
        
        return False

    @staticmethod
    def build_sage(venv_env, comfy_path, config_urls):
        """Clones and builds SageAttention inside the ComfyUI folder."""
        if not SageInstaller.install_system_dependencies(config_urls):
            Logger.warn("Dependencies not resolved. Skipping SageAttention build.")
            return

        # FIX: Clone inside ComfyUI, not the script root
        sage_dir = Path(comfy_path) / "SageAttention"
        repo_url = config_urls.get("sage_repo")
        
        if not sage_dir.exists():
            Logger.log(f"Cloning SageAttention into {sage_dir}...", "info")
            subprocess.run(["git", "clone", repo_url, str(sage_dir)], check=True)
        
        # Build Environment
        build_env = venv_env.copy()
        build_env["EXT_PARALLEL"] = "4"
        build_env["NVCC_APPEND_FLAGS"] = "--threads 8"
        build_env["MAX_JOBS"] = "32"

        original_cwd = os.getcwd()
        os.chdir(sage_dir)
        try:
            is_win = platform.system() == "Windows"
            venv_path = Path(venv_env.get("VIRTUAL_ENV", ""))
            python_exe = venv_path / ("Scripts/python.exe" if is_win else "bin/python")

            if not python_exe.exists():
                Logger.error(f"Venv Python not found at {python_exe}")
                return

            # FIX: Ensure build tools are present in the venv before running setup.py
            Logger.log("Preparing build tools (setuptools, wheel)...", "info")
            subprocess.run([str(python_exe), "-m", "pip", "install", "setuptools", "wheel"], env=build_env, check=True)

            Logger.log("Starting SageAttention source build (this may take a few minutes)...", "info")
            # Using 'pip install .' is often more reliable than 'setup.py install'
            subprocess.run([str(python_exe), "-m", "pip", "install", "."], env=build_env, check=True)
            
            Logger.success("SageAttention installed successfully.")
        except Exception as e:
            Logger.error(f"SageAttention build failed: {e}")
            Logger.info("Check if CUDA Toolkit version matches your Torch CUDA version.")
        finally:
            os.chdir(original_cwd)