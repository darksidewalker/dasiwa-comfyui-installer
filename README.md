<div align="center">

# DaSiWa ComfyUI Installer

**One command. Walk away. Come back to a working ComfyUI.**

A professional-grade installer for [ComfyUI](https://github.com/comfyanonymous/ComfyUI) built on a zero-conflict, fully isolated architecture. No Python knowledge required. No admin rights needed. No system files touched.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-blue)]()
[![Python](https://img.shields.io/badge/python-3.12-brightgreen)]()

</div>

---

## What it does

You run one command in a terminal. The installer asks you a handful of questions — all upfront, before touching a single file — then handles everything else unattended:

- Downloads and configures a **fully portable Python 3.12 environment** isolated inside your ComfyUI folder
- Clones ComfyUI at the latest stable release tag or a specific version you choose
- Detects your GPU and installs the **exact right PyTorch build** for your hardware
- Optionally installs **SageAttention**, **FFmpeg**, and a curated set of **custom nodes**
- Creates a ready-to-launch `run_comfyui` starter in your ComfyUI folder
- On subsequent runs, detects what's already installed and asks whether to update, refresh, or leave it alone

---

## Quick Install

Open a terminal **in the folder where you want ComfyUI to live**, then run:

### Windows (PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -Command "curl.exe -L -o install.ps1 https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install.ps1; .\install.ps1"
```

### Linux (Bash)

```bash
curl -OC - https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install.sh && chmod +x install.sh && ./install.sh
```

That's it. The bootstrapper fetches the rest automatically.

---

## Prerequisites

| Requirement | Notes |
| :---------- | :---- |
| **GPU** | NVIDIA (GTX 10-series or newer), AMD (RX 6000+), or Intel Arc |
| **Internet** | Active connection; ~20 GB free disk space for a full install with models |
| **Git** | Auto-installed on Windows if missing (fetches the latest release automatically). Required on Linux: `sudo apt install git` |
| **Admin rights** | Not required |

---

## The Setup Wizard

When you run the installer, it opens a guided wizard that collects all your decisions **before** anything is downloaded or changed. You review a summary and confirm once. After that, you can walk away.

```
╔══════════════════════════════════════════════════════════════╗
║                    DaSiWa Setup Wizard                       ║
║           Configure once, confirm once, walk away            ║
╚══════════════════════════════════════════════════════════════╝
```

**The wizard asks:**

1. **What to do with an existing install** — Update in place, Refresh the environment, Full reinstall, or Cancel. Nothing destructive happens without your explicit confirmation.
2. **SageAttention** — yes or no. On Windows with CUDA 13.x selected, it warns you about the upstream compatibility issue and offers to downgrade the CUDA target to 12.8 for this install only (your `config.json` is never modified).
3. **FFmpeg** — yes or no. Skipped automatically if already present.
4. **Optional models and workflows** — shows only what isn't already on disk. Pick by number, type `all`, or press Enter to skip.
5. **Summary + single confirmation** — review everything, then proceed or cancel.

---

## Hardware Support

GPU detection is automatic. If detection fails, you get a manual selection menu — a CPU-only install is never silently allowed.

| Vendor | Series | PyTorch Build |
| :----- | :----- | :------------ |
| **NVIDIA** | RTX 20 / 30 / 40 | CUDA 13.0 (configurable) |
| **NVIDIA** | RTX 50 (Blackwell) | CUDA 12.8 + `--pre` nightly |
| **NVIDIA** | GTX 10 / Pascal | CUDA 12.1 + Torch 2.4.1 (locked) |
| **AMD** | RX 7000 / GFX110x | ROCm nightly `gfx110X-all` |
| **AMD** | RX 9000 / GFX120x | ROCm nightly `gfx120X-all` |
| **AMD** | Other Radeon | ROCm 7.1 stable |
| **Intel** | Arc / iGPU | XPU wheel |

Detection uses `nvidia-smi` and `lspci` (Linux) or `Win32_VideoController` (Windows), with a weighted sort that ensures a discrete GPU always wins over an integrated one sharing the same system.

---

## SageAttention

SageAttention delivers significantly faster attention kernels for NVIDIA GPUs. The installer handles the full complexity of getting it working:

**Windows — prebuilt wheel (default)**
Queries the [woct0rdho/SageAttention](https://github.com/woct0rdho/SageAttention) release API at install time, finds the ABI3 wheel that matches your installed Torch version and CUDA tag, and installs it in seconds. No compiler needed for most users.

**Windows — source build (fallback)**
If no matching prebuilt wheel exists, falls back to a full CUDA source build with proper MSVC environment loading (`vcvars64.bat` is sourced and verified, `CUDA_HOME` is auto-detected, `DISTUTILS_USE_SDK=1` is set). Build parallelism is tuned to your available RAM to avoid out-of-memory linker failures.

**Linux**
Source build via `uv pip install --no-build-isolation`, with a dependency check for `nvcc` and `g++`/`clang++` before starting.

**CUDA 12.8 auto-downgrade (Windows only)**
If your config targets CUDA 13.x and you request SageAttention, the wizard warns you that this combination has a known upstream build failure (a namespace collision in PyTorch's `compiled_autograd.h`) and offers to target CUDA 12.8 for this install only. Your `config.json` is never written.

---

## Custom Nodes

Nodes are managed from a plain text list. Each line is a GitHub repo URL with optional flags:

```
# Standard clone
https://github.com/user/node

# Recursive clone for nodes with git submodules (e.g. CosyVoice, Foley)
https://github.com/user/node | sub

# Editable/library install (pip install -e .)
https://github.com/user/node | pkg

# Custom requirements filename
https://github.com/user/node | req:requirements-no-cupy.txt

# Flags can be combined
https://github.com/user/node | sub | req:requirements-custom.txt
```

Lines starting with `#` are comments and are preserved on every update. After all nodes are installed, the **Enforcer** runs — a final `uv pip install --upgrade` pass over a set of priority packages to ensure no node has silently downgraded a critical dependency.

**To use your own node list:** create `custom_nodes.local.txt` in the installer root. It takes full precedence over the default list and over the remote URL in `config.json`. It is gitignored and will never be overwritten by an update.

---

## Idempotent by Design

Running the installer a second time is safe. It detects existing state before asking any questions:

- **ComfyUI already present?** Offers Update / Refresh / Full reinstall / Cancel.
- **Venv already set up?** Reused in Update mode; rebuilt only in Refresh or Reinstall.
- **SageAttention already importable?** Skipped entirely.
- **FFmpeg already in PATH or in `ComfyUI/ffmpeg/`?** Skipped.
- **Models already downloaded?** Checked by filename and file size. Truncated or missing files are re-fetched; complete files are skipped.

---

## FFmpeg

FFmpeg is needed by video nodes like VideoHelperSuite, MMAudio, and WhiteRabbit.

- **Windows:** Downloads a portable build (BtbN GPL zip), extracts it to `ComfyUI/ffmpeg/`, and injects the path into the generated launcher script so all child processes inherit it automatically.
- **Linux:** Detects your package manager (`apt-get`, `pacman`, `dnf`, `zypper`, or Homebrew) and installs the system package.
- Both paths skip installation if `ffmpeg` is already reachable in PATH or a local copy already exists.

---

## Architecture: Zero Conflict

Everything lives inside the `ComfyUI/` folder the installer creates. Nothing outside it is modified.

| What | Where | Notes |
| :--- | :---- | :---- |
| Python runtime | `ComfyUI/venv/` | Managed by `uv`, fully portable |
| ComfyUI itself | `ComfyUI/` | Pinned to a specific git tag or `master` |
| Custom nodes | `ComfyUI/custom_nodes/` | Cloned and updated by the installer |
| Portable FFmpeg | `ComfyUI/ffmpeg/bin/` | Windows only; injected into launcher PATH |
| Launcher | `ComfyUI/run_comfyui.bat` / `.sh` | Opens browser + starts server |
| SageAttention | Inside venv | Built against the venv Python |

Your system Python, system PATH, and Windows registry are never touched.

**Package management:** All package operations go through `uv`, which is up to 10× faster than pip and resolves dependencies without version-clash warnings. You should never use `pip` directly in this environment.

To manually add a package:

```
# Windows
.\ComfyUI\venv\Scripts\uv pip install <package-name>

# Linux
./ComfyUI/venv/bin/uv pip install <package-name>
```

---

## Self-Updating Logic

The launcher (`install_comfyui.py`) checks its own commit hash against the repository on every run. If a newer version of the installer logic exists upstream, it downloads the update atomically and restarts. This ensures you always get bug fixes and new GPU support without re-running the bootstrapper.

To develop or test local changes without being overwritten, set `DASIWA_NO_UPDATE=1` in your environment before running.

---

## Configuration

The installer is fully data-driven. All defaults live in `config.json`. To override any setting, create `config.local.json` — it is deep-merged over the defaults at runtime and will never be overwritten by an update.

```json
{
    "python": { "display_name": "3.13" },
    "comfyui": { "version": "v0.3.9" },
    "cuda": { "global": "12.8" }
}
```

Only include the keys you want to change. Everything else inherits from `config.json`.

### Full `config.json` reference

| Key | Default | Purpose |
| :-- | :------ | :------ |
| `python.display_name` | `"3.12"` | Python version passed to `uv python install` |
| `python.full_version` | `"3.12.10"` | Exact micro-version for strict pinning |
| `comfyui.version` | `"latest"` | `"latest"` = newest git tag; any other value = specific tag |
| `comfyui.fallback_branch` | `"master"` | Used if the targeted tag checkout fails |
| `cuda.global` | `"13.0"` | CUDA wheel target for NVIDIA (all non-legacy cards) |
| `cuda.min_cuda_for_50xx` | `"12.8"` | Minimum CUDA for Blackwell / RTX 50-series |
| `urls.custom_nodes` | GitHub raw URL | Remote node list source — point to your own Gist to sync across machines |
| `urls.ffmpeg_windows` | BtbN release URL | Portable FFmpeg zip for Windows |
| `urls.sage_repo` | thu-ml/SageAttention | SageAttention source for the fallback build |
| `urls.msvc_build_tools` | VS download page | Opened in-browser when MSVC is missing |
| `optional_downloads` | — | Models and workflows offered in the wizard |

### Adding models and workflows

To add items to the optional downloads menu, append to `optional_downloads` in `config.json`:

```json
{
    "name": "My Model",
    "type": "models/checkpoints",
    "url": "https://huggingface.co/.../my-model.safetensors"
}
```

For GitHub-hosted assets with a `"latest"` version, include `repo_path` and `folder` instead of `url` — the installer queries the GitHub commits API to find the most recently updated file.

---

## Run Modes

When an existing install is detected, the wizard offers four choices:

| Mode | What happens |
| :--- | :----------- |
| **Update in place** | Pulls ComfyUI changes, re-syncs nodes, reuses the existing venv |
| **Refresh environment** | Rebuilds the venv from scratch, reinstalls all packages, keeps models |
| **Full reinstall** | Deletes the entire ComfyUI folder and starts over (double-confirmed) |
| **Cancel** | Exits without touching anything |

---

## Tuning SageAttention Builds

For power users who need to tune source build performance, three environment variables override the defaults before running the installer:

| Variable | Default | Effect |
| :------- | :------ | :----- |
| `DASIWA_SAGE_MAX_JOBS` | auto (RAM-based) | Parallel linker jobs |
| `DASIWA_SAGE_EXT_PARALLEL` | `2` | Parallel CUDA extension builds |
| `DASIWA_SAGE_NVCC_THREADS` | `--threads 4` | NVCC thread count |

The defaults are deliberately conservative — each MSVC/nvcc linker job peaks at ~3 GB RAM. Increasing `MAX_JOBS` beyond what your RAM supports will OOM during the link phase.

---

## Disclaimer

Provided as a community tool, as-is, without warranty. AI generation is resource-intensive — ensure adequate cooling. See [LICENSE](LICENSE) for full terms (MIT).
