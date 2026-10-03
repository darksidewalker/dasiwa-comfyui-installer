package install

import (
	"archive/zip"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/bootstrap"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/runutil"
)

func putTestFile(t *testing.T, path, content string, mode os.FileMode) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), mode); err != nil {
		t.Fatal(err)
	}
}

func TestPythonABI(t *testing.T) {
	for _, version := range []string{"3.12", "3.12.14", "3.11.9"} {
		if _, err := pythonABI(version); err != nil {
			t.Fatal(err)
		}
	}
	for _, version := range []string{"", "latest", "3.12t", "3.12.1.2", "2.7", "pypy3.12"} {
		if _, err := pythonABI(version); err == nil {
			t.Fatalf("accepted %q", version)
		}
	}
}

func TestUpdateMissingConfigDoesNotClearPackages(t *testing.T) {
	root := t.TempDir()
	marker := filepath.Join(root, "venv", "lib", "package.txt")
	putTestFile(t, marker, "preserve", 0644)
	called := false
	_, _, err := prepareVenv(context.Background(), root, root, "update", "3.12", nil,
		func(string, string, string, func(string)) (*bootstrap.PythonRunner, error) {
			called = true
			return nil, fmt.Errorf("unexpected")
		})
	if err == nil || called {
		t.Fatalf("err=%v prepare called=%v", err, called)
	}
	if data, err := os.ReadFile(marker); err != nil || string(data) != "preserve" {
		t.Fatalf("package changed: %s %v", data, err)
	}
}

func TestUpdateABIAndRollback(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell fault injection is POSIX-only")
	}
	for _, failure := range []string{"abi-mismatch", "uv-failure", "validation-failure"} {
		t.Run(failure, func(t *testing.T) {
			root := t.TempDir()
			v := runutil.EnvWithVenv(root, nil)
			cfg := "home = /missing/old/python\nversion = 3.11.9\ninclude-system-site-packages = false\n"
			putTestFile(t, filepath.Join(v.Root, "pyvenv.cfg"), cfg, 0644)
			putTestFile(t, filepath.Join(v.Root, "lib", "package.txt"), "preserve", 0644)
			if err := os.MkdirAll(v.BinDir, 0755); err != nil {
				t.Fatal(err)
			}
			if err := os.Symlink("/missing/old/python", v.Python); err != nil {
				t.Fatal(err)
			}
			putTestFile(t, filepath.Join(v.BinDir, "console-script"), "original script", 0755)
			tools := filepath.Join(root, "tools")
			version := "3.11"
			if failure == "abi-mismatch" {
				version = "3.12"
			}
			python := filepath.Join(tools, "python")
			putTestFile(t, python, "#!/bin/sh\nprintf '"+version+"\\n'\n", 0755)
			exitCode := "1"
			if failure == "validation-failure" {
				exitCode = "0"
			}
			putTestFile(t, filepath.Join(tools, "uv"), "#!/bin/sh\necho damaged > \"$2/pyvenv.cfg\"\nrm -f \"$2/bin/python\"\necho damaged > \"$2/bin/console-script\"\nexit "+exitCode+"\n", 0755)
			_, _, err := prepareVenv(context.Background(), root, root, "update", "3.12", nil,
				func(toolRoot, comfy, selected string, logf func(string)) (*bootstrap.PythonRunner, error) {
					if selected != "3.11" {
						t.Fatalf("selected %s, want existing ABI", selected)
					}
					return &bootstrap.PythonRunner{Python: python, Env: runutil.SetEnv(os.Environ(), "PATH", tools+string(os.PathListSeparator)+os.Getenv("PATH"))}, nil
				})
			if err == nil {
				t.Fatal("expected failure")
			}
			if data, _ := os.ReadFile(filepath.Join(v.Root, "pyvenv.cfg")); string(data) != cfg {
				t.Fatalf("config not restored: %s", data)
			}
			if link, err := os.Readlink(v.Python); err != nil || link != "/missing/old/python" {
				t.Fatalf("link not restored: %s %v", link, err)
			}
			if data, _ := os.ReadFile(filepath.Join(v.BinDir, "console-script")); string(data) != "original script" {
				t.Fatal("script not restored")
			}
			if data, _ := os.ReadFile(filepath.Join(v.Root, "lib", "package.txt")); string(data) != "preserve" {
				t.Fatal("package lost")
			}
			backups, err := filepath.Glob(filepath.Join(root, ".dasiwa-venv-backup-*"))
			if err != nil || len(backups) != 0 {
				t.Fatalf("backup cleanup: %v %v", backups, err)
			}
		})
	}
}

