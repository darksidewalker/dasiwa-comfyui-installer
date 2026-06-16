package bootstrap

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestBootstrapEnvUsesManagedLocalPython(t *testing.T) {
	root := t.TempDir()
	binDir := filepath.Join(root, ".dasiwa", "bin")
	env := bootstrapEnv(root, binDir)

	if got := envValue(env, "UV_PYTHON_INSTALL_DIR"); got != filepath.Join(root, ".dasiwa", "python") {
		t.Fatalf("UV_PYTHON_INSTALL_DIR = %q, want local managed Python dir", got)
	}
	if got := envValue(env, "UV_MANAGED_PYTHON"); got != "1" {
		t.Fatalf("UV_MANAGED_PYTHON = %q, want 1", got)
	}
	if got := envValue(env, "PATH"); !strings.HasPrefix(got, binDir+string(filepath.ListSeparator)) {
		t.Fatalf("PATH = %q, want local bin first", got)
	}
}

func envValue(env []string, key string) string {
	prefix := key + "="
	for _, item := range env {
		if strings.HasPrefix(item, prefix) {
			return strings.TrimPrefix(item, prefix)
		}
	}
	return ""
}
