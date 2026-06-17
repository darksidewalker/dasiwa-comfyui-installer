# AGENTS.md - DaSiWa ComfyUI Installer

This project is now a standalone Go installer. The release artifact is a single
binary per OS:

- `dist/dasiwa-installer-windows-amd64.exe`
- `dist/dasiwa-installer-linux-amd64`

Users should not need Python scripts, shell scripts, PowerShell scripts, or a
cloned repository next to the executable.

## Core Invariants

1. **Standalone binary UX.** The web UI, default config, default node list,
   placeholder assets, README, and license are embedded with Go `embed`.
2. **Zero system pollution.** Runtime tools are installed under `.dasiwa/`.
   ComfyUI packages live inside `ComfyUI/venv/`. Package operations go through
   `uv`, never direct `pip`.
3. **Ask once, run unattended.** The web UI collects choices up front and writes
   a temporary `.dasiwa-app-plan.json`. After start, the install flow should not
   prompt interactively.
4. **Config files are not mutated at runtime.** `config.json` is the embedded
   default. The app's Extra Settings modal sends in-memory JSON overrides.

## Important Files

- `bundle.go` embeds `config.json`, docs, and assets.
- `cmd/installer-app/main.go` serves the local browser UI and starts installs.
- `cmd/build-release/main.go` builds release binaries.
- `internal/uistatic/static/` contains the embedded HTML/CSS/JS UI.
- `internal/native/install/` orchestrates the native Go install flow.
- `internal/native/*` implements ComfyUI sync, downloads, nodes, Torch,
  FFmpeg, SageAttention, RadialAttention, launchers, and build helpers.
- `internal/bootstrap/` downloads local `uv` and ensures the managed Python
  runtime under `.dasiwa/`.
- `internal/appconfig/` loads embedded defaults and merges in-memory app
  overrides from `config_overrides`.

## Modification Map

- UI layout or behavior: `internal/uistatic/static/`
- Release binary behavior: `cmd/installer-app/main.go`
- Build outputs: `cmd/build-release/main.go`
- Install step ordering: `internal/native/install/install.go`
- Config defaults, custom node defaults, or optional downloads: `config.json`
- Torch selection: `internal/native/torch/`
- CUDA host compiler handling: `internal/native/cudahost/`
- SageAttention: `internal/native/sage/`
- RadialAttention: `internal/native/radial/`
- FFmpeg: `internal/native/ffmpeg/`
- Launchers: `internal/native/launcher/`

## Absolute Constraints

- Do not reintroduce `.py`, `.sh`, or `.ps1` installer scripts.
- Do not add a Python-engine fallback or repo-sync path that requires source
  files beside the binary.
- Do not call `pip` or `pip3` directly. Use `uv pip ... --python <venv python>`.
- Do not write to `config.json` at runtime.
- Do not remove wipe confirmation logic.
- Do not use `shell=True` equivalents for Git or subprocess calls; pass argv
  lists to `exec.Command`.
- Preserve `GIT_TERMINAL_PROMPT=0` for Git operations.

## Verification

Use writable Go caches in sandboxed environments:

```bash
env GOCACHE=/tmp/dasiwa-go-cache GOMODCACHE=/tmp/dasiwa-go-modcache go test ./...
env GOCACHE=/tmp/dasiwa-go-cache GOMODCACHE=/tmp/dasiwa-go-modcache go build -o /tmp/dasiwa-installer-smoke ./cmd/installer-app
env GOCACHE=/tmp/dasiwa-go-cache GOMODCACHE=/tmp/dasiwa-go-modcache go run ./cmd/build-release --version smoke --current --out /tmp/dasiwa-release-smoke --check-cuda-migration=
```

For standalone smoke testing, run the built binary with an empty `--root` and
confirm `/api/config` returns embedded defaults.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, invoke the `skill` tool with `skill: "graphify"` before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
