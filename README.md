# 🚀 DaSiWa ComfyUI Installer

A high-performance, one-click solution for ComfyUI. Built on a **Zero-Conflict** architecture, this installer uses `uv` to bypass traditional Python "dependency hell" and ensures a stable, portable environment for professional AI workflows.

## ✨ Core Features

* **uv-Engine:** Uses `uv` for package management—up to **10x faster** than standard `pip`.
* **Portable Python:** Automatically manages an isolated **Python 3.12** environment. No system-wide Python installation or Admin rights required.
* **Hardware-Aware:** Intelligent detection for **NVIDIA** (Pascal through Blackwell/50-series), **AMD**, and **Intel** GPUs with optimized Torch mapping.
* **Smart Node Sync:** Automated installation of nodes from `custom_nodes.txt`, supporting Git submodules and editable packages (`| pkg`).
* **Self-Healing Logic:** The installer automatically checks for logic updates and launcher improvements on every run.
* **Sage-Attention v2:** The installer can optionally try to build and install Sage-Attention v2 into the portable environment.
* **Starters:** Creates convenient "run_comfyui" starters with predefined parameters (inside the ComfyUI folder).

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

# 🛠️ Advanced Customization & Tweaking

The installer is designed to be "set and forget," but if you need to target specific hardware, private node lists, or custom Python versions, you can bypass the defaults using the **Local Override** system.

## 1. The Override Layer (`config.local.json`)
**Rule #1:** Do not edit `config.json` directly. Updates to the repository will overwrite your changes. Instead, create a file named `config.local.json` in the root directory. The installer will automatically merge these settings over the defaults.

### Key Configuration Overrides
| Key Path | Purpose | Why change it? |
| :--- | :--- | :--- |
| `python.display_name` | The broad Python version (e.g., `3.13`) | **Primary Control:** Use this to let UV find the best matching installed version (3.13.x). |
| `python.full_version` | The exact micro-version (e.g., `3.13.12`) | Use this only if a specific node requires an exact build. |
| `cuda.global` | The default CUDA version for Torch. | Default is `13.0`. Lower to `12.1` or `12.4` for older plugins or GPUs. |
| `cuda.min_cuda_for_50xx` | Safety floor for Blackwell GPUs. | Ensures RTX 50-series get the required `12.8+` runtime. |
| `urls.custom_nodes` | Remote node list source. | Point this to your own GitHub Gist to sync your personal setup across machines. |

> **Note:** The installer performs a "deep merge." If you only want to change the Python version, your `config.local.json` only needs to contain the `python` section.

---

## 2. Customizing `custom_nodes.txt`
You can modify this file locally to change which extensions are installed. The installer identifies special requirements based on flags added to the end of the URL:

* **Standard:** `https://github.com/user/repo`
    * A standard git clone.
* **Submodules (`| sub`):** `https://github.com/user/repo | sub`
    * Required for nodes like **CosyVoice** or **Foley** that use nested git repositories.
* **Editable/Library (`| pkg`):** `https://github.com/user/repo | pkg`
    * Installs the node folder as a system-link (Editable Install). Necessary for nodes that function as shared libraries.

---

## 3. Manual "uv" Commands
This installer uses **uv** for maximum speed and environment isolation. To manually add a package without breaking the installer's logic or "Enforcer" rules, use the following commands from the root folder:

### **Windows**
```
.\ComfyUI\venv\Scripts\uv pip install <package-name>
```

### **Linux**
```
./ComfyUI/venv/bin/uv pip install <package-name>
```

Using uv instead of standard pip ensures the environment remains optimized and the installer can continue to track updates correctly.

## 4. Hardware Fallbacks

If the automated GPU detection fails or you want to force a specific mode for testing, the installer provides a Mandatory Selection menu:

* **NVIDIA Modern:** Standard path using the cuda.global version (Default 13.0).

* **NVIDIA Legacy:** Forces CUDA 12.1 and Torch 2.4.1. Use this for GTX 10-series (Pascal) cards to avoid compatibility crashes.

* **AMD Experimental:** Targets the latest ROCm nightlies for GFX11/12 (RX 7000/9000) hardware.

* **Intel:** Targets Intel Arc/iGPU using the xpu torch wheel.

## 📥 Installation

To install, open your terminal (PowerShell for Windows, Bash for Linux) in the folder where you want the files to live and run the corresponding command:

### Windows (PowerShell)
PowerShell
```
powershell -ExecutionPolicy Bypass -Command "curl.exe -L -o install.ps1 https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install.ps1; .\install.ps1"
```

### Linux (Bash)
Bash
```
curl -OC - https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install.sh && chmod +x install.sh && ./install.sh
```

## 🛠️ Prerequisites

* GPU: An NVIDIA (GTX 10-series+), AMD, or Intel GPU.
* Git: Strictly required for cloning ComfyUI and managing Node updates.
* Internet: ~2GB of space and an active connection for the initial setup.

## ⚖️ Disclaimer

* As-Is: Provided as a community tool without official warranty.
* Hardware: AI generation is resource-intensive. Ensure adequate cooling.
* License: MIT License.