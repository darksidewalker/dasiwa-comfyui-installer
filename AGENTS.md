# 🤖 AGENTS.md — DaSiWa ComfyUI Installer: Agent Operational Protocol

This document is the authoritative reference for any AI agent working on this codebase.
Read it in full before making any changes. It defines the architecture, public APIs,
invariants that must never be broken, and the correct modification target for every
category of change.

---

## 1. Project Philosophy

The installer operates on three core invariants that every agent must preserve:

1. **Zero system pollution.** Nothing is installed into the user's system Python or global
   PATH. All packages live inside `ComfyUI/venv/`. All package management goes through `uv`,
   never `pip` directly.

2. **Ask once, never again.** The pre-flight wizard (`preflight_wizard` in `setup_logic.py`)
   collects every interactive decision up front and produces a `plan` dict. After the wizard
   confirms, the installation runs unattended. Do not add `input()` calls anywhere else in
   the install flow.

3. **Config files are never mutated at runtime.** `config.json` is the committed global
   default. `config.local.json` is the user override layer. Neither file is written to during
   an install run. In-memory overrides (e.g. the CUDA downgrade for SageAttention on Windows)
   are applied to derived variables only.

---

## 2. Repository Layout

```
dasiwa-comfyui-installer/
├── install.ps1              # Windows bootstrapper (uv + Python acquisition)
├── install.sh               # Linux bootstrapper
├── install_comfyui.py       # Self-update sentinel (hash guard + execv restart)
├── setup_logic.py           # Main orchestrator — wizard → plan → execution
├── config.json              # Global defaults (COMMITTED, never written at runtime)
├── config.local.json        # User overrides (GITIGNORED, deep-merged over config.json)
├── custom_nodes.txt         # Default node list (COMMITTED)
├── custom_nodes.local.txt   # User node override (GITIGNORED, takes full precedence)
└── utils/
    ├── logger.py            # UI layer — all terminal output and prompts
    ├── hardware.py          # GPU detection and vendor classification
    ├── comfyui_clone.py     # ComfyUI git management
    ├── downloader.py        # File downloads and model migration
    ├── task_nodes.py        # Custom node cloning and dependency install
    ├── task_ffmpeg.py       # FFmpeg acquisition (portable Win / apt Linux)
    ├── task_sageattention.py# SageAttention install (wheel-first, source fallback)
    └── reporter.py          # Final installation summary
```

---

## 3. Module Catalogue & Public API

### 3.1 `utils/logger.py` — **Chronicler**

The single source of truth for all terminal output and user prompts. No module may call
`print()` or `input()` directly except `logger.py` itself.

| Method | Signature | Purpose |
| :----- | :-------- | :------ |
| `Logger.init()` | `()` | Must be called once at startup. Enables Windows VT sequences; respects `NO_COLOR`. |
| `Logger.log()` | `(text, level, bold)` | Core output. Levels: `info` `ok` `warn` `fail` `error` `done` `magenta` `debug`. |
| `Logger.error()` | `(text)` | Bold red `[-]` prefix. |
| `Logger.warn()` | `(text)` | Yellow `[!]` prefix. |
| `Logger.success()` | `(text)` | Green `[DONE]` prefix. |
| `Logger.info()` | `(text)` | Cyan `[*]` prefix. |
| `Logger.debug()` | `(text)` | Gray `[.]` prefix. Low-signal detail only. |
| `Logger.banner()` | `(title, subtitle, width)` | Double-box header for major phase breaks. |
| `Logger.section()` | `(title, width)` | Single-rule header for sub-phases. |
| `Logger.rule()` | `(width)` | Horizontal divider. |
| `Logger.kv()` | `(key, value, width)` | Aligned key/value pair for summaries. |
| `Logger.ask()` | `(question, default)` | Plain text prompt with optional default. |
| `Logger.ask_yes_no()` | `(question, default)` | Boolean Y/N prompt. Returns `bool`. |
| `Logger.ask_choice()` | `(question, options, default_index)` | Numbered menu. `options` = list of `str` or `(label, description)`. Returns chosen index `int`. |
| `Logger.spinner()` | `(message)` | Context manager. Shows animated spinner while body runs; falls back to plain log when not a TTY. |

