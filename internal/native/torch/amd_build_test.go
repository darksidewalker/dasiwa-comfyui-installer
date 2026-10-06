package torch

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/runutil"
)

func TestAMDROCmBuildPrerequisites(t *testing.T) {
	args := amdBuildInstallArgs()
	want := []string{"pip", "install", "--only-binary", "setuptools", "--no-deps", "setuptools>=70.2.0"}
	if strings.Join(args, "\x00") != strings.Join(want, "\x00") {
		t.Fatalf("ROCm build prerequisite args = %v, want %v", args, want)
	}
}

// Exercise AMD's real source-only meta-package without downloading GPU wheels.
func TestAMDROCmBuildIntegration(t *testing.T) {
	if os.Getenv("DASIWA_UV_INTEGRATION") != "1" {
		t.Skip("set DASIWA_UV_INTEGRATION=1 to exercise the real ROCm sdist with uv")
	}
	uv, err := exec.LookPath("uv")
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	root := t.TempDir()
	env := runutil.UnsetEnv(os.Environ(), "VIRTUAL_ENV")
	env = runutil.SetEnv(env, "UV_CACHE_DIR", filepath.Join(root, "cache"))
	env = runutil.UnsetEnv(env, "UV_CONSTRAINT")
	env = runutil.UnsetEnv(env, "UV_NO_BUILD_ISOLATION_PACKAGE")
	env = runutil.UnsetEnv(env, "UV_VENV_SEED")
	env = runutil.UnsetEnv(env, "UV_VENV_CLEAR")
	if out, err := runutil.Output(ctx, "", env, uv, "venv", "--python", "3.12", filepath.Join(root, "venv")); err != nil {
		t.Fatalf("create clean venv: %v\n%s", err, out)
	}
	venv := runutil.EnvWithVenv(root, env)
	venv.Env = runutil.SetEnv(venv.Env, "PATH", filepath.Dir(uv)+string(os.PathListSeparator)+runutil.GetEnv(venv.Env, "PATH"))
	venv.Env = applyUvRuntimeEnv(venv.Env)
	args := []string{"pip", "install", "--python", venv.Python, "--no-deps", "https://stable.repo.amd.com/rocm/whl-next/rocm/rocm-10.0.0.tar.gz"}
	if out, err := runutil.Output(ctx, "", venv.Env, uv, args...); err == nil || !strings.Contains(out, "No module named 'setuptools'") {
		t.Fatalf("expected original missing-setuptools failure, got %v\n%s", err, out)
	}
	if err := prepareAMDBuild(ctx, venv.Env, func(line string) { t.Log(line) }); err != nil {
		t.Fatal(err)
	}
	if out, err := runutil.Output(ctx, "", venv.Env, uv, args...); err != nil {
		t.Fatalf("ROCm build after preparation: %v\n%s", err, out)
	} else {
		t.Log(out)
	}
	if out, err := runutil.Output(ctx, "", venv.Env, venv.Python, "-c", "import importlib.metadata; assert importlib.metadata.version('rocm') == '10.0.0'"); err != nil {
		t.Fatalf("ROCm installed metadata: %v\n%s", err, out)
	}
}
