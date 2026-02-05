import urllib.request
import subprocess
import sys
import os
from pathlib import Path

# --- CONFIGURATION ---
REMOTE_LOGIC_URL = "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/setup_logic.py"
LOCAL_LOGIC_NAME = "temp_setup_logic.py"
CURRENT_VERSION = 1.4  # Updated to reflect launch feature

def main():
    print(f"--- DaSiWa ComfyUI Stand-alone Installer (v{CURRENT_VERSION}) ---")
    
    # 1. Path Check: Prevent installation inside the installer folder
    current_path = Path.cwd()
    if current_path.name == "dasiwa-comfyui-installer":
        print("[!] Notice: You are inside the installer repository folder.")
        print("[*] Moving up one level for a clean installation...")
        os.chdir("..")

    # 2. Check if ComfyUI already exists
    if (Path.cwd() / "ComfyUI").exists():
        print(f"\n[!] ComfyUI was already found in '{Path.cwd()}'.")
        choice = input("Do you want to proceed with Update/Overwrite? (y/n): ")
        if choice.lower() != 'y':
            sys.exit(0)

    # 3. Download the latest logic
    print("[*] Downloading installation logic from GitHub...")
    try:
        urllib.request.urlretrieve(REMOTE_LOGIC_URL, LOCAL_LOGIC_NAME)
    except Exception as e:
        print(f"[-] Error loading logic: {e}")
        sys.exit(1)

    # 4. Execute the Logic
    print("--- Starting Installation ---\n")
    success = False
    try:
        # We run the logic script
        subprocess.run([sys.executable, LOCAL_LOGIC_NAME], check=True)
        success = True
    except Exception as e:
        print(f"\n[!] Error during installation: {e}")

    # 5. Cleanup
    print("\n--- Cleanup ---")
    if os.path.exists(LOCAL_LOGIC_NAME):
        os.remove(LOCAL_LOGIC_NAME)
        print("[+] Temporary logic deleted.")

    # 6. --- LAUNCH LOGIC ---
    if success:
        print("\n" + "="*40)
        print("DONE! ComfyUI is installed.")
        print("Your installation is in the 'ComfyUI' folder.")
        print("="*40)
        
        launch = input("\nWould you like to launch ComfyUI now? (y/n): ").strip().lower()
        if launch == 'y':
            comfy_dir = Path.cwd() / "ComfyUI"
            os.chdir(comfy_dir)
            
            # Determine launcher name
            launcher = "run_comfyui.bat" if os.name == 'nt' else "./run_comfyui.sh"
            
            print(f"[*] Launching {launcher}...")
            try:
                if os.name == 'nt':
                    subprocess.Popen([launcher], creationflags=subprocess.CREATE_NEW_CONSOLE)
                else:
                    # On Linux, we run it through bash to ensure permissions
                    subprocess.Popen(["bash", launcher], start_new_session=True)
                print("[+] Launch signal sent. You can close this installer window.")
            except Exception as e:
                print(f"[!] Could not launch: {e}")

if __name__ == "__main__":
    main()
