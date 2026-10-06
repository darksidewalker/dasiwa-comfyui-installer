package torch

import (
	"context"
	"fmt"
	"regexp"
	"strings"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/runutil"
)

// ROCm is source-only and uses setuptools.build_meta. Torch installation disables
// build isolation, so this must precede both initial installation and repair.
func prepareAMDBuild(ctx context.Context, env []string, logf runutil.LogFunc) error {
	log(logf, "Ensuring setuptools for the AMD ROCm source-package build...")
	if err := runutil.Command(ctx, logf, "", env, "uv", amdBuildInstallArgs()...); err != nil {
		return fmt.Errorf("prepare AMD ROCm build dependencies: %w", err)
	}
	return nil
}

func amdBuildInstallArgs() []string {
	// Use the normal package index, not AMD's Torch index; install only the
	// declared build prerequisite into the selected ComfyUI venv.
	return []string{"pip", "install", "--only-binary", "setuptools", "--no-deps", "setuptools>=70.2.0"}
}

const AMDIndexURL = "https://stable.repo.amd.com/rocm/whl-next/"

var amdGFXPattern = regexp.MustCompile(`(?i)\bgfx[0-9a-f]+\b`)
var amdMobilePattern = regexp.MustCompile(`(?i)\bRX\s*\d+[MS]\b|\bMOBILE\b|\bLAPTOP\b`)
var amdModelPattern = regexp.MustCompile(`(?i)\b(RX\s*\d+(?:\s*XTX|\s*XT)?|W\d+|R\d+|80[456]0S)\b`)

// Start with explicit desktop/APU mappings. Unknown families must not silently
// receive RDNA3 kernels; OS names can be disambiguated with a known gfx target.
var amdModelTargets = map[string]string{
	"RX6800": "gfx1030", "RX6800XT": "gfx1030", "RX6900XT": "gfx1030", "RX6950XT": "gfx1030", "W6800": "gfx1030",
	"RX7600": "gfx1102", "RX7600XT": "gfx1102",
	"RX7700XT": "gfx1101", "RX7800XT": "gfx1101",
	"RX7900XT": "gfx1100", "RX7900XTX": "gfx1100", "W7800": "gfx1100", "W7900": "gfx1100",
	"RX9060": "gfx1200", "RX9060XT": "gfx1200",
	"RX9070": "gfx1201", "RX9070XT": "gfx1201", "R9700": "gfx1201",
	"8060S": "gfx1151", "8050S": "gfx1151", "8040S": "gfx1151",
}

func AMDTarget(hw Hardware) (string, error) {
	name := strings.ToUpper(strings.TrimSpace(hw.Name))
	if !strings.EqualFold(strings.TrimSpace(hw.Vendor), "AMD") {
		return "", fmt.Errorf("AMD target requested for vendor %q", hw.Vendor)
	}
	if amdMobilePattern.MatchString(name) {
		return "", fmt.Errorf("AMD mobile GPU %q is not in the installer support list", hw.Name)
	}
	target := ""
	for _, model := range amdModelPattern.FindAllString(name, -1) {
		mapped := amdModelTargets[strings.ReplaceAll(model, " ", "")]
		if mapped == "" {
			return "", fmt.Errorf("AMD GPU model %q is not in the installer support list", model)
		}
		if target != "" && mapped != target {
			return "", fmt.Errorf("conflicting AMD GPU models in %q", hw.Name)
		}
		target = mapped
	}
	for _, gfx := range amdGFXPattern.FindAllString(name, -1) {
		gfx = strings.ToLower(gfx)
		switch gfx {
		case "gfx1030", "gfx1100", "gfx1101", "gfx1102", "gfx1151", "gfx1200", "gfx1201":
		default:
			return "", fmt.Errorf("AMD GPU target %s is not in the installer support list", gfx)
		}
		if target != "" && target != gfx {
			return "", fmt.Errorf("AMD GPU name/target mismatch in %q: %s versus %s", hw.Name, target, gfx)
		}
		target = gfx
	}
	if target == "" {
		return "", fmt.Errorf("AMD GPU %q is not recognized; select a supported exact model or gfx target (gfx1030, gfx1100, gfx1101, gfx1102, gfx1151, gfx1200, gfx1201)", hw.Name)
	}
	return target, nil
}

func amdInstallPlan(hw Hardware) InstallPlan {
	plan := InstallPlan{Vendor: "AMD", GPUName: strings.ToUpper(hw.Name), Backend: "rocm"}
	target, err := AMDTarget(hw)
	if err != nil {
		plan.Err = err
		return plan
	}
	plan.IndexURL = AMDIndexURL
	plan.Packages = []string{
		"torch[device-" + target + "]==2.13.0+rocm10.0.0",
		"torchvision[device-" + target + "]==0.28.0+rocm10.0.0",
		"torchaudio==2.11.0.2+rocm10.0.0",
	}
	return plan
}
