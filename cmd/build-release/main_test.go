package main

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestBuildUsesOnlySelectedOutputDirectory(t *testing.T) {
	root := t.TempDir()
	app := filepath.Join(root, "cmd", "installer-app")
	if err := os.MkdirAll(app, 0o755); err != nil {
		t.Fatal(err)
	}
	for path, content := range map[string]string{
		filepath.Join(root, "go.mod"): "module buildtest\n\ngo 1.22\n",
		filepath.Join(app, "main.go"): "package main\nvar version string\nfunc main() {}\n",
	} {
		if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	out := t.TempDir()
	name := "installer"
	if runtime.GOOS == "windows" {
		name += ".exe"
	}
	if err := build(target{GOOS: runtime.GOOS, GOARCH: runtime.GOARCH, Name: name}, "test", root, out); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(out, name)); err != nil {
		t.Fatalf("missing requested output: %v", err)
	}
	if _, err := os.Stat(filepath.Join(root, name)); !os.IsNotExist(err) {
		t.Fatalf("unexpected root mirror: %v", err)
	}
	if _, err := os.Stat(filepath.Join(root, "dist")); !os.IsNotExist(err) {
		t.Fatalf("unexpected dist directory: %v", err)
	}
}
