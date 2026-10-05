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
	Err           error
}

type installedProbe struct {
	VisionVersion string
	AudioVersion  string
	TorchVersion  string
	CUDA          string
	HIP           string
}

var PriorityPackages = []string{
	"kornia==0.8.2",
	"setuptools==81.0.0",
}

// PyTorch 2.11 is the newest stable cu130 release with a matching torchaudio
// wheel on both Python 3.12 and 3.13. Newer cu130/cu132 Torch releases do not
// publish a matching torchaudio package, so selecting them produces a mixed,
// unsupported stack for ComfyUI audio nodes.
var cuda130Packages = []string{"torch==2.11.0", "torchvision==0.26.0", "torchaudio==2.11.0"}

func Install(ctx context.Context, env []string, hw Hardware, cudaTarget string, cfg CUDAConfig, pinTorch string, logf runutil.LogFunc) error {
	if plan := PlanInstall(hw, cudaTarget, cfg, pinTorch); plan.Err != nil {
		return plan.Err
	}
	args := InstallArgs(hw, cudaTarget, cfg, pinTorch)
	log(logf, fmt.Sprintf("Installing Torch for %s (%s)...", hw.Vendor, strings.ToUpper(hw.Name)))
	env = applyUvRuntimeEnv(env)
	return runutil.Command(ctx, logf, "", env, "uv", args...)
}

func Reassert(ctx context.Context, env []string, python string, hw Hardware, cudaTarget string, cfg CUDAConfig, pinTorch string, logf runutil.LogFunc) error {
	plan := PlanInstall(hw, cudaTarget, cfg, pinTorch)
	if plan.Err != nil {
		return plan.Err
	}
	if ok, detail := CurrentInstallSatisfies(ctx, env, python, plan, pinTorch); ok {
		log(logf, "Torch backend already matches selection: "+detail)
		return nil
	} else if detail != "" {
		log(logf, "Torch backend check requires repair: "+detail)
	}
	args := InstallArgs(hw, cudaTarget, cfg, pinTorch)
	log(logf, fmt.Sprintf("Reasserting Torch backend for %s (%s)...", hw.Vendor, strings.ToUpper(hw.Name)))
	env = applyUvRuntimeEnv(env)
	return runutil.Command(ctx, logf, "", env, "uv", args...)
}

func CurrentInstallSatisfies(ctx context.Context, env []string, python string, plan InstallPlan, pinTorch string) (bool, string) {
	if plan.Err != nil {
		return false, plan.Err.Error()
	}
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
	script := "import json, torch, torchvision, torchaudio; print(json.dumps({'torch': torch.__version__, 'vision': torchvision.__version__, 'audio': torchaudio.__version__, 'cuda': torch.version.cuda or '', 'hip': getattr(torch.version, 'hip', '') or ''}))"
	out, err := runutil.Output(ctx, "", env, python, "-c", script)
	if err != nil {
		return installedProbe{}, fmt.Errorf("torch import probe failed: %w", err)
	}
	return parseInstalledProbe(out)
}

func parseInstalledProbe(out string) (installedProbe, error) {
	var raw struct {
		Vision string `json:"vision"`
		Audio  string `json:"audio"`
		Torch  string `json:"torch"`
		CUDA   string `json:"cuda"`
		HIP    string `json:"hip"`
	}
	if err := json.Unmarshal([]byte(strings.TrimSpace(out)), &raw); err != nil {
		return installedProbe{}, fmt.Errorf("could not parse torch import probe: %w", err)
	}
	if raw.Torch == "" {
		return installedProbe{}, fmt.Errorf("torch import probe did not report a torch version")
	}
	return installedProbe{
		VisionVersion: strings.TrimSpace(raw.Vision),
		AudioVersion:  strings.TrimSpace(raw.Audio),
		TorchVersion:  strings.TrimSpace(raw.Torch),
		CUDA:          strings.TrimSpace(raw.CUDA),
		HIP:           strings.TrimSpace(raw.HIP),
	}, nil
}

