import urllib.request
import subprocess
import sys
import os
from pathlib import Path

# --- KONFIGURATION ---
# Nutzt direkt die Raw-URLs von GitHub
REMOTE_LOGIC_URL = "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/setup_logic.py"
LOCAL_LOGIC_NAME = "temp_setup_logic.py"
CURRENT_VERSION = 1.2

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
    print(f"--- DaSiWa ComfyUI Stand-alone Installer (v{CURRENT_VERSION}) ---")
    
    # 1. Pfad-Check: Verhindere Installation IM Installer-Ordner, falls doch geklont wurde
    current_path = Path.cwd()
    if current_path.name == "dasiwa-comfyui-installer":
        print("[!] Hinweis: Du befindest dich in einem Installer-Ordner.")
        print("[*] Wechsel eine Ebene höher, um ComfyUI sauber zu installieren...")
        os.chdir("..")

    # 2. Prüfe ob ComfyUI schon da ist
    if (Path.cwd() / "ComfyUI").exists():
        print(f"\n[!] ComfyUI wurde bereits in '{Path.cwd()}' gefunden.")
        choice = input("Möchtest du fortfahren? (y/n): ")
        if choice.lower() != 'y':
            sys.exit(0)

    # 3. Lade die aktuellste Logik herunter
    print("[*] Lade Installations-Logik von GitHub...")
    try:
        urllib.request.urlretrieve(REMOTE_LOGIC_URL, LOCAL_LOGIC_NAME)
    except Exception as e:
        print(f"[-] Fehler beim Laden der Logik: {e}")
        sys.exit(1)

    # 4. Führe die Logik aus
    print("--- Starte Installation ---\n")
    try:
        # Wir übergeben den aktuellen Pfad als Argument, falls die Logik ihn braucht
        subprocess.run([sys.executable, LOCAL_LOGIC_NAME], check=True)
        success = True
    except Exception as e:
        print(f"\n[!] Fehler während der Installation: {e}")
        success = False

    # 5. --- SELF-DESTRUCT & CLEANUP ---
    print("\n--- Bereinigung ---")
    try:
        if os.path.exists(LOCAL_LOGIC_NAME):
            os.remove(LOCAL_LOGIC_NAME)
            print("[+] Temporäre Logik gelöscht.")
        
        # Optional: Das Script löscht sich selbst (der Wrapper)
        # Wenn du das Script behalten willst, kommentiere die nächste Zeile aus
        script_path = __file__
        if success:
            print("[+] Installation erfolgreich abgeschlossen.")
            # os.remove(script_path) # Aktivieren für totalen Self-Destruct
    except:
        pass

    if success:
        print("\n" + "="*40)
        print("FERTIG! Du kannst dieses Fenster nun schließen.")
        print("Deine Installation befindet sich im Ordner 'ComfyUI'.")
        print("="*40)

if __name__ == "__main__":
    main()