**Agent rules:**
- Always call `Logger.init()` before any output.
- Use `Logger.ask_yes_no` / `Logger.ask_choice` for all prompts. Never raw `input()`.
- `Logger.spinner()` is for operations that produce no stdout (e.g. hashing, probing). Use
  `run_cmd(..., stream=True)` for long subprocesses where the user needs to see progress.

---

### 3.2 `setup_logic.py` — **Orchestrator**

The entry point for the actual installation. Contains the wizard, the execution engine,
and all high-level task orchestration.

#### Key functions

| Function | Purpose |
| :------- | :------ |
| `main()` | Entry point. Loads config → pre-flight → wizard → executes plan. |
| `preflight_wizard(config_data, current_dir, hw)` | Collects all user decisions. Returns the `plan` dict (see §3.2.1). |
| `_detect_existing_state(current_dir)` | Non-destructive probe of disk. Returns `state` dict describing what is already installed. |
| `_resolve_cuda_target(config_data, want_sage)` | Applies the Windows/SageAttention/CUDA-13 downgrade rule. Returns `(cuda_version_str, was_downgraded_bool)`. |
| `ensure_dependencies(target_python_version, urls)` | Pre-flight: checks Python version parity, Git presence, and minimum free disk space. |
| `install_torch(env, hw, cuda_target, config)` | Constructs and runs the correct `uv pip install torch ...` command for the detected vendor + CUDA target. |
| `task_create_launchers(comfy_path, bin_dir)` | Writes `run_comfyui.bat` / `.sh` with FFmpeg PATH injection when a portable copy is present. |
| `load_config(current_dir)` | Loads `config.json`, deep-merges `config.local.json` over it if present. Returns merged dict. |
| `resolve_nodes_source(config_data, current_dir)` | Returns `custom_nodes.local.txt` path (if exists) or the remote URL from config. |
| `run_cmd(cmd, env, stream, **kwargs)` | Subprocess wrapper. `stream=True` inherits stdio for long-running installs; otherwise captures and surfaces output only on failure. |
| `get_venv_env(comfy_path)` | Returns `(env_dict, bin_dir_str)` with `VIRTUAL_ENV` and PATH set to the ComfyUI venv. |

#### 3.2.1 The `plan` dict

`preflight_wizard` returns a single dict consumed by `main()`. Shape:

```python
{
    "install_mode":       str,   # "fresh" | "update" | "refresh" | "wipe"
    "state":              dict,  # output of _detect_existing_state()
    "target_version":     str,   # ComfyUI git ref, e.g. "master" or "v0.3.7"
    "fallback_branch":    str,   # e.g. "master"
    "want_sage":          bool,
    "want_ffmpeg":        bool,
    "cuda_target":        str,   # e.g. "12.8" or "13.0"
    "cuda_downgraded":    bool,  # True if _resolve_cuda_target downgraded for Sage
    "selected_downloads": list,  # subset of config_data["optional_downloads"]
}
```

**Agent rule:** All conditional logic in `main()` branches on `plan[...]`. Do not add new
`input()` calls in `main()` or downstream task functions — add new keys to `plan` by
extending `preflight_wizard` instead.

#### 3.2.2 Install modes

| Mode | Venv | ComfyUI folder | Models |
| :--- | :--- | :------------- | :----- |
| `fresh` | Created | Cloned | Untouched |
| `update` | Reused | `git fetch + checkout` | Untouched |
| `refresh` | Rebuilt (`--clear`) | `git fetch + checkout` | Untouched |
| `wipe` | Rebuilt | Deleted and re-cloned | **Deleted** |

`wipe` requires a double-confirmation in the wizard and must remain the only code path that
deletes the ComfyUI folder.

#### 3.2.3 CUDA downgrade rule

`_resolve_cuda_target` fires **only** when all three conditions are true:

