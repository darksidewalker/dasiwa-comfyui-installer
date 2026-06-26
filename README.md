<div align="center">

# DaSiWa ComfyUI Installer

**One binary. Walk away. Come back to a working ComfyUI.**

A professional-grade installer for [ComfyUI](https://github.com/comfyanonymous/ComfyUI) built on a zero-conflict, fully isolated architecture. No Python knowledge required. No admin rights needed. No system files touched.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-blue)]()
[![Python](https://img.shields.io/badge/python-3.12-brightgreen)]()

</div>

![DaSiWa ComfyUI Installer](assets/DaSiWa-ComfyUI-Installer.webp)

---

## Unified One-Page Installer

The installer now presents the full setup on a single local page. Folder
selection, install mode, GPU and CUDA target, SageAttention, FFmpeg, optional
downloads, and the final install plan are all visible at once, with no separate
pages or script chain to follow.

That unified layout is deliberate:

- Choose the ComfyUI folder once.
- Pick the install mode once.
- Review hardware and version overrides in the same view.
- Toggle SageAttention, FFmpeg, and optional downloads without leaving the page.
- Inspect the live JSON plan before starting the install.
- Use **Extra Settings** for in-memory overrides without mutating the embedded defaults.

---

## What it does

You run the standalone installer binary. It opens a local web UI, asks you a
handful of questions upfront, then handles everything else unattended:

- Downloads and configures a **fully portable Python 3.12 environment** isolated inside your ComfyUI folder
- Clones ComfyUI at the latest stable release tag or a specific version you choose
- Detects your GPU and installs the **exact right PyTorch build** for your hardware
- Optionally installs **SageAttention**, **RadialAttention**, **FlashAttention**, **FFmpeg**, and a curated set of **custom nodes**
- Creates a ready-to-launch `run_comfyui` starter in your ComfyUI folder
- On subsequent runs, detects what's already installed and asks whether to update, refresh, or leave it alone

---

## Quick Install

The release binaries are the simplest path for most users. Download the file for
your OS, put it in the folder where you want the installer state to live, and run
it directly:

- Linux: `./dasiwa-installer-linux-amd64`
- Windows: `dasiwa-installer-windows-amd64.exe`

```bash
./dasiwa-installer-linux-amd64
```

On Windows, double-click `dasiwa-installer-windows-amd64.exe`.

If you want a direct download from the latest GitHub release:

```bash
curl -L -o dasiwa-installer-linux-amd64 \
  https://github.com/darksidewalker/dasiwa-comfyui-installer/releases/latest/download/dasiwa-installer-linux-amd64
```

```powershell
$u='https://github.com/darksidewalker/dasiwa-comfyui-installer/releases/latest/download/dasiwa-installer-windows-amd64.exe'; $o='dasiwa-installer-windows-amd64.exe'; if (Get-Command curl.exe -ErrorAction SilentlyContinue) { curl.exe -fL --retry 5 --retry-delay 2 -o $o $u } else { Start-BitsTransfer -Source $u -Destination $o }
```

The app opens a local browser page and runs the native Go install engine. The
UI, default config, placeholder assets, README, and license are embedded in the
binary, so users do not need Python scripts, shell scripts, PowerShell scripts,
`config.json`, a node-list text file, or a cloned copy of this repository next
to the executable. On first run it creates a local `.dasiwa/` bootstrap directory
for `uv`, the managed Python runtime, and cache files, then keeps all ComfyUI
packages inside `ComfyUI/venv/`.

To build standalone app binaries:

```bash
go run ./cmd/build-release --version 2.0.0
```

This creates binaries in `dist/` and mirrors them to the repository root:

```text
dist/dasiwa-installer-windows-amd64.exe
dist/dasiwa-installer-linux-amd64
dasiwa-installer-windows-amd64.exe
dasiwa-installer-linux-amd64
```

Those binaries can be copied into an empty install folder and launched directly.
The embedded `config.json` is the source of defaults. Use **Extra Settings** in
the app to edit JSON overrides for the current install without creating any
extra file.

---

## Prerequisites

| Requirement | Notes |
| :---------- | :---- |
| **GPU** | NVIDIA (GTX 10-series or newer), AMD (RX 6000+), or Intel Arc |
| **Internet** | Active connection; ~20 GB free disk space for a full install with models |
| **Git** | Auto-installed on Windows if missing (fetches the latest release automatically). Required on Linux: `sudo apt install git` |
| **Admin rights** | Not required |

---

## The Web Installer

When you run the binary, it opens a local web page in your browser and collects
the full install plan there before anything is downloaded or changed. You review
the selected folder, hardware, CUDA target, components, and optional downloads
on one page, then start the install once.

**The page includes:**

1. **Install mode** — Update in place, Refresh the environment, Full reinstall, or Cancel. Nothing destructive happens without explicit confirmation.
2. **Hardware and versions** — GPU vendor, GPU name, Python version, ComfyUI ref, and CUDA target.
3. **SageAttention** — yes or no. Modern NVIDIA installs use the complete CUDA 12.8 PyTorch wheel bundle when a requested CUDA 13.x target is not installable with `torchaudio` on Windows. Embedded defaults and local overrides are never mutated.
4. **FFmpeg** — yes or no. Skipped automatically if already present.
5. **Optional downloads** — shows only what is not already on disk.
6. **Live plan** — a JSON preview of the exact install request that will be submitted to the native installer engine.

The page is single-shot by design: once you click start, the native Go installer runs unattended until completion.

---

## Hardware Support

GPU detection is automatic. If detection fails, you get a manual selection menu — a CPU-only install is never silently allowed.

| Vendor | Series | PyTorch Build |
| :----- | :----- | :------------ |
| **NVIDIA** | RTX 20 / 30 / 40 | CUDA 12.8 + Torch 2.9.1 + torchaudio 2.9.1 (configurable) |
| **NVIDIA** | RTX 50 (Blackwell) | CUDA 12.8 + Torch 2.9.1 + torchaudio 2.9.1 |
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
Queries the [wildminder.github.io](https://wildminder.github.io/AI-windows-whl/) release API at install time, finds the ABI3 wheel that matches your installed Torch version and CUDA tag, and installs it in seconds. No compiler needed for most users.

**Windows — source build (fallback)**
If no matching prebuilt wheel exists, falls back to a full CUDA source build with proper MSVC environment loading (`vcvars64.bat` is sourced and verified, `CUDA_HOME` is auto-detected, `DISTUTILS_USE_SDK=1` is set). Build parallelism is tuned to your available RAM to avoid out-of-memory linker failures.

**Linux**
Tries the precompiled SageAttention wheel path first. If no compatible wheel exists, the installer attempts a source build only when `nvcc` and a compatible `g++`/`clang++` host compiler are available. Missing or incompatible compilers skip SageAttention instead of failing the whole ComfyUI install.

**CUDA Wheel Selection**
For modern NVIDIA cards, requested CUDA 13.x targets are normalized to the official `https://download.pytorch.org/whl/cu128` wheel index with Torch 2.9.1, torchvision 0.24.1, and torchaudio 2.9.1. PyTorch publishes `cu132` Torch and torchvision wheels, but not a matching Windows Python 3.12 `torchaudio` wheel. GTX 10 / Pascal remains locked to CUDA 12.1 and Torch 2.4.1.

---

## RadialAttention

RadialAttention is a sparse long-video attention optimization. The installer clones the ComfyUI-RadialAttn custom node and its SpargeAttn dependency, then installs them into the venv.

---

## FlashAttention

FlashAttention is the official attention kernel library from Dao-AILab. It can provide significant speedups for compatible models and is Linux-only (no Windows wheels are published).

**Installation strategies (in order):**

1. **Official release wheel** — checks the [Dao-AILab/flash-attention](https://github.com/Dao-AILab/flash-attention) GitHub releases page for a prebuilt wheel matching your Torch version, CUDA tag, Python tag, and platform.
2. **Community prebuilt wheels** — queries [mjun0812/flash-attention-prebuild-wheels](https://github.com/mjun0812/flash-attention-prebuild-wheels) for a compatible wheel, scoring candidates by platform type (`manylinux` preferred) and version recency.
3. **PyPI binary-only** — attempts `uv pip install --only-binary flash-attn` with the latest PyPI version (fetched from `pypi.org`).
4. **Source build** — clones the flash-attention repo and builds from source. Only attempted when the system has at least 96 GiB of combined RAM + swap, and both `nvcc` and `g++`/`clang++` are available.

**Environment variable overrides:**

| Variable | Default | Effect |
| :------- | :------ | :----- |
| `DASIWA_FLASH_ATTN_VERSION` | latest from PyPI (fallback `2.8.3`) | Pin a specific version |
| `DASIWA_FLASH_ATTN_WHEEL_URL` | unset | Skip all resolution and install a specific wheel URL directly |
| `DASIWA_FLASH_MAX_JOBS` | `2` | Parallel build jobs for source compilation |

**Notes:**
- FlashAttention is non-fatal: installation errors are logged but do not abort the ComfyUI install.
- On Windows, the installer skips FlashAttention entirely with a log message.
- If `flash_attn` is already importable in the venv, installation is skipped.

---

## Custom Nodes

Default nodes are configured in `config.json` under the `custom_nodes` array.
Each entry is a GitHub repo URL with optional pipe flags:

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

After all nodes are installed, the **Enforcer** runs — a final `uv pip install --upgrade` pass over priority packages to ensure no node has silently downgraded a critical dependency.

**To use your own node list:** open **Extra Settings** and replace the
`custom_nodes` array, or paste a remote node-list URL in the GUI:

```json
{
    "custom_nodes": [
        "https://github.com/user/node",
        "https://github.com/user/other-node | req:requirements-no-cupy.txt"
    ]
}
```

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

## Configuration

The installer is data-driven. Build-time defaults live in the embedded
`config.json`. To override runtime settings without rebuilding, open
**Extra Settings** in the app and edit the JSON there. Supported object sections
are merged over the defaults, while arrays such as `custom_nodes` and
`optional_downloads` replace the default arrays.

```json
{
    "python": { "display_name": "3.13" },
    "comfyui": { "version": "v0.3.9" },
    "cuda": { "global": "13.2" },
    "custom_nodes": [
        "https://github.com/user/node"
    ]
}
```

Only include the keys you want to change. Everything else inherits from `config.json`.

### Full `config.json` reference

| Key | Default | Purpose |
| :-- | :------ | :------ |
| `python.display_name` | `"3.12"` | Python version passed to `uv python install` |
| `comfyui.version` | `"latest"` | `"latest"` = newest git tag; any other value = specific tag |
| `comfyui.fallback_branch` | `"master"` | Used if the targeted tag checkout fails |
| `cuda.global` | `"13.2"` | Requested CUDA wheel target for NVIDIA; CUDA 13.x is normalized to CUDA 12.8 where torchaudio is required |
| `cuda.min_cuda_for_50xx` | `"13.2"` | Requested CUDA target for Blackwell / RTX 50-series; CUDA 13.x is normalized to CUDA 12.8 where torchaudio is required |
| `custom_nodes` | array | Default custom node repos and optional pipe flags |
| `urls.custom_nodes` | unset | Optional remote node-list URL; when set, it overrides `custom_nodes` |
| `urls.ffmpeg_windows` | BtbN release URL | Portable FFmpeg zip for Windows |
| `urls.sage_repo` | thu-ml/SageAttention | SageAttention source for the fallback build |
| `urls.sparge_repo` | woct0rdho/SpargeAttn | SpargeAttention source for RadialAttention |
| `urls.radial_node_repo` | woct0rdho/ComfyUI-RadialAttn | RadialAttention custom node repo |
| `urls.flash_attn_repo` | Dao-AILab/flash-attention | FlashAttention source for the fallback build |
| `urls.msvc_build_tools` | VS download page | Opened in-browser when MSVC is missing |
| `optional_downloads` | — | Models and workflows offered in the web installer |

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

When an existing install is detected, the web installer offers four choices:

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
