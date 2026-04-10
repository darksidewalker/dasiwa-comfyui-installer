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
            Logger.log("Downloading portable FFmpeg from configuration source...", "info")
            urllib.request.urlretrieve(download_url, zip_dest)
            
            with zipfile.ZipFile(zip_dest, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
            
            # Identify extracted folder and move to final location
            inner_dir = next(extract_to.glob("ffmpeg-*"))
            if final_bin_dir.parent.exists():
                shutil.rmtree(final_bin_dir.parent)
            shutil.move(str(inner_dir), str(final_bin_dir.parent))
            
            # Cleanup artifacts
            os.remove(zip_dest)
            shutil.rmtree(extract_to)
            
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
        else:
            # Linux relies on system package manager
            try:
                Logger.log("Installing FFmpeg via apt...", "info")
                subprocess.run(["sudo", "apt-get", "install", "-y", "ffmpeg"], check=True)
            except:
                Logger.warn("Manual install required: 'sudo apt install ffmpeg'")