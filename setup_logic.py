import subprocess
import os
import sys
import platform
import urllib.request

# URLs zu deinen Dateien auf GitHub
NODES_LIST_URL = "https://github.com/darksidewalker/dasiwa-comfyui-installer/main/custom_nodes.txt"
NODES_LIST_FILE = "custom_nodes.txt"

def run_cmd(cmd, shell=False):
    # Hilfsfunktion zum Ausführen von Befehlen
    subprocess.run(cmd, shell=shell, check=True)

def main():
    # 1. ComfyUI clonen
    if not os.path.exists("ComfyUI"):
        print("--- Cloning ComfyUI ---")
        run_cmd(["git", "clone", "https://github.com/comfyanonymous/ComfyUI"])
    os.chdir("ComfyUI")

    # 2. UV installieren
    print("--- Prüfe uv Installation ---")
    try:
        run_cmd(["uv", "--version"])
    except:
        if platform.system() == "Windows":
            run_cmd("powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\"", shell=True)
        else:
            run_cmd("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
        os.environ["PATH"] += os.pathsep + os.path.expanduser("~/.cargo/bin")

    # 3. & 4. Venv und Pip/UV Setup
    print("--- Erstelle venv (Python 3.12) ---")
    run_cmd(["uv", "venv", "venv", "--python", "3.12"])
    
    # Pfade für die Aktivierung / Nutzung
    suffix = "\\" if platform.system() == "Windows" else "/"
    python_exe = f"venv{suffix}Scripts{suffix}python.exe" if platform.system() == "Windows" else f"venv/bin/python"

    # 5. GPU Check & Torch Installation
    gpu_type = "none"
    try:
        if subprocess.run(["nvidia-smi"], capture_output=True).returncode == 0:
            gpu_type = "nvidia"
    except: pass

    if gpu_type == "nvidia":
        print("--- Installiere Torch (CUDA 12.1) ---")
        # uv pip install im Kontext der venv
        run_cmd(["uv", "pip", "install", "torch", "torchvision", "torchaudio", "--extra-index-url", "https://download.pytorch.org/whl/cu121"])
    else:
        print("Abbruch: Keine Nvidia GPU gefunden (AMD/Intel Support nicht im Script).")
        sys.exit(1)

    # 6. Haupt-Requirements
    print("--- Installiere ComfyUI Requirements ---")
    run_cmd(["uv", "pip", "install", "-r", "requirements.txt"])

    # 7. Custom Nodes aus externer TXT laden
    print("--- Lade Custom Nodes Liste ---")
    try:
        urllib.request.urlretrieve(NODES_LIST_URL, NODES_LIST_FILE)
        with open(NODES_LIST_FILE, "r") as f:
            repos = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except Exception as e:
        print(f"Konnte Liste nicht laden: {e}")
        repos = []

    if not os.path.exists("custom_nodes"):
        os.makedirs("custom_nodes")
    
    base_dir = os.getcwd()
    for repo in repos:
        repo_name = repo.split("/")[-1].replace(".git", "")
        target_path = os.path.join("custom_nodes", repo_name)
        
        print(f"--- Setup Node: {repo_name} ---")
        if not os.path.exists(target_path):
            run_cmd(["git", "clone", repo, target_path])
        
        node_req = os.path.join(target_path, "requirements.txt")
        if os.path.exists(node_req):
            print(f"Installiere Abhängigkeiten für {repo_name}...")
            run_cmd(["uv", "pip", "install", "-r", node_req])

    print("\n--- Installation fertig! ---")
    print(f"Starte mit: {python_exe} main.py")

if __name__ == "__main__":
    main()
