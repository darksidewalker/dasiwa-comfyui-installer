package installer

import "embed"

// Files contains non-Python runtime assets for the standalone GUI installer.
// Native Go engine reads defaults/docs/assets directly from this bundle.
//
//go:embed config.json README.md LICENSE
//go:embed assets/*
var Files embed.FS
