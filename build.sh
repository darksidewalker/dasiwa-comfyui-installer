#!/usr/bin/env bash
# Build the standalone installer for Windows and Linux, then replace the
# corresponding binaries in both dist/ and the repository root.
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ $# -gt 1 ]]; then
    printf 'Usage: %s [version]\n' "$0" >&2
    exit 2
fi

VERSION="${1:-$(git describe --tags --always --dirty)}"

printf 'Building DaSiWa ComfyUI Installer version %s\n' "$VERSION"
exec go run ./cmd/build-release \
    --version "$VERSION" \
    --out "$ROOT_DIR/dist"