- Platform is Windows (`IS_WIN`)
- `want_sage` is `True`
- `config_data["cuda"]["global"]` major version ≥ 13

When it fires, it offers the user a Y/N prompt to downgrade to `"12.8"` **in memory only**.
`config.json` is not touched. This is because upstream SageAttention 2.x has a known MSVC
compile failure against Torch 2.9+ (CUDA 13) due to a namespace collision in
`torch/csrc/dynamo/compiled_autograd.h`.

#### 3.2.4 `PRIORITY_PACKAGES`

```python
PRIORITY_PACKAGES = [
    "torch", "torchvision", "torchaudio",
    "numpy>=2.1.0,<=2.3.0", "pillow>=11.0.0",
    "pydantic>=2.12.5", "setuptools==81.0.0",
]
```

These are re-installed with `--upgrade` as the final step ("the Enforcer"), after all nodes
have been cloned. This ensures no node can quietly downgrade a critical package. To add a
version-locked package, append to this list in `setup_logic.py`. Do not pin packages in
node-specific `requirements.txt` files.

---

### 3.3 `utils/hardware.py` — **Hardware Scout**

| Symbol | Type | Purpose |
| :----- | :--- | :------ |
| `get_gpu_report(is_win, logger)` | function | Public entry point. Detects GPUs, applies weighted sort, falls back to `Logger.ask_choice` if vendor is `UNKNOWN`. Returns `{"vendor": str, "name": str}`. |
| `_parse_windows_gpus()` | private | PowerShell `Win32_VideoController` query. Handles int32 VRAM wrap for ≥4 GB cards. |
| `_parse_linux_gpus()` | private | `nvidia-smi` primary, `lspci` fallback. |
| `_vendor_weight(name_up)` | private | Returns sort weight: NVIDIA=3, AMD/Arc=2, Intel iGPU=1, unknown=0. Prevents an Intel HD Graphics from outranking a discrete GPU. |

**Agent rules:**
- The `get_gpu_report` fallback menu must always include an **Abort** option that calls
  `sys.exit(1)`. Never allow a CPU-only silent path.
- `_vendor_weight` must be updated if new GPU classes are added (e.g. Qualcomm Snapdragon X).
- Never remove the `UNKNOWN` re-detection loop.

---

### 3.4 `utils/comfyui_clone.py` — **Version Controller**

| Symbol | Signature | Purpose |
| :----- | :-------- | :------ |
| `sync_comfyui(comfy_path, target_version, fallback_branch)` | public | Clone if absent; otherwise fetch, auto-stash dirty tree, checkout tag or branch. |
| `_git(args, cwd, check, capture)` | private | Thin wrapper. Always sets `GIT_TERMINAL_PROMPT=0` to prevent credential hangs. |

**Agent rules:**
- Never use `shell=True` for git commands. Use the list-form `_git(["git", ...])` — this is
  what makes the code cross-platform (no bash substitution on Windows).
- The "latest tag" resolution uses two sequential `_git` calls (no shell subshell):
  `git rev-list --tags --max-count=1` → `git describe --tags <rev>`.
- Auto-stash is applied before any checkout. Do not remove it — users who ran ComfyUI once
  have generated files that would block a clean checkout.

---

### 3.5 `utils/downloader.py` — **Scavenger**

| Method | Signature | Purpose |
| :----- | :-------- | :------ |
| `Downloader.download(url, dest_folder, display_name, explicit_file, retries, delay)` | static | Atomic download (`.part` → rename). Validates Content-Length on retry. Skips existing files with matching size. |
| `Downloader.get_latest_github_file(repo_path, folder)` | static | Resolves `version: "latest"` entries via GitHub commits API. Returns `{name, download_url}` or `None`. |
| `Downloader.filter_missing(config_downloads, comfy_path)` | static | Returns only items from `optional_downloads` not yet present on disk. Called by the wizard for the download selection menu. |
| `Downloader.install_selected(selected, comfy_path)` | static | Downloads every item in `selected`. Called by `main()` after plan confirmation. |
| `Downloader.migrate_models(old_comfy_path, new_comfy_path)` | static | Moves model files and creates symlinks back. |
| `Downloader.file_exists_recursive(base_path, filename)` | static | `rglob`-based presence check. |

