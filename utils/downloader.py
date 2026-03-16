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
        Migrates EVERY folder and file inside .../models/
        Moves physical data to new install, then creates a symlink in the old folder
        pointing to the new location.
        """
        old_models_root = Path(old_comfy_path) / "models"
        new_models_root = Path(new_comfy_path) / "models"

        if not old_models_root.exists():
            Logger.error(f"Source models folder not found: {old_models_root}")
            return

        Logger.log(f"Starting complete migration from {old_models_root}...", "info")
        
        # Iterate through every directory and file in the old models folder
        # This ensures custom folders are also migrated
        for item in old_models_root.iterdir():
            if item.is_symlink():
                continue  # Skip existing links to avoid recursion issues
            
            if item.is_dir():
                # Process the directory recursively
                for file_item in item.rglob("*"):
                    if file_item.is_dir() or file_item.is_symlink():
                        continue
                        
                    # Calculate path relative to 'models' (e.g., 'checkpoints/my_folder/model.sft')
                    relative_path = file_item.relative_to(old_models_root)
                    new_file_path = new_models_root / relative_path
                    
                    # Ensure the destination subdirectory exists
                    new_file_path.parent.mkdir(parents=True, exist_ok=True)

                    if not new_file_path.exists():
                        try:
                            Logger.log(f" Moving: {relative_path}", "info")
                            # 1. MOVE the physical data to the NEW installation
                            shutil.move(str(file_item), str(new_file_path))
                            
                            # 2. LINK BACK so the old installation still functions
                            try:
                                os.symlink(new_file_path, file_item)
                            except OSError:
                                # Windows often requires Admin for symlinks
                                Logger.log(f" [!] Moved {file_item.name}, but link-back failed (No Admin).", "warn")
                        except Exception as e:
                            Logger.error(f" [!] Error migrating {relative_path}: {e}")
                    else:
                        Logger.log(f" Skipping {relative_path}: Already exists in new install.", "warn")

        Logger.success("Migration Finished. New install now owns the physical model data.")

    @staticmethod
    def download(url, dest_path, label):
        """Standard download with directory safety and basic progress feedback."""
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
            print("") # New line after progress bar
            Logger.log(f"Successfully downloaded: {label}", "ok")
            return True
        except Exception as e:
            print("")
            Logger.error(f"Failed to download {label}: {e}")
            return False

    @staticmethod
    def show_cli_menu(config_downloads, comfy_path):
        """
        Robust CLI menu for model management.
        Works in W11 Terminal, Linux, and SSH.
        """
        print("\n" + "="*55)
        print("      DASIWA MODEL DOWNLOADER & MIGRATOR")
        print("="*55)
        print(" M. MIGRATE ALL: Move all files from an old .../models/ folder")
        print("                 (Moves data to NEW, links back to OLD)")
        print("-" * 55)
        
        to_download = []
        for i, item in enumerate(config_downloads):
            # Check if file exists anywhere in the models subtree
            exists = Downloader.file_exists_recursive(Path(comfy_path) / "models", item['file'])
            status = "[INSTALLED]" if exists else "[ ]"
            print(f" {i+1}. {status} {item['name']} ({item['type']})")
            if not exists:
                to_download.append(item)

        print("\nEnter choice (Numbers e.g. '1,3' / 'all' / 'm' / Enter to skip)")
        choice = input(">> ").strip().lower()

        if choice == 'm':
            old_path = input("Paste path to OLD ComfyUI root folder: ").strip().replace('"', '')
            if old_path:
                Downloader.migrate_models(old_path, comfy_path)
            return

        selected = []
        if choice == 'all':
            selected = to_download
        elif choice:
            try:
                indices = [int(x.strip()) - 1 for x in choice.split(',')]
                for idx in indices:
                    if 0 <= idx < len(config_downloads):
                        item = config_downloads[idx]
                        # Final check before adding to queue
                        if not Downloader.file_exists_recursive(Path(comfy_path) / "models", item['file']):
                            selected.append(item)
            except (ValueError, IndexError):
                Logger.log("Invalid selection. Skipping downloads.", "warn")

        for item in selected:
            # Map 'type' from config to the correct model subfolder
            dest = Path(comfy_path) / "models" / item['type'] / item['file']
            Downloader.download(item['url'], dest, item['name'])