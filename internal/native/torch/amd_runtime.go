package torch

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/runutil"
)

// Pin the whole AMD stack for subsequent uv operations, including node child
// installers inheriting this environment. A file URI preserves paths containing
// spaces: uv splits bare UV_CONSTRAINT paths at spaces.
func AMDDependencyEnv(env []string, comfyPath string) ([]string, error) {
	path, err := filepath.Abs(filepath.Join(comfyPath, ".dasiwa", "rocm-constraints.txt"))
	if err != nil {
		return nil, err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return nil, err
	}
	const constraints = "torch==2.13.0+rocm10.0.0\ntorchvision==0.28.0+rocm10.0.0\ntorchaudio==2.11.0.2+rocm10.0.0\n"
	if err := os.WriteFile(path, []byte(constraints), 0644); err != nil {
		return nil, err
	}
	uriPath := filepath.ToSlash(path)
	if !strings.HasPrefix(uriPath, "/") {
		uriPath = "/" + uriPath
	}
	uri := (&url.URL{Scheme: "file", Path: uriPath}).String()
	// Preserve user constraints, but never user indexes over the selected backend.
	previous := runutil.GetEnv(env, "UV_CONSTRAINT")
	if previous != "" {
		uri = previous + " " + uri
	}
	env = runutil.SetEnv(env, "UV_CONSTRAINT", uri)
	env = runutil.SetEnv(env, "UV_INDEX", AMDIndexURL)
	env = runutil.SetEnv(env, "UV_DEFAULT_INDEX", "https://pypi.org/simple")
	return env, nil
}

const amdGPUProbe = `import json, torch, torchvision, torchaudio
available = bool(torch.version.hip) and torch.cuda.is_available()
arch = name = ''
computed = False
if available:
    props = torch.cuda.get_device_properties(0)
    name = props.name
    arch = getattr(props, 'gcnArchName', '')
    x = torch.ones((2, 2), device='cuda')
    y = x @ x
    torch.cuda.synchronize()
    computed = bool(torch.isfinite(y).all().item() and (y == 2).all().item())
print(json.dumps({'torch': torch.__version__, 'vision': torchvision.__version__, 'audio': torchaudio.__version__, 'cuda': torch.version.cuda or '', 'hip': torch.version.hip or '', 'available': available, 'arch': arch, 'computed': computed, 'name': name}))
`

func validateAMDProbe(out string, hw Hardware) error {
	target, err := AMDTarget(hw)
	if err != nil {
		return err
	}
	lines := strings.Split(strings.TrimSpace(out), "\n")
	data := lines[len(lines)-1]
	probe, err := parseInstalledProbe(data)
	if err != nil {
		return err
	}
	if !installedSatisfiesPlan(probe, amdInstallPlan(hw)) {
		return fmt.Errorf("AMD torch/vision/audio stack does not match pinned ROCm 10.0 versions")
	}
	var gpu struct {
		Available bool   `json:"available"`
		Computed  bool   `json:"computed"`
		Arch      string `json:"arch"`
	}
	if err := json.Unmarshal([]byte(data), &gpu); err != nil {
		return err
	}
	arch, _, _ := strings.Cut(gpu.Arch, ":")
	if !gpu.Available || !gpu.Computed || arch != target {
		return fmt.Errorf("AMD GPU verification failed: available=%t, GPU target=%q (selected %s), tensor computation=%t; check AMD driver, GPU selection and Linux device permissions", gpu.Available, gpu.Arch, target, gpu.Computed)
	}
	return nil
}

// HIP metadata alone does not prove that GPU kernels work. Verify an actual
// synchronized matrix multiply on the selected architecture before success.
func VerifyAMD(ctx context.Context, env []string, python string, hw Hardware, logf runutil.LogFunc) error {
	if _, err := AMDTarget(hw); err != nil {
		return err
	}
	probeCtx, cancel := context.WithTimeout(ctx, 90*time.Second)
	defer cancel()
	out, err := runutil.Output(probeCtx, "", env, python, "-c", amdGPUProbe)
	if err != nil {
		return fmt.Errorf("AMD GPU import/computation probe failed; check ROCm driver and device access: %s: %w", strings.TrimSpace(out), err)
	}
	if err := validateAMDProbe(out, hw); err != nil {
		return err
	}
	log(logf, "AMD ROCm GPU verified: pinned torch/vision/audio, matching architecture and synchronized tensor computation.")
	return nil
}