**Agent rules:**
- Always use the `.part` temp file pattern. Never write directly to the final destination.
  A Ctrl-C mid-download must not produce a poisoned file that the skip-check treats as valid.
- `filter_missing` + `install_selected` is the wizard-compatible split. Do not merge them
  back into a single interactive `show_cli_menu` — the wizard must finish asking before any
  download starts.

---

### 3.6 `utils/task_nodes.py` — **Integrator**

| Symbol | Signature | Purpose |
| :----- | :-------- | :------ |
| `task_custom_nodes(env, nodes_source, nodes_list_file, run_cmd_func, comfy_path)` | function | Main entry point. Returns `stats` dict: `{total, success, failed, skipped}`. |
| `fetch_node_list(source, retries, delay)` | function | Accepts a local file path or a remote URL. |
| `_parse_node_line(line)` | private | Parses `url \| flag \| req:file.txt` syntax. Returns `(url, req_filename, is_pkg)`. Tolerant of extra whitespace. |

**Pipe flag syntax** (do not break):

| Flag | Meaning |
| :--- | :------ |
| `\| sub` | Recursive `--recursive` clone (nested git repos like CosyVoice). |
| `\| pkg` | Editable install: `uv pip install -e .` with optional `-r req_file`. |
| `\| req:filename.txt` | Use a non-standard requirements filename. |

**Agent rules:**
- All git operations inject `GIT_TERMINAL_PROMPT=0` into the env. Do not remove this —
  a renamed-to-private repo would otherwise hang the installer indefinitely.
- The `comfyui-manager` skip filter is intentional — Manager installs itself via ComfyUI.
- Never call `run_cmd_func` with `shell=True`.
- Comments in `custom_nodes.txt` (lines starting with `#`) must be preserved. The parser
  already filters them; do not change this behaviour.

---

### 3.7 `utils/task_ffmpeg.py` — **Media Specialist**

| Method | Signature | Purpose |
| :----- | :-------- | :------ |
| `FFmpegInstaller.is_installed()` | static | Checks system PATH for `ffmpeg`. |
| `FFmpegInstaller.is_local_installed(comfy_root)` | static | Checks `ComfyUI/ffmpeg/bin/ffmpeg(.exe)`. |
| `FFmpegInstaller.run(comfy_path, config_urls)` | classmethod | Main entry. Skips silently if either check above passes. |
| `FFmpegInstaller.install_windows(comfy_root, download_url)` | static | Downloads portable zip, extracts, moves to `ComfyUI/ffmpeg/`, returns `bin_path`. |
| `FFmpegInstaller.install_linux()` | static | Tries package managers in order: apt-get → pacman → dnf → zypper → brew. |

**Agent rules:**
- `run()` must stay idempotent — calling it twice must not re-download.
- The portable copy always lives at `ComfyUI/ffmpeg/bin/`. `task_create_launchers` in
  `setup_logic.py` checks this exact path to inject the `PATH` line into the launcher script.
  If you rename this path, update the launcher generator to match.

---

### 3.8 `utils/task_sageattention.py` — **Build Specialist**

This is the most complex module. It has a two-stage install strategy and extensive
Windows-specific environment setup.

#### Public API

| Method | Signature | Purpose |
| :----- | :-------- | :------ |
| `SageInstaller.build_sage(venv_env, comfy_path, config_urls)` | classmethod | Main entry point. Calls `is_installed` first; if already present, exits. Tries wheel path, then source path. |
| `SageInstaller.is_installed(python_exe)` | static | Imports `sageattention` in the target venv. Returns `bool`. |
| `SageInstaller.install_system_dependencies(config_urls)` | static | Dependency menu UI. Returns `True` if safe to proceed with build. |

#### Private helpers

