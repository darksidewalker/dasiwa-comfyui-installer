package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

func TestCopyFileReplacesRunningLinuxExecutable(t *testing.T) {
	if testing.Short() {
		t.Skip("requires a Linux executable")
	}

	dir := t.TempDir()
	dst := filepath.Join(dir, "running")
	data, err := os.ReadFile("/bin/sleep")
	if err != nil {
		t.Fatalf("read /bin/sleep: %v", err)
	}
	if err := os.WriteFile(dst, data, 0o755); err != nil {
		t.Fatalf("write running executable: %v", err)
	}
	cmd := exec.Command(dst, "10")
	if err := cmd.Start(); err != nil {
		t.Fatalf("start executable: %v", err)
	}
	t.Cleanup(func() {
		_ = cmd.Process.Kill()
		_ = cmd.Wait()
	})
	time.Sleep(50 * time.Millisecond)

	src := filepath.Join(dir, "replacement")
	if err := os.WriteFile(src, []byte("replacement"), 0o755); err != nil {
		t.Fatalf("write replacement: %v", err)
	}
	if err := copyFile(src, dst); err != nil {
		t.Fatalf("copyFile() replacing running executable: %v", err)
	}
	got, err := os.ReadFile(dst)
	if err != nil {
		t.Fatalf("read replacement: %v", err)
	}
	if string(got) != "replacement" {
		t.Fatalf("replacement content = %q, want %q", got, "replacement")
	}
}
