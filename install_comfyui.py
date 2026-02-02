import urllib.request
import subprocess
import sys
import os
from pathlib import Path

# Konfiguration
REMOTE_LOGIC_URL = "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/setup_logic.py"
LOCAL_LOGIC_NAME = "setup_logic.py"
CURRENT_VERSION = 1.1 

def get_remote_version(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            first_line = response.readline().decode('utf-8')
            if "VERSION =" in first_line:
                return float(first_line.split("=")[1].split("#")[0].strip())
    except:
        return None
    return None

def main():
    print(f"--- DaSiWa ComfyUI Installer (Wrapper v{CURRENT_VERSION}) ---")
    
    # --- NEU: Verhindere kaskadierte Installation ---
    current_path = Path.cwd()
    if current_path.name == "dasiwa-comfyui-installer" and (current_path / LOCAL_LOGIC_NAME).exists():
        # Wenn wir schon im Installer-Ordner sind, wollen wir nicht noch tiefer installieren
        # Wir setzen das Arbeitsverzeichnis eins höher, damit ComfyUI NEBEN dem Installer landet
        print("[!] Hinweis: Installer-Ordner erkannt. Installation erfolgt im übergeordneten Verzeichnis.")
        os.chdir("..")

    # --- NEU: Check ob ComfyUI bereits hier installiert ist ---
    if (Path.cwd() / "ComfyUI").exists():
        print(f"\n[!] ComfyUI wurde bereits im Verzeichnis '{Path.cwd()}' gefunden.")
        choice = input("Möchtest du das Script trotzdem ausführen? (Update/Reparatur nicht garantiert) (y/n): ")
        if choice.lower() != 'y':
            print("Abgebrochen.")
            sys.exit(0)

    # --- Update Logik ---
    remote_version = get_remote_version(REMOTE_LOGIC_URL)
    should_download = False
    
    if not os.path.exists(LOCAL_LOGIC_NAME):
        should_download = True
    elif remote_version and remote_version > CURRENT_VERSION:
        print(f"[*] Update verfügbar (v{remote_version}).")
        should_download = True

    if should_download:
        try:
            urllib.request.urlretrieve(REMOTE_LOGIC_URL, LOCAL_LOGIC_NAME)
        except Exception as e:
            print(f"[-] Download-Fehler: {e}")
            if not os.path.exists(LOCAL_LOGIC_NAME): sys.exit(1)

    # Starte Logik
    print("--- Starte Installations-Logik ---\n")
    try:
        subprocess.run([sys.executable, LOCAL_LOGIC_NAME], check=True)
    except subprocess.CalledProcessError:
        print("\n[!] Installation abgebrochen.")
    except Exception as e:
        print(f"\n[!] Fehler: {e}")

if __name__ == "__main__":
    main()