| Method | Purpose |
| :----- | :------ |
| `_try_prebuilt_wheel(python_exe, venv_env)` | Probes torch version, queries woct0rdho/SageAttention GitHub releases API, installs matching ABI3 or exact wheel. Returns `True` on success. |
| `_source_build(venv_env, comfy_path, config_urls, python_exe, is_win)` | Full C++/CUDA source build with MSVC env loading on Windows. |
| `_find_vcvars()` | Locates `vcvars64.bat` via `vswhere.exe`, then manual scan of VS 2017/2019/2022 editions. |
| `_find_cuda_home()` | Checks `CUDA_HOME` / `CUDA_PATH` env vars, then `where nvcc`, then scans the standard NVIDIA toolkit directory. |
| `_load_msvc_env(vcvars_path)` | Spawns `cmd /c "vcvars64.bat && set"`, captures the resulting env vars, returns merged dict. This is the **critical step** that makes MSVC work for nvcc. |
| `_estimate_max_jobs()` | Returns a RAM-aware `MAX_JOBS` string. Overridable via `DASIWA_SAGE_MAX_JOBS` env var. |
| `check_cpp_compiler()` | On Windows: checks `_find_vcvars() is not None` (not just `cl.exe` on PATH). On Linux: probes `g++` / `clang++`. |

#### Why `_load_msvc_env` exists and must not be removed

Having `cl.exe` on PATH is **not** sufficient for a CUDA extension build on Windows.
`nvcc` internally re-invokes `vcvars64.bat` to set up the full MSVC environment
(`INCLUDE`, `LIB`, `LIBPATH`, `WindowsSdkDir`, etc.). If those vars are not set,
`nvcc` fails with:

```
nvcc fatal : Could not set up the environment for Microsoft Visual Studio
```

`_load_msvc_env` solves this by running `vcvars64.bat` in a child `cmd` shell, capturing
all the resulting environment variables, and merging them into the build env before the
`uv pip install .` call.

#### Build env vars

| Variable | Value | Overridable |
| :------- | :---- | :---------- |
| `CUDA_HOME` / `CUDA_PATH` | detected by `_find_cuda_home()` | Via env before running installer |
| `DISTUTILS_USE_SDK` | `"1"` | No — required for MSVC + nvcc |
| `EXT_PARALLEL` | `"2"` | `DASIWA_SAGE_EXT_PARALLEL` |
| `NVCC_APPEND_FLAGS` | `"--threads 4"` | `DASIWA_SAGE_NVCC_THREADS` |
| `MAX_JOBS` | `_estimate_max_jobs()` | `DASIWA_SAGE_MAX_JOBS` |

**Agent rules:**
- `build_sage` must always call `is_installed` first. Never attempt a build if SageAttention
  is already importable.
- `_try_prebuilt_wheel` must always be attempted before `_source_build` on Windows.
  It is the correct default for ~90% of Windows users (no compiler needed).
- Do not increase `EXT_PARALLEL` or `MAX_JOBS` defaults. Each MSVC/nvcc linker job peaks
  at ~2.5–3 GB RAM. `MAX_JOBS=32` on a 16 GB machine will OOM during linking.
- The `_source_build` cleanup (`shutil.rmtree(".venv")`) was removed in this version.
  Do not add it back — it is unnecessary and races with Windows file locks.

---

### 3.9 `utils/reporter.py` — **Analyst**

| Method | Signature | Purpose |
| :----- | :-------- | :------ |
| `Reporter.show_summary(hw, venv_env, start_time, node_stats, sage_installed, ffmpeg_installed)` | static | Prints the final summary using `Logger.banner`, `Logger.kv`, `Logger.rule`. |

`sage_installed` and `ffmpeg_installed` accept `None` (component was not requested),
`True` (succeeded), or `False` (was requested but failed/skipped).

---

### 3.10 `install_comfyui.py` — **Sentinel**

Self-update guard that runs before `setup_logic.py`. Checks GitHub commit SHAs for both
itself and `setup_logic.py`. If a newer version exists, downloads atomically
(`<file>.new` → `replace()`) and re-execs.

