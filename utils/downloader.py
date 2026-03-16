import urllib.request
import os
import sys
import shutil
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
                for file_item in item.rglob("*"):
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
                                Logger.log(f" [!] Link-back failed (No Admin).", "warn")
                        except Exception as e:
                            Logger.error(f" [!] Error moving {relative_path}: {e}")
            
        Logger.success("Migration Finished.")

    @staticmethod
    def download(url, dest_path, label):
        """Standard download with parent directory creation."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        Logger.log(f"Downloading {label}...", "info")
        
        def report(block_num, block_size, total_size):
            read = block_num * block_size
            if total_size > 0:
                percent = min(100, read * 100 / total_size)
                sys.stdout.write(f"\r    Progress: {percent:.1f}%")
            else:
                sys.stdout.write(f"\r    Downloaded: {read // 1024} KB")
            sys.stdout.flush()

        try:
            urllib.request.urlretrieve(url, dest_path, reporthook=report)
            print("") 
            Logger.log(f"Successfully downloaded: {label}", "ok")
            return True
        except Exception as e:
            print("")
            Logger.error(f"Failed to download {label}: {e}")
            return False

    @staticmethod
    def show_cli_menu(config_downloads, comfy_path):
        print("\n" + "="*55)
        print("      DASIWA COMPONENT DOWNLOADER & MIGRATOR")
        print("="*55)
        
        to_download = []
        for i, item in enumerate(config_downloads):
            # Check if it's a model or a generic file to determine search root
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
        
        choice = input("Enter choice: ").strip().lower()

        if choice == 'm':
            old_path = input("\nPaste path to OLD ComfyUI root: ").strip().replace('"', '')
            if old_path:
                Downloader.migrate_models(old_path, comfy_path)
            return

        selected = to_download if choice == 'all' else []
        if choice and choice != 'all':
            try:
                indices = [int(x.strip()) - 1 for x in choice.split(',')]
                for idx in indices:
                    if 0 <= idx < len(config_downloads):
                        item = config_downloads[idx]
                        # Final check
                        search_root = Path(comfy_path) / "models" if "models" in item['type'] else Path(comfy_path)
                        if not Downloader.file_exists_recursive(search_root, item['file']):
                            selected.append(item)
            except: pass

        for item in selected:
            # Flexible pathing: If type starts with 'models', it goes there. 
            # Otherwise, it's relative to the ComfyUI root.
            dest = Path(comfy_path) / item['type'] / item['file']
            Downloader.download(item['url'], dest, item['name'])