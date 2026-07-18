package install

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"

	installer "github.com/darksidewalker/dasiwa-comfyui-installer"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/appconfig"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/bootstrap"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/comfypath"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/comfyui"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/downloader"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/ffmpeg"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/launcher"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/nodes"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/flashattn"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/radial"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/runutil"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/sage"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/torch"
)

// validatePythonVersion checks Python version and platform compatibility before torch installation.
// Returns an error if the combination is known to fail, otherwise warns.
func validatePythonVersion(pythonPath string, hw torch.Hardware, logf runutil.LogFunc) error {
	// Get Python version from executable
	versionOutput, err := runutil.Output(context.Background(), "", nil, pythonPath, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
	if err != nil {
		return fmt.Errorf("could not determine Python version: %w", err)
	}
	
	versionStr := strings.TrimSpace(versionOutput)
	parts := strings.Split(versionStr, ".")
	if len(parts) < 2 {
		return fmt.Errorf("could not parse Python version: %s", versionStr)
	}
	
	major := parts[0]
	minor := parts[1]
	
	// Convert to int for comparison
	var majorInt, minorInt int
	fmt.Sscanf(major, "%d", &majorInt)
	fmt.Sscanf(minor, "%d", &minorInt)
	
	vendor := strings.ToUpper(hw.Vendor)
	
	// Windows + AMD ROCm: PyTorch ROCm wheels are Linux-only (manylinux)
	// Even with --pre flag on nightly indexes, no functional Windows wheels exist
	if runtime.GOOS == "windows" && vendor == "AMD" {
		errMsg := fmt.Sprintf("Windows + AMD ROCm is not supported: PyTorch ROCm wheels are Linux-only (manylinux_2_28_x86_64).\n"+
			"You cannot use AMD GPUs with ComfyUI on Windows via PyTorch.\n"+
			"Options:\n"+
			"  1. Install WSL2 (Ubuntu) and run ComfyUI inside WSL2\n"+
			"  2. Switch to NVIDIA GPU (CUDA is fully supported on Windows)\n"+
			"  3. Use Intel Arc GPU with XPU backend (experimental)")
		return fmt.Errorf("%s", errMsg)
	}
	
	// Python 3.12+ on AMD ROCm: Limited support in nightly wheels
	if vendor == "AMD" && majorInt == 3 && minorInt >= 12 {
		logf("Warning: Python 3.12 detected. AMD ROCm nightly wheels may have limited 3.12 support.")
		logf("If installation fails, downgrade to Python 3.11 and retry.")
		// Don't block - some nightly builds may work
	}
	
	return nil
}

type Config struct {
	Python struct {
		DisplayName string `json:"display_name"`
	} `json:"python"`
	ComfyUI struct {
		Version        string `json:"version"`
		FallbackBranch string `json:"fallback_branch"`
	} `json:"comfyui"`
	CUDA struct {
		Global        string `json:"global"`
		MinCUDAFor50x string `json:"min_cuda_for_50xx"`
	} `json:"cuda"`
	URLs              map[string]string `json:"urls"`
	CustomNodes       []string          `json:"custom_nodes"`
	OptionalDownloads []downloader.Item `json:"optional_downloads"`
}

type Choices struct {
	InstallMode     string         `json:"install_mode"`
	ConfirmWipe     bool           `json:"confirm_wipe"`
	HW              torch.Hardware `json:"hw"`
	WantSage        bool           `json:"want_sage"`
	WantRadial      bool           `json:"want_radial"`
	WantFlash       bool           `json:"want_flash"`
	WantFFmpeg      bool           `json:"want_ffmpeg"`
	WantCleanup     bool           `json:"want_cleanup"`
	ComfyPath       string         `json:"comfy_path"`
	TargetVersion   string         `json:"target_version"`
	CUDATarget      string         `json:"cuda_target"`
	Downloads       string         `json:"downloads"`
	DownloadIndices []int          `json:"download_indices"`
	DownloadNames   []string       `json:"download_names"`
	ConfigOverrides map[string]any `json:"config_overrides"`
}

func Run(ctx context.Context, root string, choices Choices, runner *bootstrap.PythonRunner, logf runutil.LogFunc) error {
	cfg, err := loadConfig(root, choices)
	if err != nil {
		return err
	}
	comfyPath := resolveComfyPath(root, choices.ComfyPath)
	if choices.InstallMode == "wipe" {
		if !choices.ConfirmWipe {
			return fmt.Errorf("wipe requested without confirmation")
		}
		log(logf, "Wiping "+comfyPath+"...")
		if err := os.RemoveAll(comfyPath); err != nil {
			return err
		}
	}
	targetVersion := choices.TargetVersion
	if targetVersion == "" {
		targetVersion = cfg.ComfyUI.Version
	}
	if targetVersion == "" || strings.EqualFold(targetVersion, "latest") {
		targetVersion = "master"
	}
	fallback := cfg.ComfyUI.FallbackBranch
	if fallback == "" {
		fallback = "master"
	}
	if err := comfyui.Sync(ctx, comfyPath, targetVersion, fallback, logf); err != nil {
		return err
	}
	venv := runutil.EnvWithVenv(comfyPath, runner.Env)
	needVenv := choices.InstallMode == "fresh" || choices.InstallMode == "refresh" || choices.InstallMode == "wipe" || !fileExists(venv.Python)
	if needVenv {
		py := cfg.Python.DisplayName
		if py == "" {
			py = "3.12"
		}
		log(logf, "Creating venv with Python "+py+"...")
		if err := runutil.Command(ctx, logf, root, runner.Env, "uv", "venv", venv.Root, "--python", py, "--clear"); err != nil {
			return err
		}
	} else {
		log(logf, "Reusing existing virtual environment.")
	}
	venv = runutil.EnvWithVenv(comfyPath, runner.Env)
	selected := selectedDownloads(cfg.OptionalDownloads, choices, comfyPath)
	if len(selected) > 0 {
		if err := downloader.InstallSelectedWithFS(selected, comfyPath, root, installer.Files, func(s string) { log(logf, s) }); err != nil {
		log(logf, "Download error: "+err.Error())
	}
	}
	cudaTarget := choices.CUDATarget
	if cudaTarget == "" {
		cudaTarget = cfg.CUDA.Global
	}
	pinTorch := ""
	if choices.WantSage && strings.EqualFold(choices.HW.Vendor, "NVIDIA") {
		var cuTag string
		pinTorch, cuTag = torchPlanForSage(cfg.Python.DisplayName, cudaTarget)
		log(logf, "Using Torch "+pinTorch+" with "+cuTag+" for the SageAttention install plan.")
	}
	if err := validatePythonVersion(venv.Python, choices.HW, logf); err != nil {
		return err
	}
	if err := torch.Install(ctx, venv.Env, choices.HW, cudaTarget, torch.CUDAConfig{Global: cfg.CUDA.Global, MinCUDAFor50x: cfg.CUDA.MinCUDAFor50x}, pinTorch, logf); err != nil {
		return err
	}
	if err := runutil.Command(ctx, logf, comfyPath, venv.Env, "uv", "pip", "install", "-r", "requirements.txt"); err != nil {
		return err
	}
	if choices.WantFFmpeg {
		if err := ffmpeg.Install(ctx, comfyPath, cfg.URLs["ffmpeg_windows"], logf); err != nil {
			log(logf, "FFmpeg install error: "+err.Error())
		}
	}
	nodeLines, err := resolveNodeLines(cfg)
	if err != nil {
		log(logf, "Could not fetch remote node list: "+err.Error())
	}
	stats := nodes.Sync(ctx, venv.Env, nodeLines, comfyPath, logf)
	log(logf, fmt.Sprintf("Custom nodes: %d ok, %d failed, %d skipped", stats.Success, len(stats.Failed), stats.Skipped))
	managerReq := filepath.Join(comfyPath, "manager_requirements.txt")
	if fileExists(managerReq) {
		_ = runutil.Command(ctx, logf, comfyPath, venv.Env, "uv", "pip", "install", "-r", managerReq)
	}
	_ = runutil.Command(ctx, logf, comfyPath, venv.Env, "uv", torch.PriorityInstallArgs(choices.WantSage, runtime.GOOS == "windows", pinTorch, choices.HW, cudaTarget)...)
	if err := torch.Reassert(ctx, venv.Env, venv.Python, choices.HW, cudaTarget, torch.CUDAConfig{Global: cfg.CUDA.Global, MinCUDAFor50x: cfg.CUDA.MinCUDAFor50x}, pinTorch, logf); err != nil {
		return err
	}
	if choices.WantSage {
		if err := sage.Install(ctx, venv.Env, comfyPath, cfg.URLs, logf); err != nil {
			return err
		}
	}
	if choices.WantRadial {
		if err := radial.Install(ctx, venv.Env, comfyPath, cfg.URLs, logf); err != nil {
			return err
		}
	}
	if choices.WantFlash {
		if err := flashattn.Install(ctx, venv.Env, comfyPath, cfg.URLs, logf); err != nil {
			log(logf, "FlashAttention install error: "+err.Error())
		}
	}
	if err := launcher.Create(comfyPath); err != nil {
		return err
	}
	log(logf, "Native Go install flow complete.")
	return nil
}

func loadConfig(root string, choices Choices) (Config, error) {
	data, err := appconfig.LoadMergedJSONWithFallback(root, installer.Files)
	if err != nil {
		return Config{}, err
	}
	data, err = appconfig.MergeJSONBytes(data, choices.ConfigOverrides)
	if err != nil {
		return Config{}, err
	}
	var cfg Config
	if err := json.Unmarshal(data, &cfg); err != nil {
		return Config{}, err
	}
	if cfg.URLs == nil {
		cfg.URLs = map[string]string{}
	}
	return cfg, nil
}

func selectedDownloads(items []downloader.Item, choices Choices, comfyPath string) []downloader.Item {
	if strings.EqualFold(choices.Downloads, "all") {
		return downloader.FilterMissing(items, comfyPath)
	}
	var requested []downloader.Item
	for _, index := range choices.DownloadIndices {
		if index >= 0 && index < len(items) {
			requested = append(requested, items[index])
		}
	}
	if len(requested) > 0 {
		return downloader.FilterMissing(requested, comfyPath)
	}
	wanted := map[string]struct{}{}
	for _, name := range choices.DownloadNames {
		wanted[name] = struct{}{}
	}
	for _, item := range items {
		if _, ok := wanted[item.Name]; ok {
			requested = append(requested, item)
		}
	}
	return downloader.FilterMissing(requested, comfyPath)
}

func resolveComfyPath(root, selected string) string {
	return comfypath.Resolve(root, selected)
}

func resolveNodeLines(cfg Config) ([]string, error) {
	if cfg.URLs["custom_nodes"] != "" {
		return nodes.FetchList(cfg.URLs["custom_nodes"])
	}
	return cfg.CustomNodes, nil
}

func fileExists(path string) bool { _, err := os.Stat(path); return err == nil }
func torchPlanForSage(pythonDisplay, cudaTarget string) (string, string) {
	return sage.PlanWindowsTorch(pythonDisplay, cudaTarget)
}
func log(logf runutil.LogFunc, line string) {
	if logf != nil {
		logf(line)
	}
}