**Agent rules:**
- The `_atomic_download(url, dest)` pattern (write to `.new`, then `Path.replace()`) must
  be preserved. On Windows, `Path.replace()` is the only safe overwrite of a file that
  Python may have open.
- Do not add logic here. This file's sole job is hash comparison and file swap. All
  installation logic belongs in `setup_logic.py`.
- Developer override: set `DASIWA_NO_UPDATE=1` in environment to skip the hash check
  (useful when testing local modifications that should not be overwritten).

---

### 3.11 Bootstrappers: `install.ps1` / `install.sh`

OS-level prep: download and sync the repo zip, install `uv` if missing, install the
target portable Python version, hand off to `setup_logic.py`.

**Agent rules:**
- Never add installation logic here. If a step belongs to the install flow, it goes in
  `setup_logic.py`.
- The temp extract folder (`temp_extract/` / `$TEMP_DIR`) must always be cleaned up.
  Never remove the cleanup at the end of the sync block.
- The `install.ps1` / `install.sh` files themselves are **not** overwritten during the
  zip-sync (they are excluded from the copy step). This is intentional — the user ran
  the bootstrapper, so overwriting it mid-run would be dangerous.
- `install.ps1` gates `Pause` on `$Host.Name -eq 'ConsoleHost'` to avoid hangs when
  piped. Do not remove this guard.

---

## 4. Configuration Reference

### `config.json` (global defaults — committed)

| Key path | Type | Purpose |
| :------- | :--- | :------ |
| `python.display_name` | `"3.12"` | Broad Python version passed to `uv python install`. |
| `python.full_version` | `"3.12.10"` | Exact micro-version for pinning if needed. |
| `cuda.global` | `"13.0"` | Default CUDA wheel target for NVIDIA Torch installs. |
| `cuda.min_cuda_for_50xx` | `"12.8"` | Minimum CUDA for Blackwell (RTX 50-series) + `--pre` flag. |
| `comfyui.version` | `"latest"` | `"latest"` maps to `master` branch; any other value is a git tag. |
| `comfyui.fallback_branch` | `"master"` | Used if the targeted tag checkout fails. |
| `urls.custom_nodes` | URL | Remote `custom_nodes.txt` source. Point to a Gist to share setups. |
| `urls.ffmpeg_windows` | URL | BtbN portable FFmpeg zip for Windows. |
| `urls.sage_repo` | URL | `https://github.com/thu-ml/SageAttention.git` |
| `urls.git_windows` | URL | Git for Windows silent installer. |
| `urls.msvc_build_tools` | URL | VS Build Tools download page (opened in browser). |
| `optional_downloads[]` | array | Models/workflows offered to the user in the wizard. |

### `config.local.json` (user overrides — gitignored)

Supported override sections: `python`, `comfyui`, `cuda`, `urls`. The merge is a
**shallow merge per section** — each section in the local file fully overrides its
counterpart keys in the global config.

Example — use Python 3.13 and pin a specific ComfyUI version:

```json
{
    "python": { "display_name": "3.13", "full_version": "3.13.2" },
    "comfyui": { "version": "v0.3.9" }
}
```

**Agent rule:** Never suggest editing `config.json` for user-specific values. Always
direct users to `config.local.json`.

---

## 5. Navigation & Modification Map

| Goal | File(s) to edit |
| :--- | :------------- |
| Add a new install step | `setup_logic.py` → extend `preflight_wizard` + `main()` |
| Add a wizard question | `setup_logic.py` → `preflight_wizard` only; add new key to `plan` |
| Change default packages | `PRIORITY_PACKAGES` list in `setup_logic.py` |
| Add a model/workflow option | `optional_downloads` array in `config.json` |
| Change the CUDA downgrade rule | `_resolve_cuda_target()` in `setup_logic.py` |
| Change Torch wheel URLs | `install_torch()` in `setup_logic.py` |
| Modify the node flag syntax | `_parse_node_line()` in `utils/task_nodes.py` |
| Add a new GPU vendor | `install_torch()` and `_vendor_weight()` in `utils/hardware.py` |
| Change the SageAttention wheel source | `_try_prebuilt_wheel()` in `utils/task_sageattention.py` |
| Add a new log level or UI element | `utils/logger.py` only |
| Change the launcher script | `task_create_launchers()` in `setup_logic.py` |
| Change FFmpeg source URL | `urls.ffmpeg_windows` in `config.json` |
| Change self-update branch | `REPO_BRANCH` constant in `install_comfyui.py` |
| Fix cross-platform path handling | Use `pathlib.Path` everywhere; never string concatenation |

