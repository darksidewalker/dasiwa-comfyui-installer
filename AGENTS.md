# 🤖 AGENTS.md: Autonomous Agent Operational Protocol

This document defines the system prompt extensions and technical boundaries for AI agents interacting with the **DaSiWa-ComfyUI-Installer**. Agents must adhere to these protocols to ensure environment isolation and cross-platform stability.

---

## 🏗️ Project Architecture & File Ownership

The project utilizes a **Modular Micro-Agent Pattern**. Logic is strictly siloed by domain.

### 🛠️ Core Utilities (`utils/`)
| Module | Agent Role | Responsibility |
| :--- | :--- | :--- |
| `utils/hardware.py` | **Hardware Scout** | Probes GPU (NVIDIA/AMD/Intel). Must handle PowerShell/SMI fallbacks. |
| `utils/downloader.py` | **Scavenger** | Handles GitHub API, recursive downloads, and model migration. |
| `utils/comfyui_clone.py` | **Version Controller** | Manages Git tags/branches for the core ComfyUI repository. |
| `utils/logger.py` | **Chronicler** | Standardizes ANSI color output. Use `Logger.log(text, level)`. |
| `utils/reporter.py` | **Analyst** | Compiles telemetry into a final installation summary. |
| `utils/task_nodes.py` | **Integrator** | Handles custom node cloning and recursive `pip` dependency resolution. |
| `utils/task_sageattention.py`| **Build Specialist** | Manages C++/CUDA source compilation for SageAttention v2. |

### 🚀 Entry Points & Orchestration
| File | Agent Role | Responsibility |
| :--- | :--- | :--- |
| `install.ps1 / .sh` | **Bootstrappers** | OS-level prep, `uv` acquisition, and Python bootstrapping. |
| `install_comfyui.py` | **Sentinel** | Self-update guardian. Compares hashes and hot-swaps logic scripts. |
| `setup_logic.py` | **Orchestrator** | Executes the main installation lifecycle and state management. |

---

## 🛠️ Operational Instructions for Agents

### 1. The "UV" Command Constraint
* **Constraint:** Never utilize standard `pip`. 
* **Protocol:** All package management must go through `uv`. When modifying `setup_logic.py` or `task_nodes.py`, ensure the `--python` path is explicitly passed to `uv pip install` to avoid polluting the system environment.

### 2. Configuration Hierarchy
* **Rule:** `config.local.json` (User) > `config.json` (Global).
* **Protocol:** Do not modify `config.json` to store user-specific paths or preferences. Agents should check for the existence of `config.local.json` and suggest modifications there first.

### 3. Hardware Sensitivity & Torch Mapping
* **Instruction:** The `Hardware Scout` determines the `torch` index URL. 
* **Protocol:** If hardware detection is modified, agents must maintain the "Mandatory Selection" fallback loop in `hardware.py`. Never assume a successful auto-detection; the UI must allow manual override to prevent "CPU-only" accidental installs.

### 4. Self-Healing & Hash Integrity
* **Instruction:** The system checks `.version_hash` on startup.
* **Protocol:** If modifying the core logic, agents must be aware that `install_comfyui.py` will attempt to overwrite local changes with the remote GitHub version unless the user is in a "Developer Mode" or the hash check is bypassed.

---

## 📂 Navigation & Modification Map

* **To add installation steps:** Edit `setup_logic.py`.
* **To update default dependencies:** Modify `PRIORITY_PACKAGES` in `setup_logic.py`.
* **To add default models/workflows:** Append to `optional_downloads` in `config.json`.
* **To fix cross-platform pathing:** Use `pathlib.Path` exclusively. Never use string concatenation for paths.

---

## 🛡️ Forbidden Actions for AI Agents

1. **DO NOT** suggest `pip install` commands to the user.
2. **DO NOT** hardcode absolute paths (e.g., `C:\Python312`). Use relative anchors from `Path.cwd()`.
3. **DO NOT** remove the `cleanup` logic in the bootstrappers that removes temporary extraction folders.
4. **DO NOT** modify `custom_nodes.txt` programmatically without preserving user comments (#).

---
**Agent Note:** Before performing any maintenance, run a `git status` check within the `ComfyUI` directory (if present) to verify which branch the **Version Controller** has targeted.