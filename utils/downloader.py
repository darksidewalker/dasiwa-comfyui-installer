import urllib.request
import urllib.error
import os
import shutil
import time
import json
import socket
from pathlib import Path

from utils.logger import Logger


class Downloader:
    @staticmethod
    def get_input(prompt):
        return input(prompt)

    @staticmethod
    def check_connectivity(hosts=None):
        """Verify that the required hostnames are resolvable and reachable."""
        if hosts is None:
            hosts = ["github.com", "pypi.org", "download.pytorch.org"]
        
        Logger.log("Checking network connectivity...", "info")
        all_ok = True
        for host in hosts:
            try:
                # Perform a basic DNS lookup
                ip = socket.gethostbyname(host)
                Logger.debug(f" Resolved {host} to {ip}")
            except socket.gaierror:
                Logger.error(f"DNS lookup failed for {host}. "
                             "Check your internet connection or DNS settings.")
                all_ok = False
            except Exception as e:
                Logger.warn(f" Connectivity check failed for {host}: {e}")
                all_ok = False
        return all_ok

    # ---------- Remote lookup helpers ----------

    @staticmethod
    def get_latest_github_file(repo_path, folder):
        """
        Query the GitHub commits API for the most recently changed JSON file
        inside `folder`. Returns a dict {name, download_url} or None.
        """
        api_url = f"https://api.github.com/repos/{repo_path}/commits?path={folder}&per_page=1"
        headers = {'User-Agent': 'DaSiWa-Installer/1.0'}

        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                commits = json.loads(resp.read().decode())
                if not commits:
                    return None

                # Pull folder contents for direct download URLs
                contents_url = f"https://api.github.com/repos/{repo_path}/contents/{folder}"
                req_contents = urllib.request.Request(contents_url, headers=headers)
                with urllib.request.urlopen(req_contents, timeout=15) as resp_c:
                    files = json.loads(resp_c.read().decode())
                    json_files = [f for f in files if f['name'].endswith('.json')]
                    if not json_files:
                        return None

                    # Identify the file touched in the most recent commit
                    last_sha = commits[0]['sha']
                    detail_url = f"https://api.github.com/repos/{repo_path}/commits/{last_sha}"
                    req_detail = urllib.request.Request(detail_url, headers=headers)
                    with urllib.request.urlopen(req_detail, timeout=15) as resp_d:
                        detail = json.loads(resp_d.read().decode())
                        for f_changed in detail.get('files', []):
                            fn = f_changed['filename']
                            if fn.startswith(folder) and fn.endswith('.json'):
                                return {
                                    "name": os.path.basename(fn),
                                    "download_url": f_changed['raw_url'],
                                }

                    return {
                        "name": json_files[0]['name'],
                        "download_url": json_files[0]['download_url'],
                    }
        except urllib.error.HTTPError as e:
            if e.code == 404:
                Logger.warn(f"GitHub: '{repo_path}/{folder}' not found (404). "
                            f"Check repo_path and folder in config.")
            else:
                Logger.warn(f"GitHub API error {e.code} for {repo_path}/{folder}: {e.reason}")
            return None
        except Exception as e:
            Logger.warn(f"GitHub API unreachable for {repo_path}/{folder}: {e}")
            return None

    # ---------- Download core ----------

    @staticmethod
    def download(url, dest_folder, display_name, explicit_file=None, retries=3, delay=2):
        """
        Download with atomic write (.part -> rename) and content-length validation.
        Skips cleanly if the target already exists with a matching size.
        """
        filename = explicit_file if explicit_file else url.split('/')[-1].split('?')[0]
        dest = Path(dest_folder) / filename
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Pre-fetch Content-Length to validate existing files
        expected_size = None
        try:
            head_req = urllib.request.Request(
                url, method="HEAD", headers={'User-Agent': 'DaSiWa-Installer/1.0'}
            )
            with urllib.request.urlopen(head_req, timeout=10) as resp:
                cl = resp.headers.get("Content-Length")
                expected_size = int(cl) if cl else None
        except Exception:
            pass  # Not every server supports HEAD — fall through

        if dest.exists():
            actual = dest.stat().st_size
            if expected_size and actual != expected_size:
                Logger.warn(f" {filename} exists but size mismatch "
                            f"({actual} vs {expected_size}); redownloading.")
                dest.unlink()
            else:
                Logger.log(f" {filename} already exists. Skipping.", "ok")
                return

        tmp = dest.with_suffix(dest.suffix + ".part")
        for attempt in range(retries):
            try:
                Logger.log(f" Downloading {display_name} "
                           f"(Attempt {attempt + 1}/{retries})...", "info")
                req = urllib.request.Request(
                    url, headers={'User-Agent': 'DaSiWa-Installer/1.0'}
                )
                with urllib.request.urlopen(req, timeout=25) as response, open(tmp, 'wb') as out:
                    shutil.copyfileobj(response, out)

                if expected_size and tmp.stat().st_size != expected_size:
                    raise IOError(
                        f"size mismatch ({tmp.stat().st_size} vs {expected_size})"
                    )

                tmp.replace(dest)
                Logger.log(f" [DONE] {filename}", "ok")
                return

            except Exception as e:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
                if attempt < retries - 1:
                    Logger.warn(f" Error: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    Logger.error(f" Download failed for {display_name}: {e}")

    # ---------- Helpers ----------

    @staticmethod
    def file_exists_recursive(base_path, filename):
        if not filename:
            return False
        base_path = Path(base_path)
        return any(base_path.rglob(filename)) if base_path.exists() else False

    @staticmethod
    def migrate_models(old_comfy_path, new_comfy_path):
        old_models_root = Path(old_comfy_path) / "models"
        new_models_root = Path(new_comfy_path) / "models"
        if not old_models_root.exists():
            Logger.error(f"Source models folder not found: {old_models_root}")
            return

        Logger.log(f"Starting migration from {old_models_root}...", "info")
        for item in list(old_models_root.iterdir()):
            if item.is_symlink() or not item.is_dir():
                continue
            for file_item in list(item.rglob("*")):
                if file_item.is_dir() or file_item.is_symlink():
                    continue
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
                            Logger.log(" [!] Link-back failed (Requires Admin/Privileges).",
                                       "warn")
                    except Exception as e:
                        Logger.error(f" [!] Error moving {relative_path}: {e}")
        Logger.success("Migration Finished.")

    # ---------- Interactive picker (used by the pre-flight wizard) ----------

    @staticmethod
    def filter_missing(config_downloads, comfy_path):
        """Return only the items that are not yet installed and have a resolvable URL."""
        comfy_path = Path(comfy_path)
        missing = []
        for item in config_downloads:
            # Resolve 'latest' items via GitHub API
            if item.get('version') == 'latest' and 'repo_path' in item:
                latest = Downloader.get_latest_github_file(item['repo_path'], item['folder'])
                if latest:
                    item['file'] = latest['name']
                    item['url'] = latest['download_url']
                    if "(Latest:" not in item['name']:
                        item['name'] = f"{item['name']} (Latest: {latest['name']})"
                else:
                    # Remote lookup failed — skip this item entirely. No URL to download from.
                    Logger.warn(f"Skipping '{item.get('name', '?')}': "
                                f"could not resolve latest version from GitHub.")
                    continue

            # Any item that reaches this point must have a URL to be downloadable
            if not item.get('url'):
                Logger.warn(f"Skipping '{item.get('name', '?')}': no URL available.")
                continue

            search_root = comfy_path / "models" if "models" in item['type'] else comfy_path
            filename = item.get('file')
            # If we don't have a filename yet and it's not a 'latest' item, derive from URL
            if not filename:
                filename = item['url'].split('/')[-1].split('?')[0]
                item['file'] = filename

            if not Downloader.file_exists_recursive(search_root, filename):
                missing.append(item)
        return missing

    @staticmethod
    def install_selected(selected, comfy_path):
        """Download every entry in `selected`."""
        for item in selected:
            if not item.get('url'):
                Logger.warn(f"Skipping '{item.get('name', '?')}': no URL to download from.")
                continue
            dest_dir = Path(comfy_path) / item['type']
            try:
                Downloader.download(
                    item['url'], dest_dir, item['name'],
                    explicit_file=item.get('file'),
                )
            except Exception as e:
                Logger.error(f"Download failed for {item.get('name', '?')}: {e}")
