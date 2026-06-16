package comfypath

import (
	"os"
	"path/filepath"
	"testing"
)

func TestResolveDefaultsToComfyUIUnderRoot(t *testing.T) {
	root := t.TempDir()
	got := Resolve(root, "")
	want := filepath.Join(root, "ComfyUI")
	if got != want {
		t.Fatalf("Resolve empty = %q, want %q", got, want)
	}
}

func TestResolveExistingParentAppendsComfyUI(t *testing.T) {
	root := t.TempDir()
	parent := filepath.Join(root, "install-here")
	if err := os.Mkdir(parent, 0o755); err != nil {
		t.Fatal(err)
	}
	got := Resolve(root, parent)
	want := filepath.Join(parent, "ComfyUI")
	if got != want {
		t.Fatalf("Resolve parent = %q, want %q", got, want)
	}
}

func TestResolveExistingComfyUIRootStaysDirect(t *testing.T) {
	root := t.TempDir()
	comfy := filepath.Join(root, "Somewhere")
	if err := os.Mkdir(comfy, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(comfy, "main.py"), []byte(""), 0o644); err != nil {
		t.Fatal(err)
	}
	got := Resolve(root, comfy)
	if got != comfy {
		t.Fatalf("Resolve ComfyUI root = %q, want %q", got, comfy)
	}
}

func TestResolveComfyUIBasenameStaysDirect(t *testing.T) {
	root := t.TempDir()
	got := Resolve(root, "ComfyUI")
	want := filepath.Join(root, "ComfyUI")
	if got != want {
		t.Fatalf("Resolve ComfyUI name = %q, want %q", got, want)
	}
}