func TestMigrationRemovesInheritedUVDefaults(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell fixture is POSIX-only")
	}
	for _, value := range []string{"1", "false"} {
		t.Run(value, func(t *testing.T) {
			root := t.TempDir()
			v := runutil.EnvWithVenv(root, nil)
			putTestFile(t, filepath.Join(v.Root, "pyvenv.cfg"), "version = 3.12.12\n", 0644)
			putTestFile(t, v.Python, "#!/bin/sh\nprintf '3.12\\n'\n", 0755)
			tools := filepath.Join(root, "tools")
			putTestFile(t, filepath.Join(tools, "uv"), "#!/bin/sh\n[ -z \"${UV_VENV_CLEAR+x}\" ] || exit 20\n[ -z \"${UV_VENV_SEED+x}\" ] || exit 21\nprintf checked > \"$2/checked\"\n", 0755)
			t.Setenv("UV_VENV_CLEAR", value)
			t.Setenv("UV_VENV_SEED", value)
			_, _, err := prepareVenv(context.Background(), root, root, "update", "3.12", nil,
				func(string, string, string, func(string)) (*bootstrap.PythonRunner, error) {
					return &bootstrap.PythonRunner{Python: v.Python, Env: runutil.SetEnv(os.Environ(), "PATH", tools)}, nil
				})
			if err != nil {
				t.Fatal(err)
			}
			if data, err := os.ReadFile(filepath.Join(v.Root, "checked")); err != nil || string(data) != "checked" {
				t.Fatalf("uv was not called with sanitized environment: %q %v", data, err)
			}
			if os.Getenv("UV_VENV_CLEAR") != value || os.Getenv("UV_VENV_SEED") != value {
				t.Fatal("parent environment changed")
			}
		})
	}
}

func TestRunSyncBeforeRuntimeAndAfterWipe(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell fault injection is POSIX-only")
	}
	for _, mode := range []string{"fresh", "refresh", "wipe"} {
		t.Run(mode, func(t *testing.T) {
			root := t.TempDir()
			comfy := filepath.Join(root, "ComfyUI")
			if mode == "wipe" {
				putTestFile(t, filepath.Join(comfy, ".dasiwa", "python", "old"), "old", 0644)
			}
			tools := filepath.Join(root, "tools")
			putTestFile(t, filepath.Join(tools, "git"), "#!/bin/sh\n[ \"$1\" = clone ] || exit 20\n[ ! -e \"$3\" ] || exit 21\nprintf 'sync-blocked-after-empty-target-check\\n' >&2\nexit 22\n", 0755)
			t.Setenv("PATH", tools+string(os.PathListSeparator)+os.Getenv("PATH"))
			var logs []string
			err := Run(context.Background(), root, Choices{InstallMode: mode, ConfirmWipe: true, ComfyPath: comfy}, func(s string) { logs = append(logs, s) })
			if err == nil || !strings.Contains(strings.Join(logs, "\n"), "sync-blocked-after-empty-target-check") {
				t.Fatalf("sync ordering: %v %v", err, logs)
			}
			if _, err := os.Stat(filepath.Join(root, ".dasiwa", "python")); !os.IsNotExist(err) {
				t.Fatal("installer-local Python created")
			}
			if _, err := os.Stat(filepath.Join(comfy, ".dasiwa", "python")); !os.IsNotExist(err) {
				t.Fatal("runtime created before Sync")
			}
		})
	}
}

