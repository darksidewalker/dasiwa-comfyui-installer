# 🚀 DaSiWa ComfyUI Installer

A high-performance, one-click solution for ComfyUI. Built on a **Zero-Conflict** architecture, this installer uses `uv` to bypass traditional Python "dependency hell" and ensures a stable, portable environment for professional AI workflows.

## ✨ Core Features

* **uv-Engine:** Uses `uv` for package management—up to **10x faster** than standard `pip`.
* **Portable Python:** Automatically manages an isolated **Python 3.12** environment. No system-wide Python installation or Admin rights required.
* **Hardware-Aware:** Intelligent detection for **NVIDIA** (Pascal through Blackwell/50-series), **AMD**, and **Intel** GPUs with optimized Torch mapping.
* **Smart Node Sync:** Automated installation of nodes from `custom_nodes.txt`, supporting Git submodules and editable packages (`| pkg`).
* **Self-Healing Logic:** The installer automatically checks for logic updates and launcher improvements on every run.

## 🛡️ Zero-Conflict Architecture

To ensure your setup remains stable regardless of your OS configuration:
* **Alias Bypass:** Ignores broken Windows Store Python links.
* **Isolated Venv:** Everything is contained within the `ComfyUI/venv` folder. 
* **No Global Changes:** Does not touch your system PATH or global registry.
* **Pip-Less:** By using `uv` directly, we avoid the overhead and version-clash warnings common with standard `pip`.

## ⚙️ Configuration & Power-User Hints

The installer is data-driven. You can reconfigure almost every aspect by editing `config.json` or `custom_nodes.txt`.

### 1. Reconfiguring `config.json`

| Key | Purpose | Hint | 
| ----- | ----- | ----- | 
| `python.full_version` | The exact Python build used. | Change this if a specific node requires 3.11 or 3.13. | 
| `cuda.global` | The default CUDA version for Torch. | Default is `13.0`. Lower to `12.4` if using older plugins. | 
| `cuda.min_cuda_for_50xx` | Safety floor for new GPUs. | Ensures Blackwell/50-series GPUs get a compatible runtime. | 
| `urls.custom_nodes` | Remote node list source. | Point this to your own GitHub Gist to share your setup with friends. | 

### 2. Customizing `custom_nodes.txt`

You can modify this file locally to change which nodes are installed:
* **Standard:** `https://github.com/user/repo`
* **Submodules:** Add `| sub` at the end for nodes like **CosyVoice** that require nested git fetches.
* **Editable/Library:** Add `| pkg` for nodes that need to be installed as a system-link (Editable Install).

### 3. Manual "uv" Commands

If you need to manually add a package to the environment without breaking the installer's logic:
* **Windows:** `ComfyUI\venv\Scripts\uv pip install <package-name>`
* **Linux:** `./ComfyUI/venv/bin/uv pip install <package-name>`
  *Using `uv` instead of `pip` ensures the installer can still track and update the environment later.*

## 📥 Installation

To install, open your terminal (PowerShell for Windows, Bash for Linux) in the folder where you want the files to live and run the corresponding command:

### Windows (PowerShell)
PowerShell
```
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install.ps1 | iex"
```

### Linux (Bash)
Bash
```
curl -LsSf https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install.sh | bash
```

## 🛠️ Prerequisites

* GPU: An NVIDIA (GTX 10-series+), AMD, or Intel GPU.
* Git: Strictly required for cloning ComfyUI and managing Node updates.
* Internet: ~2GB of space and an active connection for the initial setup.

## ⚖️ Disclaimer

* As-Is: Provided as a community tool without official warranty.
* Hardware: AI generation is resource-intensive. Ensure adequate cooling.
* License: MIT License.