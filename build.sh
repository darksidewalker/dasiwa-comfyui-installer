#!/usr/bin/env bash
# Build the standalone Windows and Linux installers directly in the app root.
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ $# -gt 1 ]]; then
    printf 'Usage: %s [version]\n' "$0" >&2
    exit 2
fi

VERSION="${1:-$(git describe --tags --always --dirty)}"

printf 'Building DaSiWa ComfyUI Installer version %s\n' "$VERSION"
go run ./cmd/build-release \
    --version "$VERSION" \
    --out "$ROOT_DIR"

printf 'Binaries written to %s\n' "$ROOT_DIR"
