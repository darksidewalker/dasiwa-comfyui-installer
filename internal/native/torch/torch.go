package torch

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/runutil"
)

type Hardware struct {
	Vendor string
	Name   string
}

type CUDAConfig struct {
	Global        string
	MinCUDAFor50x string
}

type InstallPlan struct {
	Vendor        string
	GPUName       string
	Backend       string
	EffectiveCUDA string
	IndexURL      string
	Packages      []string
}

type installedProbe struct {
	TorchVersion string
	CUDA         string
	HIP          string
}

var PriorityPackages = []string{
	"kornia==0.8.2",
	"setuptools==81.0.0",
}

var cuda128Packages = []string{"torch==2.9.1", "torchvision==0.24.1", "torchaudio==2.9.1"}

func Install(ctx context.Context, env []string, hw Hardware, cudaTarget string, cfg CUDAConfig, pinTorch string, logf runutil.LogFunc) error {
	args := InstallArgs(hw, cudaTarget, cfg, pinTorch)
	log(logf, fmt.Sprintf("Installing Torch for %s (%s)...", hw.Vendor, strings.ToUpper(hw.Name)))
	return runutil.Command(ctx, logf, "", env, "uv", args...)
}

func Reassert(ctx context.Context, env []string, python string, hw Hardware, cudaTarget string, cfg CUDAConfig, pinTorch string, logf runutil.LogFunc) error {
	plan := PlanInstall(hw, cudaTarget, cfg, pinTorch)
	if ok, detail := CurrentInstallSatisfies(ctx, env, python, plan, pinTorch); ok {
		log(logf, "Torch backend already matches selection: "+detail)
		return nil
	} else if detail != "" {
		log(logf, "Torch backend check requires repair: "+detail)
	}
	args := InstallArgs(hw, cudaTarget, cfg, pinTorch)
	log(logf, fmt.Sprintf("Reasserting Torch backend for %s (%s)...", hw.Vendor, strings.ToUpper(hw.Name)))
	return runutil.Command(ctx, logf, "", env, "uv", args...)
}

func CurrentInstallSatisfies(ctx context.Context, env []string, python string, plan InstallPlan, pinTorch string) (bool, string) {
	if python == "" {
		return false, "venv Python path is empty"
	}
	probe, err := probeInstalled(ctx, env, python)
	if err != nil {
		return false, err.Error()
	}
	if pinTorch != "" && !pinnedVersionMatches(probe.TorchVersion, pinTorch) {
		return false, fmt.Sprintf("torch %s != pinned %s", probe.TorchVersion, pinTorch)
	}
	if !installedSatisfiesPlan(probe, plan) {
		return false, fmt.Sprintf("torch %s cuda=%q hip=%q does not match %s %s", probe.TorchVersion, probe.CUDA, probe.HIP, plan.Backend, plan.EffectiveCUDA)
	}
	return true, fmt.Sprintf("torch %s cuda=%q hip=%q", probe.TorchVersion, probe.CUDA, probe.HIP)
}

func probeInstalled(ctx context.Context, env []string, python string) (installedProbe, error) {
	script := "import json, torch, torchvision, torchaudio; print(json.dumps({'torch': torch.__version__, 'cuda': torch.version.cuda or '', 'hip': getattr(torch.version, 'hip', '') or ''}))"
	out, err := runutil.Output(ctx, "", env, python, "-c", script)
	if err != nil {
		return installedProbe{}, fmt.Errorf("torch import probe failed: %w", err)
	}
	return parseInstalledProbe(out)
}

func parseInstalledProbe(out string) (installedProbe, error) {
	var raw struct {
		Torch string `json:"torch"`
		CUDA  string `json:"cuda"`
		HIP   string `json:"hip"`
	}
	if err := json.Unmarshal([]byte(strings.TrimSpace(out)), &raw); err != nil {
		return installedProbe{}, fmt.Errorf("could not parse torch import probe: %w", err)
	}
	if raw.Torch == "" {
		return installedProbe{}, fmt.Errorf("torch import probe did not report a torch version")
	}
	return installedProbe{
		TorchVersion: strings.TrimSpace(raw.Torch),
		CUDA:         strings.TrimSpace(raw.CUDA),
		HIP:          strings.TrimSpace(raw.HIP),
	}, nil
}

func installedSatisfiesPlan(probe installedProbe, plan InstallPlan) bool {
	switch plan.Backend {
	case "cuda":
		return sameMajorMinor(probe.CUDA, plan.EffectiveCUDA)
	case "rocm":
		return probe.HIP != ""
	default:
		return true
	}
}

func InstallArgs(hw Hardware, cudaTarget string, cfg CUDAConfig, pinTorch string) []string {
	plan := PlanInstall(hw, cudaTarget, cfg, pinTorch)
	args := []string{"pip", "install"}
	args = append(args, plan.Packages...)
	if plan.IndexURL != "" {
		args = append(args, "--index-url", plan.IndexURL)
	}
	return args
}

