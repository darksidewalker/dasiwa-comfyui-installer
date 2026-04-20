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
        """ffmpeg in PATH (anywhere) is good enough for ComfyUI nodes."""
        return shutil.which("ffmpeg") is not None

    @staticmethod
    def is_local_installed(comfy_root):
        """Did we already drop a portable copy into ComfyUI/ffmpeg/?"""
        comfy_root = Path(comfy_root)
        exe = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
        return (comfy_root / "ffmpeg" / "bin" / exe).exists()

    # ---------- Windows portable install ----------

    @staticmethod
    def install_windows(comfy_root, download_url):
        zip_dest = comfy_root / "ffmpeg.zip"
        extract_to = comfy_root / "ffmpeg_temp"
        final_root = comfy_root / "ffmpeg"

        try:
            Logger.log("Downloading portable FFmpeg for Windows...", "info")
            urllib.request.urlretrieve(download_url, zip_dest)

            if extract_to.exists():
                shutil.rmtree(extract_to, ignore_errors=True)

            with zipfile.ZipFile(zip_dest, 'r') as zip_ref:
                zip_ref.extractall(extract_to)

            inner_dir = next(extract_to.glob("ffmpeg-*"), None)
            if not inner_dir:
                raise RuntimeError("Could not find extracted FFmpeg folder structure.")

            if final_root.exists():
                shutil.rmtree(final_root, ignore_errors=True)
            shutil.move(str(inner_dir), str(final_root))

            # Cleanup
            try:
                zip_dest.unlink()
            except OSError:
                pass
            shutil.rmtree(extract_to, ignore_errors=True)

            Logger.log("Portable FFmpeg configured in ComfyUI root.", "ok")
            return str(final_root / "bin")

        except Exception as e:
            Logger.error(f"FFmpeg download failed: {e}")
            return None

    # ---------- Linux system-package install ----------

    @staticmethod
    def install_linux():
        managers = [
            ("apt-get", ["sudo", "apt-get", "install", "-y", "ffmpeg"]),
            ("pacman",  ["sudo", "pacman", "-S", "--noconfirm", "ffmpeg"]),
            ("dnf",     ["sudo", "dnf", "install", "-y", "ffmpeg"]),
            ("zypper",  ["sudo", "zypper", "install", "-y", "ffmpeg"]),
            ("brew",    ["brew", "install", "ffmpeg"]),
        ]
        for manager, cmd in managers:
            if shutil.which(manager):
                try:
                    Logger.log(f"Detected {manager}. Attempting FFmpeg installation...", "info")
                    subprocess.run(cmd, check=True)
                    Logger.success(f"FFmpeg installed successfully via {manager}.")
                    return True
                except subprocess.CalledProcessError:
                    Logger.warn(f"Failed to install via {manager}. Trying next option...")
                except Exception as e:
                    Logger.error(f"Unexpected error with {manager}: {e}")

        Logger.error("Could not automatically install FFmpeg.")
        Logger.log("Please install FFmpeg manually using your distribution's package manager.",
                   "warn")
        return False

    # ---------- Public entry point ----------

    @classmethod
    def run(cls, comfy_path, config_urls):
        comfy_path = Path(comfy_path)

        # If either system-wide ffmpeg or our portable copy is present, skip
        if cls.is_installed():
            Logger.log("FFmpeg already detected in system PATH.", "ok")
            return
        if cls.is_local_installed(comfy_path):
            Logger.log("Portable FFmpeg already present in ComfyUI/ffmpeg/.", "ok")
            return

        if platform.system() == "Windows":
            url = config_urls.get("ffmpeg_windows")
            if not url:
                Logger.error("FFmpeg URL missing in config.json")
                return
            bin_path = cls.install_windows(comfy_path, url)
            if bin_path:
                os.environ["PATH"] += os.pathsep + bin_path

        elif platform.system() == "Linux":
            cls.install_linux()
