import urllib.request
import os
import sys
import shutil
import time
import json
from pathlib import Path
from utils.logger import Logger

class Downloader:
    @staticmethod
    def get_input(prompt):
        """Standardized input method to prevent AttributeError in setup_logic."""
        return input(prompt)

    @staticmethod
    def get_latest_github_file(repo_path, folder):
        """
        Queries GitHub commits for a folder to find the most recently updated JSON file.
        """
        api_url = f"https://api.github.com/repos/{repo_path}/commits?path={folder}&per_page=1"
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                commits = json.loads(response.read().decode())
                if not commits:
                    return None

                # Fetch folder contents to get download URLs
                contents_url = f"https://api.github.com/repos/{repo_path}/contents/{folder}"
                req_contents = urllib.request.Request(contents_url, headers=headers)
                
                with urllib.request.urlopen(req_contents, timeout=15) as resp_cont:
                    files = json.loads(resp_cont.read().decode())
                    json_files = [f for f in files if f['name'].endswith('.json')]
                    
                    if not json_files:
                        return None
                    
                    # Identify the file from the last commit
                    last_sha = commits[0]['sha']
                    detail_url = f"https://api.github.com/repos/{repo_path}/commits/{last_sha}"
                    req_detail = urllib.request.Request(detail_url, headers=headers)
                    
                    with urllib.request.urlopen(req_detail, timeout=15) as resp_det:
                        detail = json.loads(resp_det.read().decode())
                        for f_changed in detail.get('files', []):
                            if f_changed['filename'].startswith(folder) and f_changed['filename'].endswith('.json'):
                                return {
                                    "name": os.path.basename(f_changed['filename']),
                                    "download_url": f_changed['raw_url']
                                }
                
                # Fallback to the first JSON file if commit detail is ambiguous
                return {"name": json_files[0]['name'], "download_url": json_files[0]['download_url']}
        except Exception as e:
            Logger.error(f"GitHub API Error: {e}")
            return None

    @staticmethod
    def download(url, dest_folder, display_name, explicit_file=None, retries=3, delay=2):
        """
        Downloads a file. Detects filename from URL if not explicitly provided.
        """
        # Determine filename from URL if not specified (HF/Direct URLs)
        filename = explicit_file if explicit_file else url.split('/')[-1].split('?')[0]
        dest = Path(dest_folder) / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        if dest.exists():
            Logger.log(f" {filename} already exists. Skipping.", "ok")
            return
            
        for attempt in range(retries):
            try:
                Logger.log(f" Downloading {display_name} (Attempt {attempt + 1}/{retries})...", "info")
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                
                with urllib.request.urlopen(req, timeout=25) as response, open(dest, 'wb') as out_file:
                    shutil.copyfileobj(response, out_file)
                
                Logger.log(f" [DONE] {filename}", "ok")
                return 
            except Exception as e:
                if attempt < retries - 1:
                    Logger.warn(f" Error: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    Logger.error(f" Download failed for {display_name}: {e}")

    @staticmethod
    def file_exists_recursive(base_path, filename):
        """Checks if a file exists anywhere in the directory subtree."""
        if not filename: return False
        base_path = Path(base_path)
        return any(base_path.rglob(filename)) if base_path.exists() else False

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
            if item.is_symlink() or not item.is_dir(): continue
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
        """Displays interactive menu with 'latest' awareness logic."""
        to_download = []
        comfy_path = Path(comfy_path)
        
        # Pre-process 'latest' entries and resolve filenames
        for item in config_downloads:
            if item.get('version') == 'latest' and 'repo_path' in item:
                latest = Downloader.get_latest_github_file(item['repo_path'], item['folder'])
                if latest:
                    item['file'] = latest['name']
                    item['url'] = latest['download_url']
                    item['name'] = f"{item['name']} (Latest: {latest['name']})"

            search_root = comfy_path / "models" if "models" in item['type'] else comfy_path
            if not Downloader.file_exists_recursive(search_root, item.get('file')):
                to_download.append(item)

        if not to_download:
            Logger.log("All optional components are already present.", "ok")
            return

        print(f"\n{Logger.BOLD}{Logger.CYAN}--- OPTIONAL COMPONENTS ---{Logger.END}")
        for i, item in enumerate(config_downloads, 1):
            status = f"{Logger.GREEN}[Installed]{Logger.END}" if item not in to_download else f"{Logger.YELLOW}[Missing]{Logger.END}"
            print(f" {i}. {item['name']:<45} {status}")

        print("\nCommands: [Numbers (1,3)], 'all', 'm' (Migrate), [Enter] (Skip)")
        choice = Downloader.get_input("Selection: ").lower().strip()

        if not choice: return
        if choice == 'm':
            old_path = Downloader.get_input("\nOld ComfyUI root: ").replace('"', '')
            if old_path: Downloader.migrate_models(old_path, comfy_path)
            return

        selected = to_download if choice == 'all' else []
        if choice != 'all':
            try:
                indices = [int(x) - 1 for x in choice.replace(',', ' ').split()]
                selected = [config_downloads[i] for i in indices if 0 <= i < len(config_downloads) and config_downloads[i] in to_download]
            except: Logger.error("Invalid selection.")

        for item in selected:
            dest_dir = comfy_path / item['type']
            Downloader.download(item['url'], dest_dir, item['name'], explicit_file=item.get('file'))