# 🚀 DaSiWa ComfyUI Installer

This script provides a one-click installation experience for ComfyUI, optimized with **uv** for maximum speed. It automatically handles environments, GPU detection, and my specific set of Custom Nodes.

## ✨ Features

1. **ComfyUI Core:** Clones the latest official repository.
2. **Performance:** Installs `uv` for lightning-fast package management (up to 10x faster than standard pip).
3. **Environment:** Creates a virtual **Python** environment (`venv`).
4. **GPU Setup:** Automatically detects **GPUs** and installs the correct PyTorch version.
5. **Custom Nodes:** Installs a predefined list from `custom_nodes.txt` including all sub-dependencies.
6. **Auto-Update:** The installer checks for logic updates on every start.

## 🛠️ Prerequisites

* An **NVIDIA, AMD or Intel GPU** (required for the automated Torch installation).

---

# 📥 Installation

## Choose the method that fits your operating system:

1. Download this repository as a ZIP or clone it.
 
### Windows (Easy Way)
2. Double-click install.bat.
3. Follow the on-screen prompts.

### Linux (Easy Way)
2. Open your terminal in the folder.
3. Make the script executable and run it `Bash`
4.
```
chmod +x install.sh && ./install.sh
```

## Pro / Remote Installation (One-Liner)

If you don't want to download the whole repo and just want to start the Python process directly.

Requires already installed: 
- Git
- Python 3.12

### Windows (PowerShell):
`PowerShell`
```
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install_comfyui.py" -OutFile "install.py"; python install.py
```
### Linux (Bash):
`Bash`
```
curl -L -o install.py https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install_comfyui.py && python3 install.py
```
# 🚀 After Installation

Once finished, navigate into the new ComfyUI folder. You will find a launcher created by the script:

## Windows: 
Double-click `run_comfyui.bat`

## Linux: 
Run `./run_comfyui.sh`

##💡Hints

- The first start may need some time because of internal comfyui updates, manager pulls and frontend update.

# 🛠️ Configuration

To change the CUDA version or add more nodes, edit these files on your GitHub fork:
- setup_logic.py -> Change GLOBAL_CUDA_VERSION = "13.0"
- custom_nodes.txt -> Add your GitHub repo links

# Why Python 3.12
While 3.13 is out, many of the specialized wheels for the 5090 or other GPU's (like Triton and SageAttention) are currently most stable on 3.12.
