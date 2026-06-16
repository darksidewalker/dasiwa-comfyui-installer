package pathbrowser

import (
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
)

type Entry struct {
	Name  string `json:"name"`
	Path  string `json:"path"`
	IsDir bool   `json:"isDir"`
}

type ListResponse struct {
	Path    string  `json:"path"`
	Parent  string  `json:"parent"`
	Entries []Entry `json:"entries"`
	Roots   []Entry `json:"roots"`
}

func List(pathValue, mode string) ListResponse {
	if mode != "directory" && mode != "file" && mode != "model" {
		mode = "directory"
	}
	pathValue = strings.TrimSpace(pathValue)
	if pathValue == "" {
		pathValue = defaultBrowsePath()
	}
	pathValue = filepath.Clean(pathValue)
	if info, err := os.Stat(pathValue); err == nil && !info.IsDir() {
		pathValue = filepath.Dir(pathValue)
	}
	if info, err := os.Stat(pathValue); err != nil || !info.IsDir() {
		pathValue = defaultBrowsePath()
	}
	pathValue, _ = filepath.Abs(pathValue)
	resp := ListResponse{
		Path:   pathValue,
		Parent: parentPath(pathValue),
		Roots:  roots(),
	}
	entries, err := os.ReadDir(pathValue)
	if err != nil {
		return resp
	}
	for _, entry := range entries {
		name := entry.Name()
		full := filepath.Join(pathValue, name)
		isDir := entry.IsDir()
		if !isDir && mode == "directory" {
			continue
		}
		if !isDir && mode == "model" && !isModelFile(name) {
			continue
		}
		resp.Entries = append(resp.Entries, Entry{Name: name, Path: full, IsDir: isDir})
	}
	sort.SliceStable(resp.Entries, func(i, j int) bool {
		left, right := resp.Entries[i], resp.Entries[j]
		if left.IsDir != right.IsDir {
			return left.IsDir
		}
		return strings.ToLower(left.Name) < strings.ToLower(right.Name)
	})
	return resp
}

func defaultBrowsePath() string {
	if home, err := os.UserHomeDir(); err == nil && home != "" {
		return home
	}
	if cwd, err := os.Getwd(); err == nil && cwd != "" {
		return cwd
	}
	return string(filepath.Separator)
}

func parentPath(pathValue string) string {
	parent := filepath.Dir(pathValue)
	if parent == pathValue || parent == "." {
		return ""
	}
	return parent
}

func roots() []Entry {
	if runtime.GOOS == "windows" {
		var out []Entry
		for letter := 'A'; letter <= 'Z'; letter++ {
			root := string(letter) + ":\\"
			if _, err := os.Stat(root); err == nil {
				out = append(out, Entry{Name: root, Path: root, IsDir: true})
			}
		}
		return out
	}
	out := []Entry{{Name: "/", Path: "/", IsDir: true}}
	if home, err := os.UserHomeDir(); err == nil && home != "" {
		out = append(out, Entry{Name: "Home", Path: home, IsDir: true})
	}
	if cwd, err := os.Getwd(); err == nil && cwd != "" {
		out = append(out, Entry{Name: "Current", Path: cwd, IsDir: true})
	}
	return out
}

func isModelFile(name string) bool {
	ext := strings.ToLower(filepath.Ext(name))
	switch ext {
	case ".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf":
		return true
	default:
		return false
	}
}
