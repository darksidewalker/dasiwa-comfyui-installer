package runutil

import (
	"context"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestCommandResolvesExecutableFromEnvPath(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell script fixture is Unix-only")
	}
	dir := t.TempDir()
	exe := filepath.Join(dir, "fake-uv")
	if err := os.WriteFile(exe, []byte("#!/bin/sh\necho ok\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	env := SetEnv(os.Environ(), "PATH", dir)
	var lines []string
	if err := Command(context.Background(), func(line string) {
		lines = append(lines, line)
	}, "", env, "fake-uv"); err != nil {
		t.Fatal(err)
	}
	if strings.Join(lines, "\n") != "ok" {
		t.Fatalf("output = %q, want ok", strings.Join(lines, "\n"))
	}
}

func TestUnsetEnvRemovesAllOccurrencesAndPreservesInput(t *testing.T) {
	env := []string{"UV_VENV_CLEAR=1", "KEEP=value", "UV_VENV_CLEAR=false", "UV_VENV_SEED=1", "uv_venv_clear=1"}
	got := UnsetEnv(UnsetEnv(env, "UV_VENV_CLEAR"), "UV_VENV_SEED")
	want := "KEEP=value\nuv_venv_clear=1"
	if runtime.GOOS == "windows" {
		want = "KEEP=value"
	}
	if strings.Join(got, "\n") != want {
		t.Fatalf("unexpected environment: %v", got)
	}
	if env[0] != "UV_VENV_CLEAR=1" || len(env) != 5 {
		t.Fatal("parent environment changed")
	}
}

func TestSetAndGetEnvAreCaseInsensitiveOnWindows(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows env keys are case-insensitive")
	}
	env := SetEnv([]string{"Path=C:\\Windows"}, "PATH", "C:\\DaSiWa")
	if len(env) != 1 {
		t.Fatalf("env length = %d, want 1", len(env))
	}
	if got := GetEnv(env, "PATH"); got != "C:\\DaSiWa" {
		t.Fatalf("PATH = %q, want C:\\DaSiWa", got)
	}
}