// Opt-in: DASIWA_UV_INTEGRATION=1 enables network Python downloads.
// All runtimes, wheels and venvs are isolated in t.TempDir (TMPDIR).
func TestManagedRuntimeIntegration(t *testing.T) {
	if os.Getenv("DASIWA_UV_INTEGRATION") != "1" {
		t.Skip("set DASIWA_UV_INTEGRATION=1 for isolated real-uv test")
	}
	uv, err := exec.LookPath("uv")
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	logf := func(s string) { t.Log(s) }
	for _, dangling := range []bool{false, true} {
		t.Run(fmt.Sprint("dangling=", dangling), func(t *testing.T) {
			root := t.TempDir()
			old := filepath.Join(root, "old-installer")
			tools := filepath.Join(root, "new-installer")
			comfy := filepath.Join(root, "ComfyUI")
			if err := os.MkdirAll(comfy, 0755); err != nil {
				t.Fatal(err)
			}
			runner, err := bootstrap.PreparePython(old, "3.12", logf)
			if err != nil {
				t.Fatal(err)
			}
			v := runutil.EnvWithVenv(comfy, runner.Env)
			if err := runutil.Command(ctx, logf, root, runner.Env, uv, "venv", v.Root, "--python", runner.Python); err != nil {
				t.Fatal(err)
			}
			wheel := filepath.Join(root, "runtime_marker-1.0-py3-none-any.whl")
			writeMarkerWheel(t, wheel)
			if err := runutil.Command(ctx, logf, root, v.Env, uv, "pip", "install", "--python", v.Python, "--no-index", wheel); err != nil {
				t.Fatal(err)
			}
			if dangling {
				if err := os.RemoveAll(old); err != nil {
					t.Fatal(err)
				}
			}
			t.Setenv("UV_VENV_CLEAR", "1")
			t.Setenv("UV_VENV_SEED", "1")
			v, abi, err := prepareVenv(ctx, tools, comfy, "update", "3.13", logf, bootstrap.PreparePythonAt)
			if err != nil {
				t.Fatal(err)
			}
			if abi != "3.12" {
				t.Fatalf("changed package ABI: %s", abi)
			}
			if err := os.RemoveAll(old); err != nil {
				t.Fatal(err)
			}
			if err := os.RemoveAll(tools); err != nil {
				t.Fatal(err)
			}
			assertMarkerRuntime(t, ctx, v, comfy)
			cfg, err := os.ReadFile(filepath.Join(v.Root, "pyvenv.cfg"))
			if err != nil {
				t.Fatal(err)
			}
			v, _, err = prepareVenv(ctx, tools, comfy, "update", "3.13", logf, bootstrap.PreparePythonAt)
			if err != nil {
				t.Fatal(err)
			}
			again, err := os.ReadFile(filepath.Join(v.Root, "pyvenv.cfg"))
			if err != nil || string(cfg) != string(again) {
				t.Fatalf("not idempotent: %s vs %s (%v)", cfg, again, err)
			}
			assertMarkerRuntime(t, ctx, v, comfy)
		})
	}
	t.Run("fresh", func(t *testing.T) {
		root := t.TempDir()
		tools, comfy := filepath.Join(root, "installer"), filepath.Join(root, "ComfyUI")
		if err := os.MkdirAll(comfy, 0755); err != nil {
			t.Fatal(err)
		}
		v, _, err := prepareVenv(ctx, tools, comfy, "fresh", "3.12", logf, bootstrap.PreparePythonAt)
		if err != nil {
			t.Fatal(err)
		}
		if err := os.RemoveAll(tools); err != nil {
			t.Fatal(err)
		}
		out, err := runutil.Output(ctx, "", nil, v.Python, "-c", "import ssl, encodings, pathlib, sys; assert pathlib.Path(sys.base_prefix).is_relative_to(pathlib.Path(sys.argv[1])); print('standalone')", filepath.Join(comfy, ".dasiwa", "python"))
		if err != nil || strings.TrimSpace(out) != "standalone" {
			t.Fatalf("%s %v", out, err)
		}
	})
}

func assertMarkerRuntime(t *testing.T, ctx context.Context, v runutil.Venv, comfy string) {
	t.Helper()
	out, err := runutil.Output(ctx, "", nil, v.Python, "-c", "import ssl, encodings, pathlib, sys, runtime_marker, importlib.metadata; assert runtime_marker.VALUE == 42; assert importlib.metadata.version('runtime-marker') == '1.0'; assert pathlib.Path(sys.base_prefix).is_relative_to(pathlib.Path(sys.argv[1])); print('preserved')", filepath.Join(comfy, ".dasiwa", "python"))
	if err != nil || strings.TrimSpace(out) != "preserved" {
		t.Fatalf("runtime/package check: %s %v", out, err)
	}
	cfg, err := readVenvConfig(filepath.Join(v.Root, "pyvenv.cfg"))
	if err != nil || cfg["relocatable"] != "true" {
		t.Fatalf("venv not relocatable: %v %v", cfg, err)
	}
	script := filepath.Join(v.BinDir, "runtime-marker")
	if runtime.GOOS == "windows" {
		script += ".exe"
	}
	out, err = runutil.Output(ctx, "", nil, script)
	if err != nil || strings.TrimSpace(out) != "42" {
		t.Fatalf("console script not preserved: %s %v", out, err)
	}
}

func writeMarkerWheel(t *testing.T, path string) {
	t.Helper()
	f, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	w := zip.NewWriter(f)
	for name, content := range map[string]string{
		"runtime_marker.py":                             "VALUE = 42\ndef main():\n    print(VALUE)\n",
		"runtime_marker-1.0.dist-info/entry_points.txt": "[console_scripts]\nruntime-marker = runtime_marker:main\n",
		"runtime_marker-1.0.dist-info/METADATA":         "Metadata-Version: 2.1\nName: runtime-marker\nVersion: 1.0\n",
		"runtime_marker-1.0.dist-info/WHEEL":            "Wheel-Version: 1.0\nGenerator: dasiwa-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
		"runtime_marker-1.0.dist-info/RECORD":           "runtime_marker.py,,\nruntime_marker-1.0.dist-info/METADATA,,\nruntime_marker-1.0.dist-info/WHEEL,,\nruntime_marker-1.0.dist-info/entry_points.txt,,\nruntime_marker-1.0.dist-info/RECORD,,\n",
	} {
		entry, err := w.Create(name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := entry.Write([]byte(content)); err != nil {
			t.Fatal(err)
		}
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}
}
