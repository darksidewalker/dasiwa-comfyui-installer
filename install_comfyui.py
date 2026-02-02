import urllib.request
import subprocess
import sys
import os

# Konfiguration
REMOTE_LOGIC_URL = "https://github.com/darksidewalker/dasiwa-comfyui-installer/main/setup_logic.py"
LOCAL_LOGIC_NAME = "setup_logic.py"
CURRENT_VERSION = 1.0  # Lokale Version dieses Wrappers

def get_remote_version(url):
    try:
        # Wir lesen nur die erste Zeile der Remote-Datei, um die Version zu finden
        with urllib.request.urlopen(url) as response:
            first_line = response.readline().decode('utf-8')
            if "VERSION =" in first_line:
                return float(first_line.split("=")[1].strip())
    except:
        return None
    return None

def main():
    print(f"--- Prüfe auf Updates (Aktuelle Version: {CURRENT_VERSION}) ---")
    
    remote_version = get_remote_version(REMOTE_LOGIC_URL)
    
    if remote_version and remote_version > CURRENT_VERSION:
        print(f"[*] Neue Version {remote_version} gefunden. Lade Update herunter...")
        urllib.request.urlretrieve(REMOTE_LOGIC_URL, LOCAL_LOGIC_NAME)
    elif not os.path.exists(LOCAL_LOGIC_NAME):
        print("[!] Setup-Logik fehlt. Lade Initialversion herunter...")
        urllib.request.urlretrieve(REMOTE_LOGIC_URL, LOCAL_LOGIC_NAME)
    else:
        print("[+] Version ist aktuell.")

    # Führe die Logik aus
    try:
        subprocess.run([sys.executable, LOCAL_LOGIC_NAME], check=True)
    except Exception as e:
        print(f"Fehler während der Ausführung: {e}")

if __name__ == "__main__":
    main()
