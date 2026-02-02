# Introduction

This is an installer script for my DaSiWa ComfyUI workflows that automates the following steps:

   1. ComfyUI Core: Clones the latest version of ComfyUI.

   2. Performance: Installs uv for lightning-fast package management.

   3. Environment: Creates a virtual Python 3.12 environment (venv).

   4. GPU Setup: Automatically detects NVIDIA GPUs and installs the correct PyTorch version (or halts for manual AMD setup).

   5. Custom Nodes: Installs a predefined list of custom nodes and their specific dependencies.

# Prerequisites

   1. Python 3.12 (Recommended)

   2. Git installed and added to your PATH.

   3. An NVIDIA GPU (for the automated Torch installation).

# Installation

## Alternative: Easy Entry (Auto-Check)

If you don't want to check for Python or Git manually, use these wrappers:

### Windows
Double-click `install.bat`. It will check for Git/Python and offer to install them via `winget` if they are missing.

### Linux
1. Make it executable: `chmod +x install.sh`
2. Run it: `./install.sh`
It will detect your distribution (Ubuntu, Arch, Fedora, etc.) and ask if you want to install missing packages via `sudo`.

Open your terminal/bash/PowerShell and run:
```
git clone https://github.com/darksidewalker/dasiwa-comfyui-installer && cd dasiwa-comfyui-installer && python install_comfyui.py
```
## Follow the prompts:

   - The script will ask you for an installation path.
   - Press Enter to install it in the current directory or provide a specific path.
   - The script will check if a ComfyUI folder already exists to prevent overwriting.

## After Installation

Once finished, you can start ComfyUI by navigating into the new ComfyUI folder and running:
### Windows
```
venv\Scripts\python.exe main.py
```
### Linux 
```
./venv/bin/python main.py
```
