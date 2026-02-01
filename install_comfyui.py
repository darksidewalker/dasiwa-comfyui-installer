import urllib.request
import subprocess
import sys
import os

# URL zu deinem eigentlichen Installations-Script auf GitHub
REMOTE_SCRIPT_URL = "https://github.com/darksidewalker/dasiwa-comfyui-installer/main/setup_logic.py"
LOCAL_SCRIPT_NAME = "setup_logic.py"

def main():
    print(f"--- Lade Installations-Logik von {REMOTE_SCRIPT_URL} ---")
    try:
        urllib.request.urlretrieve(REMOTE_SCRIPT_URL, LOCAL_SCRIPT_NAME)
        print("--- Download abgeschlossen. Starte Installation... ---\n")
        
        # Startet das heruntergeladene Script mit dem aktuellen Python-Interpreter
        subprocess.run([sys.executable, LOCAL_SCRIPT_NAME], check=True)
    except Exception as e:
        print(f"Fehler: {e}")
    finally:
        if os.path.exists(LOCAL_SCRIPT_NAME):
            os.remove(LOCAL_SCRIPT_NAME)

if __name__ == "__main__":
    main()
