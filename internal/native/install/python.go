package install

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/bootstrap"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/runutil"
)

type preparePythonFunc func(string, string, string, func(string)) (*bootstrap.PythonRunner, error)

var pythonVersionPattern = regexp.MustCompile(`^(3)\.([0-9]+)(?:\.[0-9]+)?$`)

func pythonABI(version string) (string, error) {
	parts := pythonVersionPattern.FindStringSubmatch(strings.TrimSpace(version))
	if parts == nil {
		return "", fmt.Errorf("unsupported Python version %q; refusing to risk existing packages", version)
	}
	return parts[1] + "." + parts[2], nil
}

func readVenvConfig(path string) (map[string]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	cfg := map[string]string{}
	for _, line := range strings.Split(string(data), "\n") {
		if key, value, ok := strings.Cut(line, "="); ok {
			cfg[strings.TrimSpace(key)] = strings.TrimSpace(value)
		}
	}
	return cfg, nil
}

// prepareVenv is called after wipe and checkout. An update is never treated as
// fresh merely because its interpreter is a dangling symlink: pyvenv.cfg owns
// the package ABI, even if the original installer/runtime no longer exists.
func prepareVenv(ctx context.Context, toolRoot, comfyPath, mode, configured string, logf runutil.LogFunc, prepare preparePythonFunc) (runutil.Venv, string, error) {
	var empty runutil.Venv
	comfyPath, err := filepath.Abs(comfyPath)
	if err != nil {
		return empty, "", err
	}
	venv := runutil.EnvWithVenv(comfyPath, nil)
	reset := mode == "fresh" || mode == "refresh" || mode == "wipe"
	existing := false
	cfg := map[string]string{}
	version := configured
	if version == "" {
		version = "3.12"
	}
	if !reset {
		if _, err := os.Lstat(venv.Root); err == nil {
			existing = true
			cfg, err = readVenvConfig(filepath.Join(venv.Root, "pyvenv.cfg"))
			if err != nil {
				return empty, "", fmt.Errorf("cannot migrate existing venv safely: %w", err)
			}
			if implementation := cfg["implementation"]; implementation != "" && implementation != "CPython" {
				return empty, "", fmt.Errorf("cannot migrate %s packages to CPython", implementation)
			}
			version = cfg["version_info"]
			if version == "" {
				version = cfg["version"]
			}
		} else if !os.IsNotExist(err) {
			return empty, "", err
		}
	}
	abi, err := pythonABI(version)
	if err != nil {
		return empty, "", err
	}
	// Updates select the existing ABI, not the configured default or patch pin.
	if existing {
		version = abi
	}
	runner, err := prepare(toolRoot, comfyPath, version, func(s string) { log(logf, s) })
	if err != nil {
		return empty, "", err
	}
	actual, err := interpreterABI(ctx, runner.Python, runner.Env)
	if err != nil {
		return empty, "", err
	}
	if actual != abi {
		return empty, "", fmt.Errorf("managed Python ABI %s does not match venv ABI %s; packages were not changed", actual, abi)
	}
	// Inherited uv defaults must not turn --allow-existing into a destructive
	// clear or seed packages into the environment during a runtime-only repair.
	runner.Env = runutil.SetEnv(runner.Env, "UV_VENV_CLEAR", "false")
	runner.Env = runutil.SetEnv(runner.Env, "UV_VENV_SEED", "false")
	venv = runutil.EnvWithVenv(comfyPath, runner.Env)
	args := []string{"venv", venv.Root, "--python", runner.Python, "--relocatable", "--no-project", "--no-config", "--no-python-downloads"}
	rollback := func() error { return nil }
	cleanup := func() {}
	if existing {
		args = append(args, "--allow-existing")
		if cfg["include-system-site-packages"] == "true" {
			args = append(args, "--system-site-packages")
		}
		rollback, cleanup, err = snapshotVenv(venv)
		if err != nil {
			return empty, "", err
		}
		log(logf, "Migrating existing venv to ComfyUI-local Python "+abi+" (preserving packages)...")
	} else {
		args = append(args, "--clear")
		log(logf, "Creating relocatable venv with ComfyUI-local Python "+abi+"...")
	}
	defer func() { cleanup() }()
	err = runutil.Command(ctx, logf, comfyPath, runner.Env, "uv", args...)
	if err == nil {
		actual, err = interpreterABI(ctx, venv.Python, venv.Env)
		if err == nil && actual != abi {
			err = fmt.Errorf("venv ABI %s does not match %s", actual, abi)
		}
	}
	if err != nil {
		if restoreErr := rollback(); restoreErr != nil {
			// Leave the backup for manual recovery if restoration itself failed.
			cleanup = func() {}
			return empty, "", errors.Join(err, fmt.Errorf("venv rollback failed: %w", restoreErr))
		}
		return empty, "", err
	}
	return venv, abi, nil
}

func interpreterABI(ctx context.Context, python string, env []string) (string, error) {
	out, err := runutil.Output(ctx, "", env, python, "-c", "import sys, ssl, encodings; assert sys.implementation.name == 'cpython'; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
	if err != nil {
		return "", fmt.Errorf("Python runtime validation failed: %s: %w", strings.TrimSpace(out), err)
	}
	return pythonABI(strings.TrimSpace(out))
}

// uv --allow-existing rewrites interpreter/activation files and metadata, but
// leaves site-packages and existing console scripts in place. Snapshot only the
// small mutable surface (never duplicate potentially multi-GB packages).
func snapshotVenv(venv runutil.Venv) (rollback func() error, cleanup func(), err error) {
	backup, err := os.MkdirTemp(filepath.Dir(venv.Root), ".dasiwa-venv-backup-")
	if err != nil {
		return nil, nil, err
	}
	cleanup = func() { _ = os.RemoveAll(backup) }
	names := []string{filepath.Base(venv.BinDir), "pyvenv.cfg", "CACHEDIR.TAG", ".gitignore", "lib64"}
	for _, name := range names {
		if err := copyVenvEntry(filepath.Join(venv.Root, name), filepath.Join(backup, name)); err != nil {
			cleanup()
			return nil, nil, err
		}
	}
	rollback = func() error {
		var errs []error
		for _, name := range names {
			target := filepath.Join(venv.Root, name)
			if err := os.RemoveAll(target); err != nil {
				errs = append(errs, err)
				continue
			}
			if err := copyVenvEntry(filepath.Join(backup, name), target); err != nil {
				errs = append(errs, err)
			}
		}
		if len(errs) != 0 {
			return fmt.Errorf("backup retained at %s: %w", backup, errors.Join(errs...))
		}
		return nil
	}
	return rollback, cleanup, nil
}

func copyVenvEntry(src, dst string) error {
	info, err := os.Lstat(src)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return err
	}
	if info.Mode()&os.ModeSymlink != 0 {
		link, err := os.Readlink(src)
		if err != nil {
			return err
		}
		return os.Symlink(link, dst)
	}
	if info.IsDir() {
		if err := os.Mkdir(dst, info.Mode().Perm()); err != nil {
			return err
		}
		entries, err := os.ReadDir(src)
		if err != nil {
			return err
		}
		for _, entry := range entries {
			if err := copyVenvEntry(filepath.Join(src, entry.Name()), filepath.Join(dst, entry.Name())); err != nil {
				return err
			}
		}
		return nil
	}
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.OpenFile(dst, os.O_CREATE|os.O_EXCL|os.O_WRONLY, info.Mode().Perm())
	if err != nil {
		return err
	}
	_, copyErr := io.Copy(out, in)
	return errors.Join(copyErr, out.Close())
}
