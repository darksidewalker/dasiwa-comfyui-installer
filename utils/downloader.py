import urllib.request
import os
import sys
import shutil
import time
from pathlib import Path
from utils.logger import Logger

class Downloader:
    @staticmethod
    def get_input(prompt):
        """Standardized input method to prevent AttributeError in setup_logic."""
        return input(prompt)

    @staticmethod
    def download(url, dest, name, retries=3, delay=2):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        if dest.exists():
            Logger.log(f" {name} already exists. Skipping.", "ok")
            return
            
        for attempt in range(retries):
            try:
                Logger.log(f" Downloading {name} (Attempt {attempt + 1}/{retries})...", "info")
                
                # Using Request with headers to avoid being blocked by hosts like GitHub/HuggingFace
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                
                with urllib.request.urlopen(req, timeout=25) as response, open(dest, 'wb') as out_file:
                    shutil.copyfileobj(response, out_file)
                
                Logger.log(f" [DONE] {name}", "ok")
                return 
            except Exception as e:
                if attempt < retries - 1:
                    Logger.warn(f" Error on {name}: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    Logger.error(f" Download failed for {name} after {retries} attempts: {e}")

    @staticmethod
    def file_exists_recursive(base_path, filename):
        """Checks if a file exists anywhere in the directory subtree."""
        base_path = Path(base_path)
        if not base_path.exists():
            return False
        # Uses rglob to find the file even if it is in a subfolder
        return any(base_path.rglob(filename))

    @staticmethod
    def migrate_models(old_comfy_path, new_comfy_path):
        """Migrates folders inside .../models/ and creates symlinks."""
        old_models_root = Path(old_comfy_path) / "models"
        new_models_root = Path(new_comfy_path) / "models"

        if not old_models_root.exists():
            Logger.error(f"Source models folder not found: {old_models_root}")
            return

        Logger.log(f"Starting migration from {old_models_root}...", "info")
        
        for item in list(old_models_root.iterdir()):
            if item.is_symlink(): continue
            if item.is_dir():
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
                                os.symlink(new_file_path, file_item)
                            except OSError:
                                Logger.log(f" [!] Link-back failed (Requires Admin/Privileges).", "warn")
                        except Exception as e:
                            Logger.error(f" [!] Error moving {relative_path}: {e}")
            
        Logger.success("Migration Finished.")

    @staticmethod
    def show_cli_menu(config_downloads, comfy_path):
        """Displays an interactive menu for optional downloads."""
        to_download = []
        comfy_path = Path(comfy_path)
        
        for item in config_downloads:
            search_root = comfy_path / "models" if "models" in item['type'] else comfy_path
            if not Downloader.file_exists_recursive(search_root, item['file']):
                to_download.append(item)

        if not to_download:
            Logger.log("All optional components are already present.", "ok")
            return

        print(f"\n{Logger.BOLD}{Logger.CYAN}--- OPTIONAL COMPONENTS ---{Logger.END}")
        for i, item in enumerate(config_downloads, 1):
            status = f"{Logger.GREEN}[Installed]{Logger.END}" if item not in to_download else f"{Logger.YELLOW}[Missing]{Logger.END}"
            print(f" {i}. {item['name']:<40} {status}")

        print("\nCommands:")
        print("  > [Numbers] : Select items (e.g., 1,3)")
        print("  > 'all'     : Download all missing")
        print("  > 'm'       : Migrate models from old install")
        print("  > [Enter]   : Skip / Continue")
        print("—" * 55)
        
        choice = Downloader.get_input("Enter choice: ").lower().strip()

        if not choice:
            return

        if choice == 'm':
            old_path = Downloader.get_input("\nPaste path to OLD ComfyUI root: ").replace('"', '')
            if old_path:
                Downloader.migrate_models(old_path, comfy_path)
            return

        selected = []
        if choice == 'all':
            selected = to_download
        else:
            try:
                raw_indices = choice.replace(',', ' ').split()
                indices = [int(x) - 1 for x in raw_indices]
                for idx in indices:
                    if 0 <= idx < len(config_downloads):
                        item = config_downloads[idx]
                        if item in to_download:
                            selected.append(item)
            except ValueError:
                Logger.error("Invalid selection. Please use numbers or 'all'.")

        for item in selected:
            dest = comfy_path / item['type'] / item['file']
            Downloader.download(item['url'], dest, item['name'])