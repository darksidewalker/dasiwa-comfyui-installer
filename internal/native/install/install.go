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
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/flashattn"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/launcher"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/nodes"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/radial"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/runutil"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/sage"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/torch"
)

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

func Run(ctx context.Context, root string, choices Choices, logf runutil.LogFunc) error {
	var warnings []string
	cfg, err := loadConfig(root, choices)
	if err != nil {
		return err
	}
	comfyPath := resolveComfyPath(root, choices.ComfyPath)
	if (choices.WantSage || choices.WantRadial || choices.WantFlash) && !strings.EqualFold(strings.TrimSpace(choices.HW.Vendor), "NVIDIA") {
		return fmt.Errorf("SageAttention, RadialAttention and FlashAttention installer options require NVIDIA; disable them for %s", choices.HW.Vendor)
	}
	if plan := torch.PlanInstall(choices.HW, choices.CUDATarget, torch.CUDAConfig{Global: cfg.CUDA.Global, MinCUDAFor50x: cfg.CUDA.MinCUDAFor50x}, ""); plan.Err != nil {
		return plan.Err
	}
	if strings.EqualFold(strings.TrimSpace(choices.HW.Vendor), "AMD") {
		if err := validateAMDSelection(comfyPath, choices.InstallMode, cfg.Python.DisplayName); err != nil {
			return err
		}
		if err := validateAMDHost(ctx); err != nil {
			return err
		}
		log(logf, "AMD ROCm 10.0 selected. Windows requires AMD Adrenalin 26.8.1 or newer; Linux requires a compatible amdgpu driver and access to /dev/kfd and /dev/dri.")
	}
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
	venv, pythonVersion, err := prepareVenv(ctx, root, comfyPath, choices.InstallMode, cfg.Python.DisplayName, logf, bootstrap.PreparePythonAt)
	if err != nil {
		return err
	}
	cfg.Python.DisplayName = pythonVersion
	selected := selectedDownloads(cfg.OptionalDownloads, choices, comfyPath)
	if len(selected) > 0 {
		if err := downloader.InstallSelectedWithFS(selected, comfyPath, root, installer.Files, func(s string) { log(logf, s) }); err != nil {
			warnings = append(warnings, "Downloads: "+err.Error())
			log(logf, "WARNING: Download error: "+err.Error())
		}
	}
	cudaTarget := choices.CUDATarget
	if cudaTarget == "" {
		cudaTarget = cfg.CUDA.Global
	}
	pinTorch := ""
	if choices.WantSage && strings.EqualFold(choices.HW.Vendor, "NVIDIA") {
		var cuTag string
		pinTorch, cuTag = sageTorchPlan(choices.HW, cfg.Python.DisplayName, cudaTarget, torch.CUDAConfig{Global: cfg.CUDA.Global, MinCUDAFor50x: cfg.CUDA.MinCUDAFor50x})
		log(logf, "Using Torch "+pinTorch+" with "+cuTag+" for the SageAttention install plan.")
	}
	if strings.EqualFold(strings.TrimSpace(choices.HW.Vendor), "AMD") {
		if err := validateAMDABI(cfg.Python.DisplayName); err != nil {
			return err
		}
		venv.Env, err = torch.AMDDependencyEnv(venv.Env, comfyPath)
		if err != nil {
			return err
		}
	}
	if strings.EqualFold(strings.TrimSpace(choices.HW.Vendor), "NVIDIA") {
		// Metadata remains readable even when an old compiled extension cannot import.
		old, probeErr := runutil.Output(ctx, "", venv.Env, venv.Python, "-c", "import importlib.metadata as m\ntry: print(m.version('torch'))\nexcept m.PackageNotFoundError: print('')")
		if probeErr != nil {
			return fmt.Errorf("read Torch metadata before upgrade: %w", probeErr)
		}
		plan := torch.PlanInstall(choices.HW, cudaTarget, torch.CUDAConfig{Global: cfg.CUDA.Global, MinCUDAFor50x: cfg.CUDA.MinCUDAFor50x}, pinTorch)
		if args := attentionResetArgs(strings.TrimSpace(old), plan); len(args) > 0 {
			log(logf, "Torch ABI changes: removing existing SageAttention/FlashAttention before upgrade; selected extensions will be reinstalled.")
			if err := runutil.Command(ctx, logf, "", venv.Env, "uv", append(args, "--python", venv.Python)...); err != nil {
				return err
			}
		}
	}
	if err := torch.Install(ctx, venv.Env, choices.HW, cudaTarget, torch.CUDAConfig{Global: cfg.CUDA.Global, MinCUDAFor50x: cfg.CUDA.MinCUDAFor50x}, pinTorch, logf); err != nil {
		return err
	}
	if strings.EqualFold(strings.TrimSpace(choices.HW.Vendor), "AMD") {
		if err := torch.VerifyAMD(ctx, venv.Env, venv.Python, choices.HW, logf); err != nil {
			return err
		}
	}
	if err := runutil.Command(ctx, logf, comfyPath, venv.Env, "uv", "pip", "install", "-r", "requirements.txt"); err != nil {
		return err
	}
	if choices.WantFFmpeg {
		if err := ffmpeg.Install(ctx, comfyPath, cfg.URLs["ffmpeg_windows"], logf); err != nil {
			warnings = append(warnings, "FFmpeg: "+err.Error())
			log(logf, "WARNING: FFmpeg install error: "+err.Error())
		}
	}
	nodeLines, err := resolveNodeLines(cfg)
	if err != nil {
		warnings = append(warnings, "Remote node list: "+err.Error())
		log(logf, "WARNING: Could not fetch remote node list: "+err.Error())
	}
	stats := nodes.Sync(ctx, venv.Env, nodeLines, comfyPath, logf)
	warnings = append(warnings, stats.FailureDetails...)
	log(logf, fmt.Sprintf("Custom nodes: %d ok, %d failed, %d skipped", stats.Success, len(stats.Failed), stats.Skipped))
	managerReq := filepath.Join(comfyPath, "manager_requirements.txt")
	if fileExists(managerReq) {
		if err := runutil.Command(ctx, logf, comfyPath, venv.Env, "uv", "pip", "install", "-r", managerReq); err != nil {
			warnings = append(warnings, "Manager dependencies: "+err.Error())
			log(logf, "WARNING: Manager dependencies incomplete: "+err.Error())
		}
	}
	if err := runutil.Command(ctx, logf, comfyPath, venv.Env, "uv", torch.PriorityInstallArgs(choices.WantSage, runtime.GOOS == "windows", pinTorch, choices.HW, cudaTarget)...); err != nil {
		warnings = append(warnings, "Priority packages (including Triton where selected): "+err.Error())
		log(logf, "WARNING: Priority package installation incomplete: "+err.Error())
	}
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
			warnings = append(warnings, "FlashAttention: "+err.Error())
			log(logf, "WARNING: FlashAttention install error: "+err.Error())
		}
	}
	if strings.EqualFold(strings.TrimSpace(choices.HW.Vendor), "AMD") {
		if err := torch.VerifyAMD(ctx, venv.Env, venv.Python, choices.HW, logf); err != nil {
			return err
		}
	}
	if strings.EqualFold(strings.TrimSpace(choices.HW.Vendor), "NVIDIA") {
		plan := torch.PlanInstall(choices.HW, cudaTarget, torch.CUDAConfig{Global: cfg.CUDA.Global, MinCUDAFor50x: cfg.CUDA.MinCUDAFor50x}, pinTorch)
		if ok, detail := torch.CurrentInstallSatisfies(ctx, venv.Env, venv.Python, plan, pinTorch); !ok {
			return fmt.Errorf("final Torch backend verification failed: %s", detail)
		}
	}
	if err := launcher.Create(comfyPath); err != nil {
		return err
	}
	if len(warnings) > 0 {
		return &WarningsError{Details: warnings}
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
func log(logf runutil.LogFunc, line string) {
	if logf != nil {
		logf(line)
	}
}