func installedSatisfiesPlan(probe installedProbe, plan InstallPlan) bool {
	switch plan.Backend {
	case "cuda":
		return sameMajorMinor(probe.CUDA, plan.EffectiveCUDA)
	case "rocm":
		return probe.HIP != "" && probe.CUDA == "" && probe.TorchVersion == "2.13.0+rocm10.0.0" && probe.VisionVersion == "0.28.0+rocm10.0.0" && probe.AudioVersion == "2.11.0.2+rocm10.0.0"
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
	vendor := strings.ToUpper(strings.TrimSpace(hw.Vendor))
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
		targetCU = effectiveNVIDIACUDA(targetCU)
		plan.Backend = "cuda"
		plan.EffectiveCUDA = targetCU
		plan.IndexURL = whlURL + "cu" + strings.ReplaceAll(targetCU, ".", "")
		if targetCU == "12.1" {
			plan.Packages = []string{"torch==2.4.1", "torchvision==0.19.1", "torchaudio==2.4.1"}
		} else if targetCU == "13.0" {
			plan.Packages = append([]string(nil), cuda130Packages...)
		} else if pinTorch != "" {
			plan.Packages = []string{"torch==" + pinTorch, "torchvision", "torchaudio"}
		} else {
			plan.Packages = []string{"torch", "torchvision", "torchaudio"}
		}
		return plan
	}
	if vendor == "AMD" {
		return amdInstallPlan(hw)
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
	wantTriton := strings.EqualFold(strings.TrimSpace(hw.Vendor), "NVIDIA") && (wantSage || isWindows)
	if wantTriton {
		if isWindows {
			packages = append(packages, windowsTritonSpec(pinTorch))
		} else {
			packages = append(packages, "triton>=3.7,<3.8")
		}
	}
	if pinTorch != "" {
		packages = append(packages, "torch=="+pinTorch)
	}
	args := append([]string{"pip", "install", "--upgrade", "--no-deps"}, packages...)
	if pinTorch != "" && strings.ToUpper(hw.Vendor) == "NVIDIA" && cudaTarget != "" {
		cudaTarget = effectiveNVIDIACUDA(cudaTarget)
		args = append(args,
			"--extra-index-url", "https://download.pytorch.org/whl/cu"+strings.ReplaceAll(cudaTarget, ".", ""),
			"--index-strategy", "unsafe-best-match",
		)
	}
	return args
}

func effectiveNVIDIACUDA(target string) string {
	if strings.HasPrefix(target, "13.") {
		// PyTorch publishes a complete Python 3.12 Linux/Windows package set
		// (torch, torchvision, and torchaudio) for cu130. CUDA 13.2 lacks a
		// matching torchaudio wheel, while the CUDA 13.x toolkits can compile
		// extensions against the cu130 wheel family with a minor-version warning.
		return "13.0"
	}
	return target
}

func windowsTritonSpec(torchVersion string) string {
	switch {
	case strings.HasPrefix(torchVersion, "2.9."):
		return "triton-windows>=3.5,<3.6"
	case strings.HasPrefix(torchVersion, "2.10."), strings.HasPrefix(torchVersion, "2.11."):
		return "triton-windows>=3.6,<3.7"
	case strings.HasPrefix(torchVersion, "2.12."):
		return "triton-windows>=3.7,<3.8"
	default:
		return "triton-windows"
	}
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

// applyUvRuntimeEnv merges uv reliability-tuning environment variables into
// the existing env slice without clobbering user-set values.
func applyUvRuntimeEnv(env []string) []string {
	for _, kv := range uvRuntimeEnv() {
		parts := strings.SplitN(kv, "=", 2)
		if len(parts) == 2 {
			env = runutil.SetEnv(env, parts[0], parts[1])
		}
	}
	return env
}

// uvRuntimeEnv returns environment variables that improve reliability of
// `uv pip install` against flaky or rate-limited indices:
//   - UV_HTTP_TIMEOUT: generous per-request timeout (avoids premature HandshakeFailure aborts)
//   - UV_RETRY_COUNT: retry transient failures before giving up
//   - UV_MAX_CONCURRENT_DOWNLOADS: throttle parallel downloads to avoid provider rate limits
//   - UV_NO_BUILD_ISOLATION: skip isolated build environments where metadata fetch may fail
func uvRuntimeEnv() []string {
	return []string{
		"UV_HTTP_TIMEOUT=120",
		"UV_RETRY_COUNT=5",
		"UV_MAX_CONCURRENT_DOWNLOADS=2",
		"UV_NO_BUILD_ISOLATION=1",
	}
}
