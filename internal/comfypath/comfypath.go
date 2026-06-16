package comfypath

import (
	"os"
	"path/filepath"
	"strings"
)

func Resolve(root, selected string) string {
	selected = strings.TrimSpace(selected)
	if selected == "" {
		return filepath.Join(root, "ComfyUI")
	}
	candidate := filepath.Clean(selected)
	if !filepath.IsAbs(candidate) {
		candidate = filepath.Join(root, candidate)
	}
	if isComfyRoot(candidate) || strings.EqualFold(filepath.Base(candidate), "ComfyUI") {
		return candidate
	}
	nested := filepath.Join(candidate, "ComfyUI")
	if isComfyRoot(nested) || dirExists(nested) || dirExists(candidate) {
		return nested
	}
	return candidate
}

func isComfyRoot(path string) bool {
	return fileExists(filepath.Join(path, "main.py"))
}

func dirExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.IsDir()
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}
