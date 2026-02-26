# 🚀 DaSiWa ComfyUI Installer

This script provides a one-click installation experience for ComfyUI, optimized with **uv** for maximum speed. It automatically handles environments, GPU detection, and my specific set of Custom Nodes.

## ✨ Features

1. **ComfyUI Core:** Clones the latest official repository.
2. **Performance:** Installs `uv` for lightning-fast package management (up to 10x faster than standard pip).
3. **Environment:** Creates a virtual **Python** environment (`venv`).
4. **GPU Setup:** Automatically detects **GPUs** and installs the correct PyTorch version.
5. **Custom Nodes:** Installs a predefined list from `custom_nodes.txt` including all sub-dependencies.
6. **Auto-Update:** The installer checks for logic updates on every start.
7. **Starters:** Creates convenient "run_comfyui" starters with predefined parameters (inside the ComfyUI folder.

### 🛡️ Zero-Conflict Design (New Section)

This installer is designed to be "invisible" to your operating system:

- Ignores Windows Store Aliases: It bypasses the "fake" Python links that often break AI installations.
- No Admin Rights: Since Python is downloaded as a portable folder, you don't need administrator privileges to "install" it.
- Strict Versioning: By locking to Python via config.json, we ensure high-performance libraries like Triton and SageAttention remain stable.

## 🛠️ Prerequisites

- GPU: An NVIDIA, AMD, or Intel GPU (required for automated Torch optimization).
- No Python Installation Required: The installer now uses uv to automatically download and manage a portable, isolated Python environment. You do not need to install  Python on your system manually.
- Internet Connection: Required for the initial download of the portable Python binary and ComfyUI components.

---

# 📥 Installation

## Choose the method that fits your operating system:

1. Download the fitting installer file.
 
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
- Python
- Git

### Windows (PowerShell):
`PowerShell`
```
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install.ps1 | iex"
```
### Linux (Bash):
`Bash`
```
curl -LsSf https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install.sh | bash
```
# 🚀 After Installation

Once finished, navigate into the new ComfyUI folder. You will find a launcher created by the script:

## Windows: 
Double-click `run_comfyui.bat`

## Linux: 
Run `./run_comfyui.sh`

## 💡Hints

- The first start may need some time because of internal comfyui updates, manager pulls and frontend update.

# 🛠️ Configuration & Customization

## 1. Core Installer Settings

Core Installer Settings (config.json)

The installer is data-driven. To change the environment, edit config.json in the root folder. No coding required.

### Setting	description

**python**:	Define the version to hunt for. Change pathon versions (e.g., "3.12.10", "312" and "3.12") to update the download source.

**cuda**:	`Global` sets the default toolkit. The installer automatically downshifts to 12.1 for GTX 10-series (Pascal) and shifts to nightly for RTX 50-series (Blackwell).

**url**:	    Update any url point to your own fork or a different list of repositories

## 2. Managing Nodes

Edit custom_nodes.txt on your fork to add or remove repos.

Use `| pkg` for nodes that need an editable pip install.
Use `| sub` for nodes with submodules (like CosyVoice).

## 3. Running & Customizing Startup

The installer generates a optimized launcher script in the root ComfyUI folder. Always use these launchers to ensure your virtual environment and hardware optimizations are correctly loaded.

### 🛠️ Adding Startup Arguments

If you want to change how ComfyUI runs (e.g., adding `--lowvram`, changing the port, or enabling `--listen`), you should edit the launcher files rather than running Python commands manually.
Operating System	File to Edit	How to Customize

**Windows**	run_comfyui.bat	Right-click -> Edit. Add flags to the end of the line starting with python.exe.

**Linux**	run_comfyui.sh	Open in any text editor. Add flags to the end of the line starting with python.

#### Example customization for low-end GPUs:

In run_comfyui.sh / .bat
```
python main.py --preview-method auto --lowvram --gpu-only
```
## 🔍 What the Launchers Do

To keep your experience stable, these scripts perform the following actions every time they start:

- Environment Locking: They force the system to use the internal venv, preventing conflicts with global Python installs.
- Log Maintenance: They clear the previous user/comfyui.log so you always have a fresh, readable log if a crash occurs.
- Auto-Browser: They attempt to open your browser to http://127.0.0.1:8188 automatically after a short delay.

# 🐍 Why Python 3.12
While 3.13 is out, many of the specialized wheels for the 5090 or other GPU's (like Triton and SageAttention) are currently most stable on 3.12.

# ⚖️ Disclaimer & Terms of Use

TL;DR: This is a free community tool. I built it to be helpful, but use it at your own risk.

"As-Is" Software: This installer is provided without any guarantees. It might work perfectly, or it might need manual tweaking for your specific setup.

No Liability: I (the author) am not responsible for any system errors, data loss, or hardware issues that occur while using this script.

Third-Party Content: This script downloads software from external sources (Python, PyTorch, ComfyUI, etc.). Their respective licenses and terms apply to those components.

Hardware Responsibility: High-performance tasks like AI generation put stress on your hardware. Ensure your system has adequate cooling and a proper power supply.
    
Legal Standard: THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED. IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE.
