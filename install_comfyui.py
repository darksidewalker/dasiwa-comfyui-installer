import urllib.request
import subprocess
import sys
import os

# Konfiguration - WICHTIG: Nutze hier auch die raw.githubusercontent URL
REMOTE_LOGIC_URL = "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/setup_logic.py"
LOCAL_LOGIC_NAME = "setup_logic.py"
CURRENT_VERSION = 1.0  # Version dieses Wrappers

def get_remote_version(url):
    try:
        # Kurzer Timeout, falls GitHub nicht erreichbar ist
        with urllib.request.urlopen(url, timeout=5) as response:
            first_line = response.readline().decode('utf-8')
            if "VERSION =" in first_line:
                # Extrahiert die Zahl hinter 'VERSION ='
                return float(first_line.split("=")[1].split("#")[0].strip())
    except Exception as e:
        print(f"Update-Check fehlgeschlagen: {e}")
        return None
    return None

def main():
    print(f"--- DaSiWa ComfyUI Installer (Wrapper v{CURRENT_VERSION}) ---")
    
    remote_version = get_remote_version(REMOTE_LOGIC_URL)
    
    should_download = False
    if not os.path.exists(LOCAL_LOGIC_NAME):
        print("[!] Setup-Logik fehlt. Lade Initialversion herunter...")
        should_download = True
    elif remote_version and remote_version > CURRENT_VERSION:
        print(f"[*] Neue Logik-Version {remote_version} gefunden. Aktualisiere...")
        should_download = True
    else:
        print("[+] Version ist aktuell oder Server nicht erreichbar.")

    if should_download:
        try:
            urllib.request.urlretrieve(REMOTE_LOGIC_URL, LOCAL_LOGIC_NAME)
            print("[+] Download erfolgreich.")
        except Exception as e:
            print(f"[-] Fehler beim Download: {e}")
            if not os.path.exists(LOCAL_LOGIC_NAME):
                sys.exit(1)

    # Führe die Logik aus
    print("--- Starte Installations-Logik ---\n")
    try:
        # Wir nutzen sys.executable, um denselben Python-Interpreter zu verwenden
        subprocess.run([sys.executable, LOCAL_LOGIC_NAME], check=True)
    except subprocess.CalledProcessError:
        print("\n[!] Die Installation wurde mit einem Fehler abgebrochen.")
    except Exception as e:
        print(f"\n[!] Unerwarteter Fehler: {e}")

if __name__ == "__main__":
    main()
