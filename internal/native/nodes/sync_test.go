package nodes

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/runutil"
)

// The test executable doubles as fake git/uv; no external tools or downloads
// are involved in this deterministic failure-path regression test.
func TestMain(m *testing.M) {
	if os.Getenv("DASIWA_NODE_TEST_HELPER") == "1" {
		if filepath.Base(os.Args[0]) == "uv" && strings.Contains(strings.Join(os.Args, " "), "FailNode") {
			fmt.Fprintln(os.Stderr, "Failed to build `example-native-package==1.0`\n'nmake' '-?' failed with: no such file or directory\nCMake Error: CMAKE_CXX_COMPILER not set, after EnableLanguage")
			os.Exit(1)
		}
		os.Exit(0)
	}
	os.Exit(m.Run())
}

func TestSyncRetainsDependencyFailureAndContinues(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("test helper uses Unix executable symlinks")
	}
	root := t.TempDir()
	bin := filepath.Join(root, "tools")
	if err := os.MkdirAll(bin, 0755); err != nil {
		t.Fatal(err)
	}
	exe, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	for _, tool := range []string{"git", "uv"} {
		if err := os.Symlink(exe, filepath.Join(bin, tool)); err != nil {
			t.Fatal(err)
		}
	}
	for _, name := range []string{"FailNode", "GoodNode"} {
		node := filepath.Join(root, "custom_nodes", name)
		if err := os.MkdirAll(node, 0755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(node, "requirements.txt"), []byte("numpy\n"), 0600); err != nil {
			t.Fatal(err)
		}
	}
	env := runutil.SetEnv(os.Environ(), "PATH", bin)
	env = runutil.SetEnv(env, "DASIWA_NODE_TEST_HELPER", "1")
	env = runutil.SetEnv(env, "VIRTUAL_ENV", filepath.Join(root, "venv"))
	stats := Sync(context.Background(), env, []string{"https://example.invalid/FailNode", "https://example.invalid/GoodNode"}, root, nil)
	if stats.Success != 1 || len(stats.Failed) != 1 || len(stats.FailureDetails) != 1 {
		t.Fatalf("unexpected stats: %+v", stats)
	}
	for _, want := range []string{"FailNode", "example-native-package", "Missing build tool: nmake", "Missing C++ compiler"} {
		if !strings.Contains(stats.FailureDetails[0], want) {
			t.Fatalf("%s missing from %s", want, stats.FailureDetails[0])
		}
	}
}
