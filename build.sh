#!/usr/bin/env bash
# Build the standalone installer for Windows and Linux.
# Primary output is dist/, and each binary is also mirrored to the app root.
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ $# -gt 1 ]]; then
    printf 'Usage: %s [version]\n' "$0" >&2
    exit 2
fi

VERSION="${1:-$(git describe --tags --always --dirty)}"

# Names match the default targets in cmd/build-release/main.go.
TARGETS=(
    "dasiwa-installer-windows-amd64.exe"
    "dasiwa-installer-linux-amd64"
)

DIST_DIR="$ROOT_DIR/dist"

printf 'Building DaSiWa ComfyUI Installer version %s\n' "$VERSION"
go run ./cmd/build-release \
    --version "$VERSION" \
    --out "$DIST_DIR"

# build-release already mirrors dist/ -> root; do it explicitly here as well so
# the app root always holds up-to-date binaries even if that step is removed.
for name in "${TARGETS[@]}"; do
    src="$DIST_DIR/$name"
    dst="$ROOT_DIR/$name"
    if [[ -f "$src" ]]; then
        printf 'Building %s -> %s\n' "$name" "$dst"
        cp -f "$src" "$dst"
    else
        printf 'warning: expected %s was not produced\n' "$src" >&2
    fi
done

printf 'Binaries written to %s and %s\n' "$DIST_DIR" "$ROOT_DIR"
