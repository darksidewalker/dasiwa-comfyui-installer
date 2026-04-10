import os
import shutil
import subprocess
import platform
import urllib.request
import zipfile
from pathlib import Path
from utils.logger import Logger

class FFmpegInstaller:
    @staticmethod
    def is_installed():
        """Checks if ffmpeg is accessible in the current environment."""
        return shutil.which("ffmpeg") is not None

    @staticmethod
    def install_windows(comfy_root, download_url):
        """Downloads a portable FFmpeg build for Windows using config URL."""
        zip_dest = comfy_root / "ffmpeg.zip"
        extract_to = comfy_root / "ffmpeg_temp"
        final_bin_dir = comfy_root / "ffmpeg" / "bin"

        try:
            Logger.log("Downloading portable FFmpeg for Windows...", "info")
            urllib.request.urlretrieve(download_url, zip_dest)
            
            with zipfile.ZipFile(zip_dest, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
            
            inner_dir = next(extract_to.glob("ffmpeg-*"), None)
            if not inner_dir:
                raise Exception("Could not find extracted FFmpeg folder structure.")

            if final_bin_dir.parent.exists():
                shutil.rmtree(final_bin_dir.parent)
            
            shutil.move(str(inner_dir), str(final_bin_dir.parent))
            
            if zip_dest.exists(): os.remove(zip_dest)
            if extract_to.exists(): shutil.rmtree(extract_to)
            
            Logger.log("Portable FFmpeg configured in ComfyUI root.", "ok")
            return str(final_bin_dir)
        except Exception as e:
            Logger.error(f"FFmpeg download failed: {e}")
            return None

    @classmethod
    def run(cls, comfy_path, config_urls):
        """Main entry point for the FFmpeg task."""
        if cls.is_installed():
            Logger.log("FFmpeg already detected in system PATH.", "ok")
            return

        if platform.system() == "Windows":
            url = config_urls.get("ffmpeg_windows")
            if not url:
                Logger.error("FFmpeg URL missing in config.json")
                return
            bin_path = cls.install_windows(Path(comfy_path), url)
            if bin_path:
                os.environ["PATH"] += os.pathsep + bin_path
        
        elif platform.system() == "Linux":
            cls.install_linux()

    @staticmethod
    def install_linux():
        """Detects the Linux distro's package manager and attempts installation."""
        # Map package managers to their install commands
        managers = {
            "apt-get": ["sudo", "apt-get", "install", "-y", "ffmpeg"],
            "pacman": ["sudo", "pacman", "-S", "--noconfirm", "ffmpeg"],
            "dnf": ["sudo", "dnf", "install", "-y", "ffmpeg"],
            "zypper": ["sudo", "zypper", "install", "-y", "ffmpeg"],
            "brew": ["brew", "install", "ffmpeg"] # For Linux Homebrew users
        }

        for manager, cmd in managers.items():
            if shutil.which(manager):
                try:
                    Logger.log(f"Detected {manager}. Attempting FFmpeg installation...", "info")
                    # Try to install. check=True will raise error if sudo is denied or fails
                    subprocess.run(cmd, check=True)
                    Logger.success(f"FFmpeg installed successfully via {manager}.")
                    return
                except subprocess.CalledProcessError:
                    Logger.warn(f"Failed to install via {manager}. Trying next option...")
                except Exception as e:
                    Logger.error(f"Unexpected error with {manager}: {e}")

        # If all managers fail or none are found
        Logger.error("Could not automatically install FFmpeg.")
        Logger.log("Please install FFmpeg manually using your distribution's package manager.", "warn")