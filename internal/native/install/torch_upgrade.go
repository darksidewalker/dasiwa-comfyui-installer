package install

import (
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/sage"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/torch"
	"strings"
)

// Keep the optional attention planner aligned with hardware overrides (GTX 10).
func sageTorchPlan(hw torch.Hardware, python, cuda string, cfg torch.CUDAConfig) (string, string) {
	pin, tag := sage.PlanWindowsTorch(python, cuda)
	plan := torch.PlanInstall(hw, cuda, cfg, pin)
	for _, spec := range plan.Packages {
		if strings.HasPrefix(spec, "torch==") {
			pin = strings.TrimPrefix(spec, "torch==")
		}
	}
	if plan.Backend == "cuda" {
		tag = "cu" + strings.ReplaceAll(plan.EffectiveCUDA, ".", "")
	}
	return pin, tag
}

// Import success alone cannot validate kernels compiled against an older Torch.
// Remove only CUDA compiled extensions when the selected Torch ABI changes;
// selected extensions will be installed again, unselected ones stay removed.
func attentionResetArgs(installed string, plan torch.InstallPlan) []string {
	if installed == "" || plan.Backend != "cuda" {
		return nil
	}
	for _, spec := range plan.Packages {
		if strings.HasPrefix(spec, "torch==") {
			expected := strings.TrimPrefix(spec, "torch==") + "+cu" + strings.ReplaceAll(plan.EffectiveCUDA, ".", "")
			if installed != expected {
				return []string{"pip", "uninstall", "sageattention", "flash-attn"}
			}
		}
	}
	return nil
}