---

## 6. Absolute Constraints — Never Violate

1. **Do not call `pip` or `pip3` directly.** Use `uv pip install` with `--python` explicitly
   set to the venv Python path.

2. **Do not add interactive prompts outside `preflight_wizard`.** Any new question goes
   into the wizard and its answer into the `plan` dict.

3. **Do not write to `config.json` at runtime.** In-memory modifications only.

4. **Do not hardcode absolute paths.** Use `Path.cwd()`, `Path(__file__).parent`, or
   paths derived from `comfy_path` / `venv_env["VIRTUAL_ENV"]`.

5. **Do not use `shell=True` for git commands.** Use list-form args and `_git()` /
   `run_cmd()` directly. `shell=True` breaks cross-platform compatibility.

6. **Do not remove the auto-stash in `sync_comfyui`.** Users who have run ComfyUI once
   have generated files (`user/`, logs, etc.) that would block a clean checkout.

7. **Do not remove `GIT_TERMINAL_PROMPT=0`.** Without it, a repo that has gone private
   will block the installer indefinitely waiting for credentials.

8. **Do not remove the `wipe` double-confirmation.** It is the only path that deletes
   user data (models, workflows).

9. **Do not merge `filter_missing` and `install_selected` back into a single interactive
   function.** The wizard must finish asking before any download begins.

10. **Do not remove `_load_msvc_env` or the `DISTUTILS_USE_SDK=1` injection.** These are
    the critical fix for Windows SageAttention builds. Removing them re-introduces the
    `nvcc fatal: could not set up the environment` failure.

11. **Do not modify `custom_nodes.txt` or `custom_nodes.local.txt` programmatically.**
    Comments (`#`) are user data and must be preserved.

12. **Do not remove the `.part` temp-file pattern in `Downloader.download`.** Direct
    writes leave corrupt files that the existence-check will treat as complete.

---

## 7. Environment Variable Reference

| Variable | Module | Effect |
| :------- | :----- | :----- |
| `NO_COLOR` | `logger.py` | Disables all ANSI escape codes. |
| `DASIWA_NO_UPDATE` | `install_comfyui.py` | Skips hash check / self-update (developer mode). |
| `DASIWA_SAGE_MAX_JOBS` | `task_sageattention.py` | Override `MAX_JOBS` for source build. |
| `DASIWA_SAGE_EXT_PARALLEL` | `task_sageattention.py` | Override `EXT_PARALLEL` for source build. |
| `DASIWA_SAGE_NVCC_THREADS` | `task_sageattention.py` | Override `NVCC_APPEND_FLAGS`. |
| `CUDA_HOME` / `CUDA_PATH` | `task_sageattention.py` | Explicit CUDA toolkit root (respected before auto-detection). |

---

## 8. Before Every Maintenance Run

```bash
# 1. Confirm which ComfyUI revision is currently checked out
git -C ComfyUI status
git -C ComfyUI log --oneline -5

# 2. Confirm the venv Python and Torch match expectations
ComfyUI/venv/bin/python -c "import torch;print(torch.__version__, torch.version.cuda)"
# Windows:
# ComfyUI\venv\Scripts\python.exe -c "import torch;print(torch.__version__, torch.version.cuda)"

# 3. Never start a change from inside the ComfyUI/ folder.
#    setup_logic.py uses os.chdir(comfy_path) during install and restores cwd at the end.
#    A stale cwd from a previous aborted run will silently resolve paths wrong.
```
