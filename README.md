# 🚀 DaSiWa ComfyUI Installer

This script provides a one-click installation experience for ComfyUI, optimized with **uv** for maximum speed. It automatically handles environments, GPU detection, and my specific set of Custom Nodes.

## ✨ Features

1. **ComfyUI Core:** Clones the latest official repository.
2. **Performance:** Installs `uv` for lightning-fast package management (up to 10x faster than standard pip).
3. **Environment:** Creates a virtual **Python 3.12** environment (`venv`).
4. **GPU Setup:** Automatically detects **NVIDIA GPUs** and installs the correct PyTorch version.
5. **Custom Nodes:** Installs a predefined list from `custom_nodes.txt` including all sub-dependencies.
6. **Auto-Update:** The installer checks for logic updates on every start.

## 🛠️ Prerequisites

* **Python 3.12** (Recommended)
* **Git** installed and added to your PATH.
* An **NVIDIA GPU** (required for the automated Torch installation).

---

## 📥 Installation

### Windows (PowerShell)
`PowerShell`
```
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install_comfyui.py" -OutFile "install.py"; python install.py
```
### Linux (Bash/Terminal)
`Bash`
```
curl -L -o install.py https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install_comfyui.py && python3 install.py
```

Follow the prompts:

- The script will ask for an installation path.
- Press Enter to install in the current directory or provide a specific path.
- The script will check if a ComfyUI folder already exists to prevent overwriting.

## 🚀 After Installation

Once finished, navigate into the new ComfyUI folder and start it using the virtual environment:

Use the `run_comfyui` inside your ComfyUI to start.