func PlanInstall(hw Hardware, cudaTarget string, cfg CUDAConfig, pinTorch string) InstallPlan {
	vendor := strings.ToUpper(hw.Vendor)
	gpuName := strings.ToUpper(hw.Name)
	whlURL := "https://download.pytorch.org/whl/"
	plan := InstallPlan{Vendor: vendor, GPUName: gpuName, Backend: "default"}
	if vendor == "NVIDIA" {
		targetCU := cudaTarget
		if targetCU == "" {
			targetCU = cfg.Global
		}
		if isGTX10(hw) {
			targetCU = "12.1"
		} else if strings.Contains(gpuName, "RTX 50") && cfg.MinCUDAFor50x != "" {
			targetCU = cfg.MinCUDAFor50x
		}
		if strings.HasPrefix(targetCU, "13.") {
			targetCU = "12.8"
		}
		plan.Backend = "cuda"
		plan.EffectiveCUDA = targetCU
		plan.IndexURL = whlURL + "cu" + strings.ReplaceAll(targetCU, ".", "")
		if targetCU == "12.1" {
			plan.Packages = []string{"torch==2.4.1", "torchvision==0.19.1", "torchaudio==2.4.1"}
		} else if targetCU == "12.8" {
			plan.Packages = append([]string(nil), cuda128Packages...)
		} else if pinTorch != "" {
			plan.Packages = []string{"torch==" + pinTorch, "torchvision", "torchaudio"}
		} else {
			plan.Packages = []string{"torch", "torchvision", "torchaudio"}
		}
		return plan
	}
	if vendor == "AMD" {
		plan.Backend = "rocm"
		switch {
		case strings.Contains(gpuName, "GFX110") || strings.Contains(gpuName, "RX 7000"):
			plan.IndexURL = "https://rocm.nightlies.amd.com/v2/gfx110X-all/"
			plan.Packages = []string{"--pre", "torch", "torchvision", "torchaudio"}
		case strings.Contains(gpuName, "GFX1151") || strings.Contains(gpuName, "STRIX"):
			plan.IndexURL = "https://rocm.nightlies.amd.com/v2/gfx1151/"
			plan.Packages = []string{"--pre", "torch", "torchvision", "torchaudio"}
		case strings.Contains(gpuName, "GFX120") || strings.Contains(gpuName, "RX 9000"):
			plan.IndexURL = "https://rocm.nightlies.amd.com/v2/gfx120X-all/"
			plan.Packages = []string{"--pre", "torch", "torchvision", "torchaudio"}
		default:
			plan.IndexURL = whlURL + "rocm7.1"
			plan.Packages = []string{"torch", "torchvision", "torchaudio"}
		}
		return plan
	}
	if vendor == "INTEL" {
		plan.Backend = "xpu"
		plan.IndexURL = whlURL + "xpu"
		plan.Packages = []string{"torch", "torchvision", "torchaudio"}
		return plan
	}
	plan.Packages = []string{"torch", "torchvision", "torchaudio"}
	return plan
}

func PriorityInstallArgs(wantSage bool, isWindows bool, pinTorch string, hw Hardware, cudaTarget string) []string {
	packages := append([]string{}, PriorityPackages...)
	if wantSage {
		if isWindows {
			packages = append(packages, "triton-windows")
		} else {
			packages = append(packages, "triton>=3.7,<3.8")
		}
	}
	if pinTorch != "" {
		packages = append(packages, "torch=="+pinTorch)
	}
	args := append([]string{"pip", "install", "--upgrade", "--no-deps"}, packages...)
	if pinTorch != "" && strings.ToUpper(hw.Vendor) == "NVIDIA" && cudaTarget != "" {
		args = append(args,
			"--extra-index-url", "https://download.pytorch.org/whl/cu"+strings.ReplaceAll(cudaTarget, ".", ""),
			"--index-strategy", "unsafe-best-match",
		)
	}
	return args
}

func isGTX10(hw Hardware) bool {
	name := strings.ToUpper(hw.Name)
	return strings.ToUpper(hw.Vendor) == "NVIDIA" && (strings.Contains(name, "GTX 10") || strings.Contains(name, "PASCAL") || strings.Contains(name, "LEGACY"))
}

func isRTX50(hw Hardware) bool {
	name := strings.ToUpper(hw.Name)
	return strings.ToUpper(hw.Vendor) == "NVIDIA" && (strings.Contains(name, "RTX 50") || strings.Contains(name, "BLACKWELL"))
}

func sameMajorMinor(a, b string) bool {
	ap := strings.Split(a, ".")
	bp := strings.Split(b, ".")
	return len(ap) >= 2 && len(bp) >= 2 && ap[0] == bp[0] && ap[1] == bp[1]
}

func pinnedVersionMatches(installed, pinned string) bool {
	if installed == pinned {
		return true
	}
	if strings.Contains(pinned, "+") {
		return false
	}
	return strings.Split(installed, "+")[0] == pinned
}

func log(logf runutil.LogFunc, line string) {
	if logf != nil {
		logf(line)
	}
}
