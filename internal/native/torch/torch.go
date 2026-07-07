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
	Vendor           string
	GPUName          string
	Backend          string
	EffectiveCUDA    string
	IndexURL         string
	Packages         []string
	AlternateIndexes []string // fallback index URLs (e.g. direct R2, community mirrors)
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
	env = applyUvRuntimeEnv(env)
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
	env = applyUvRuntimeEnv(env)
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
	// Append alternate mirrors as extra-index-url so uv falls back
	// sequentially when the primary host refuses connections.
	for _, alt := range plan.AlternateIndexes {
		if alt != "" && alt != plan.IndexURL {
			args = append(args, "--extra-index-url", alt)
		}
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
		targetCU = effectiveNVIDIACUDA(targetCU)
		plan.Backend = "cuda"
		plan.EffectiveCUDA = targetCU
		plan.IndexURL = whlURL + "cu" + strings.ReplaceAll(targetCU, ".", "")
		plan.AlternateIndexes = alternatePyTorchIndexes(targetCU)
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
			plan.IndexURL = "https://rocm.nightlies.amd.com/v2/gfx110X-all/"
			plan.Packages = []string{"--pre", "torch", "torchvision", "torchaudio"}
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
		return "12.8"
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

// alternatePyTorchIndexes returns backup index URLs in priority order for
// PyTorch wheels when the primary host fails (e.g., Cloudflare R2 TLS issues).
// The first entry is always the official host; subsequent entries are
// alternative endpoints within PyTorch's distribution infrastructure.
// Note: These alternates assume the same wheel tree exists at each URL.
// If all hosts fail, the installer logs the error and exits with status 2.
func alternatePyTorchIndexes(cudaTarget string) []string {
	base := strings.ReplaceAll(cudaTarget, ".", "")
	mirrors := []string{}
	// Direct R2 storage endpoint (bypasses any intermediate CNAME).
	mirrors = append(mirrors, "https://download.r2.pytorch.org/whl/cu"+base)
	// PyTorch nightly channel (shares stable wheel tree in some regions).
	mirrors = append(mirrors, "https://download.pytorch.org/whl/nightly/cu"+base)
	// Hugging Face mirror (community-maintained cache of PyTorch wheels).
	// Requires HUGGINGFACE_TOKEN env var set by user for private model access.
	mirrors = append(mirrors, "https://huggingface.co/pytorch/pytorch/resolve/main/whl/cu"+base)
	return mirrors
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
