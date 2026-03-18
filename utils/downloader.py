import urllib.request
import os
import sys
import shutil
import time
from pathlib import Path
from utils.logger import Logger

class Downloader:
    @staticmethod
    def file_exists_recursive(base_path, filename):
        """Checks if a file exists anywhere in the directory subtree."""
        if not os.path.exists(base_path):
            return False
        return any(Path(base_path).rglob(filename))

    @staticmethod
    def migrate_models(old_comfy_path, new_comfy_path):
        """
        Migrates EVERY folder inside .../models/
        Moves physical data to new install, then links back.
        """
        old_models_root = Path(old_comfy_path) / "models"
        new_models_root = Path(new_comfy_path) / "models"

        if not old_models_root.exists():
            Logger.error(f"Source models folder not found: {old_models_root}")
            return

        Logger.log(f"Starting migration from {old_models_root}...", "info")
        
        for item in old_models_root.iterdir():
            if item.is_symlink(): continue
            if item.is_dir():
                # Using list() to avoid issues if the directory content changes during iteration
                for file_item in list(item.rglob("*")):
                    if file_item.is_dir() or file_item.is_symlink(): continue
                        
                    relative_path = file_item.relative_to(old_models_root)
                    new_file_path = new_models_root / relative_path
                    new_file_path.parent.mkdir(parents=True, exist_ok=True)

                    if not new_file_path.exists():
                        try:
                            Logger.log(f" Moving: {relative_path}", "info")
                            shutil.move(str(file_item), str(new_file_path))
                            try:
                                # Create symlink back to original location so old install still "works"
                                os.symlink(new_file_path, file_item)
                            except OSError:
                                Logger.log(f" [!] Link-back failed (Requires Admin/Privileges).", "warn")
                        except Exception as e:
                            Logger.error(f" [!] Error moving {relative_path}: {e}")
            
        Logger.success("Migration Finished.")

    @staticmethod
    def download(url, dest, name="item"):
        # Ensure the folder exists before downloading
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        retries = 3
        delay = 5 
        
        for i in range(retries):
            try:
                Logger.log(f"Downloading {name}...", "info")
                # Add a User-Agent to avoid being blocked by some servers
                opener = urllib.request.build_opener()
                opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
                urllib.request.install_opener(opener)
                
                urllib.request.urlretrieve(url, dest)
                Logger.log(f"Successfully downloaded {name}", "ok")
                return True
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    Logger.log(f"Rate limited (429). Retrying in {delay}s... (Attempt {i+1}/{retries})", "warn")
                    time.sleep(delay)
                    delay *= 2 
                else:
                    Logger.error(f"HTTP Error {e.code} for {name}: {e.reason}")
                    break 
            except Exception as e:
                Logger.error(f"Download failed for {name}: {e}")
                time.sleep(1)
        return False

    @staticmethod
    def get_input(prompt):
        """Robust input handler that manages EOF errors from piped execution."""
        try:
            # On Linux/macOS, try to read directly from the terminal if stdin is a pipe
            if sys.platform != "win32" and not sys.stdin.isatty():
                with open('/dev/tty', 'r') as tty:
                    print(prompt, end='', flush=True)
                    return tty.readline().strip()
            
            return input(prompt).strip()
        except EOFError:
            return "" # Return empty to trigger default behavior/skip

    @staticmethod
    def show_cli_menu(config_downloads, comfy_path):
        print("\n" + "="*55)
        print("      DASIWA COMPONENT DOWNLOADER & MIGRATOR")
        print("="*55)
        
        to_download = []
        for i, item in enumerate(config_downloads):
            search_root = Path(comfy_path) / "models" if "models" in item['type'] else Path(comfy_path)
            
            exists = Downloader.file_exists_recursive(search_root, item['file'])
            status = "[INSTALLED]" if exists else "[ ]"
            print(f" {i+1}. {status} {item['name']} ({item['type']})")
            if not exists: to_download.append(item)

        print("\n" + "—"*55)
        print("  COMMANDS:")
        print("  > [Numbers] : Select specific items (e.g., 1,3)")
        print("  > 'all'     : Download all missing items")
        print("  > 'm'       : Migrate models from old install")
        print("  > [Enter]   : Skip / Continue setup")
        print("—"*55)
        
        choice = Downloader.get_input("Enter choice: ").lower()

        if not choice:
            Logger.log("Skipping component selection.", "info")
            return

        if choice == 'm':
            old_path = Downloader.get_input("\nPaste path to OLD ComfyUI root: ").replace('"', '')
            if old_path:
                Downloader.migrate_models(old_path, comfy_path)
            return

        selected = to_download if choice == 'all' else []
        if choice and choice != 'all':
            try:
                # Support comma-separated or space-separated numbers
                raw_indices = choice.replace(',', ' ').split()
                indices = [int(x) - 1 for x in raw_indices]
                for idx in indices:
                    if 0 <= idx < len(config_downloads):
                        item = config_downloads[idx]
                        search_root = Path(comfy_path) / "models" if "models" in item['type'] else Path(comfy_path)
                        if not Downloader.file_exists_recursive(search_root, item['file']):
                            selected.append(item)
            except ValueError:
                Logger.error("Invalid selection. Please use numbers (e.g., 1, 2).")

        for item in selected:
            dest = Path(comfy_path) / item['type'] / item['file']
            Downloader.download(item['url'], dest, item['name'])