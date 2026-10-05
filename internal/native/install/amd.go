package install

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/runutil"
)

func validateAMDPlatform(goos, arch, build string) error {
	if arch != "amd64" || (goos != "linux" && goos != "windows") {
		return fmt.Errorf("AMD ROCm install supports only Windows/Linux x86_64, not %s/%s", goos, arch)
	}
	if goos == "windows" {
		n, err := strconv.Atoi(strings.TrimSpace(build))
		if err != nil || n < 26200 {
			return fmt.Errorf("AMD ROCm 10.0 requires Windows 11 25H2 (build 26200 or newer); detected build %q", build)
		}
	}
	return nil
}

func validateAMDHost(ctx context.Context) error {
	build := ""
	if runtime.GOOS == "windows" {
		probeCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
		defer cancel()
		out, err := runutil.Output(probeCtx, "", nil, "powershell", "-NoProfile", "-NonInteractive", "-Command", `(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').CurrentBuildNumber`)
		if err != nil {
			return fmt.Errorf("cannot verify AMD Windows prerequisite: %w", err)
		}
		build = strings.TrimSpace(out)
	}
	return validateAMDPlatform(runtime.GOOS, runtime.GOARCH, build)
}

func validateAMDABI(version string) error {
	abi, err := pythonABI(version)
	if err != nil {
		return err
	}
	if abi != "3.12" && abi != "3.13" {
		return fmt.Errorf("AMD ROCm install requires Python 3.12 or 3.13; selected ABI is %s. Updates preserve the existing ABI; use Refresh only if you intend to rebuild packages", abi)
	}
	return nil
}

// Inspect update metadata before checkout, wipe or managed-runtime migration.
// Never silently change an existing environment's package ABI.
func validateAMDSelection(comfyPath, mode, configured string) error {
	version := configured
	if version == "" {
		version = "3.12"
	}
	if mode != "fresh" && mode != "refresh" && mode != "wipe" {
		root := filepath.Join(comfyPath, "venv")
		if _, err := os.Lstat(root); err == nil {
			cfg, err := readVenvConfig(filepath.Join(root, "pyvenv.cfg"))
			if err != nil {
				return fmt.Errorf("cannot validate existing AMD venv safely: %w", err)
			}
			if impl := cfg["implementation"]; impl != "" && impl != "CPython" {
				return fmt.Errorf("AMD requires CPython, existing venv uses %s", impl)
			}
			version = cfg["version_info"]
			if version == "" {
				version = cfg["version"]
			}
		} else if !os.IsNotExist(err) {
			return err
		}
	}
	return validateAMDABI(version)
}
