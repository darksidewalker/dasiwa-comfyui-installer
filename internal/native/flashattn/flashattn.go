package flashattn

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/cudahost"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/runutil"
)

const (
	packageName            = "flash_attn"
	pypiName               = "flash-attn"
	defaultReleaseVersion  = "2.8.3"
	prebuildReleasesAPI    = "https://api.github.com/repos/mjun0812/flash-attention-prebuild-wheels/releases?per_page=100"
	minBuildMemoryBytes    = 96 * 1024 * 1024 * 1024 // 96 GiB
)

type TorchInfo struct {
	Torch     string
	CUDA      string
	PythonTag string
	Platform  string
	CXX11ABI  string
	Archs     []string
}

func IsInstalled(ctx context.Context, python string) bool {
	_, err := runutil.Output(ctx, "", os.Environ(), python, "-c", "import flash_attn; print(flash_attn.__version__)")
	return err == nil
}

// Install attempts to install flash-attn into the ComfyUI venv.
// Linux-only: returns nil (no-op) on non-Linux platforms with a log message.
func Install(ctx context.Context, env []string, comfyPath string, urls map[string]string, logf runutil.LogFunc) error {
	if runtime.GOOS != "linux" {
		log(logf, "Skipping FlashAttention: only supported on Linux (no Windows wheels available).")
		return nil
	}

	venv := runutil.EnvWithVenv(comfyPath, env)
	if _, err := os.Stat(venv.Python); err != nil {
		return fmt.Errorf("could not find venv Python at %s", venv.Python)
	}
	if IsInstalled(ctx, venv.Python) {
		log(logf, "FlashAttention already installed; skipping.")
		return nil
	}

	// Allow overriding wheel URL via environment variable.
	if wheelURL := os.Getenv("DASIWA_FLASH_ATTN_WHEEL_URL"); wheelURL != "" {
		log(logf, "Installing FlashAttention from env URL: "+wheelURL)
		if err := installWheel(ctx, venv, wheelURL, logf); err != nil {
			return fmt.Errorf("flash-attn wheel install from env URL failed: %w", err)
		}
		return nil
	}

	info, err := probeTorch(ctx, venv.Python)
	if err != nil {
		log(logf, "Could not probe Torch/CUDA for FlashAttention wheel matching: "+err.Error())
		log(logf, "Falling back to PyPI binary-only install...")
		return installFromPyPI(ctx, venv, logf)
	}
	if info.CUDA == "" {
		return errors.New("torch is CPU-only; FlashAttention requires CUDA")
	}

	// Strategy 1: Official Dao-AILab release wheel
	log(logf, "Strategy 1: checking official FlashAttention release wheels...")
	if err := tryOfficialWheel(ctx, venv, info, logf); err == nil {
		return nil
	} else {
		log(logf, "Official wheel not available: "+err.Error())
	}

	// Strategy 2: Community prebuilt wheels (mjun0812)
	log(logf, "Strategy 2: checking community prebuilt wheels...")
	if err := tryPrebuiltWheel(ctx, venv, info, logf); err == nil {
		return nil
	} else {
		log(logf, "Community prebuilt not available: "+err.Error())
	}

	// Strategy 3: PyPI binary-only
	log(logf, "Strategy 3: trying PyPI binary-only install...")
	if err := installFromPyPI(ctx, venv, logf); err == nil {
		return nil
	} else {
		log(logf, "PyPI binary install failed: "+err.Error())
	}

	// Strategy 4: Source build (only if enough memory and compilers)
	log(logf, "Strategy 4: attempting source build...")
	return trySourceBuild(ctx, venv, comfyPath, urls, logf)
}

func installWheel(ctx context.Context, venv runutil.Venv, wheelURL string, logf runutil.LogFunc) error {
	installEnv := runutil.SetEnv(venv.Env, "UV_SKIP_WHEEL_FILENAME_CHECK", "1")
	if err := runutil.Command(ctx, logf, "", installEnv, "uv", "pip", "install", "--force-reinstall", "--no-cache", "--no-deps", "--python", venv.Python, wheelURL); err != nil {
		return err
	}
	return nil
}

func installFromPyPI(ctx context.Context, venv runutil.Venv, logf runutil.LogFunc) error {
	version := getFlashAttentionVersion(logf)
	spec := pypiName + "==" + version
	log(logf, "Installing "+spec+" from PyPI (binary only)...")
	if err := runutil.Command(ctx, logf, "", venv.Env, "uv", "pip", "install", "--only-binary", spec, "--python", venv.Python); err != nil {
		return err
	}
	if IsInstalled(ctx, venv.Python) {
		log(logf, "FlashAttention installed from PyPI.")
		return nil
	}
	// Try without version pin
	log(logf, "Versioned install failed; trying unpinned...")
	if err := runutil.Command(ctx, logf, "", venv.Env, "uv", "pip", "install", "--only-binary", pypiName, "--python", venv.Python); err != nil {
		return err
	}
	return nil
}

func tryOfficialWheel(ctx context.Context, venv runutil.Venv, info TorchInfo, logf runutil.LogFunc) error {
	version := getFlashAttentionVersion(logf)
	wheelURL, wheelName := officialWheelURL(version, info)
	log(logf, "Checking official wheel: "+wheelName)
	if !httpHeadExists(ctx, wheelURL) {
		return fmt.Errorf("official wheel not found at release URL")
	}
	log(logf, "Found official FlashAttention wheel: "+wheelName)
	return installWheel(ctx, venv, wheelURL, logf)
}

func tryPrebuiltWheel(ctx context.Context, venv runutil.Venv, info TorchInfo, logf runutil.LogFunc) error {
	candidate, err := findPrebuiltWheel(ctx, info)
	if err != nil {
		return err
	}
	log(logf, "Found prebuilt FlashAttention wheel: "+candidate.Name+" ("+candidate.Source+")")
	return installWheel(ctx, venv, candidate.URL, logf)
}

func trySourceBuild(ctx context.Context, venv runutil.Venv, comfyPath string, urls map[string]string, logf runutil.LogFunc) error {
	// Check memory
	memOK, memDetail, memErr := buildMemoryOK()
	if memErr != nil {
		log(logf, "Could not check system memory for FlashAttention source build: "+memErr.Error())
	} else if !memOK {
		log(logf, "Skipping FlashAttention source build: only "+memDetail+" available (need ~96 GiB for compilation).")
		return nil
	}

	// Check compilers
	if !cudahost.CheckNVCC(ctx) || !cudahost.CheckCPP() {
		log(logf, "Skipping FlashAttention source build: nvcc and g++/clang++ are required.")
		return nil
	}

	repoURL := urls["flash_attn_repo"]
	if repoURL == "" {
		repoURL = "https://github.com/Dao-AILab/flash-attention.git"
	}
	dir := filepath.Join(comfyPath, "flash-attention")
	if _, err := os.Stat(dir); os.IsNotExist(err) {
		if err := runutil.Command(ctx, logf, "", os.Environ(), "git", "clone", "--depth", "1", repoURL, dir); err != nil {
			return err
		}
	} else {
		_ = runutil.Command(ctx, logf, dir, os.Environ(), "git", "pull", "--ff-only")
	}

	buildEnv, res := cudahost.ApplyToEnv(ctx, venv.Env, logf)
	if res.Status == "incompatible" {
		log(logf, "Skipping FlashAttention source build: "+cudahost.Hint(res))
		return nil
	}

	version := getFlashAttentionVersion(logf)
	// Check out the specific version tag
	_ = runutil.Command(ctx, logf, dir, os.Environ(), "git", "checkout", "v"+version)

	buildEnv = runutil.SetEnv(buildEnv, "MAX_JOBS", envDefault("DASIWA_FLASH_MAX_JOBS", "2"))
	return runutil.Command(ctx, logf, dir, buildEnv, "uv", "pip", "install", "--no-build-isolation", "--python", venv.Python, ".")
}

// --- Torch probing ---

func probeTorch(ctx context.Context, python string) (TorchInfo, error) {
	script := `
import json, torch, sys, platform, os
cuda = torch.version.cuda or ""
torch_ver = torch.__version__.split("+")[0]
py_tag = "cp" + str(sys.version_info.major) + str(sys.version_info.minor)
plat = platform.platform(aliased=True)
cxx11abi = ""
try:
    cxx11abi = os.environ.get("_GLIBCXX_USE_CXX11_ABI", "0")
except:
    pass
archs = []
if hasattr(torch, "cuda") and torch.cuda.is_available():
    try:
        caps = torch.cuda.get_device_capability()
        archs = ["sm" + str(caps[0]*10+caps[1])]
    except:
        pass
info = {"cuda": cuda, "torch": torch_ver, "python_tag": py_tag, "platform": plat, "cxx11abi": cxx11abi, "archs": archs}
print(json.dumps(info))
`
	out, err := runutil.Output(ctx, "", os.Environ(), python, "-c", script)
	if err != nil {
		return TorchInfo{}, err
	}
	var raw struct {
		CUDA      string   `json:"cuda"`
		Torch     string   `json:"torch"`
		PythonTag string   `json:"python_tag"`
		Platform  string   `json:"platform"`
		CXX11ABI  string   `json:"cxx11abi"`
		Archs     []string `json:"archs"`
	}
	if err := json.Unmarshal([]byte(strings.TrimSpace(out)), &raw); err != nil {
		return TorchInfo{}, err
	}
	if raw.CUDA == "" || raw.Torch == "" || raw.PythonTag == "" || raw.Platform == "" {
		return TorchInfo{}, errors.New("incomplete Torch/CUDA info from probe")
	}
	return TorchInfo{
		Torch:     raw.Torch,
		CUDA:      raw.CUDA,
		PythonTag: raw.PythonTag,
		Platform:  raw.Platform,
		CXX11ABI:  raw.CXX11ABI,
		Archs:     raw.Archs,
	}, nil
}

// --- Wheel resolution ---

func officialWheelURL(version string, info TorchInfo) (string, string) {
	cudaMajor := strings.Split(info.CUDA, ".")[0]
	wheelName := fmt.Sprintf(
		"%s-%s+cu%storch%scxx11abi%s-%s-%s-%s.whl",
		packageName,
		version,
		cudaMajor,
		info.Torch,
		info.CXX11ABI,
		info.PythonTag,
		info.PythonTag,
		info.Platform,
	)
	url := fmt.Sprintf(
		"https://github.com/Dao-AILab/flash-attention/releases/download/v%s/%s",
		version,
		wheelName,
	)
	return url, wheelName
}

type wheelCandidate struct {
	Name string
	URL  string
	Source string
}

func findPrebuiltWheel(ctx context.Context, info TorchInfo) (wheelCandidate, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, prebuildReleasesAPI, nil)
	if err != nil {
		return wheelCandidate{}, err
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("User-Agent", "DaSiWa-Installer-Go/1.0")
	client := http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return wheelCandidate{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return wheelCandidate{}, fmt.Errorf("GitHub returned %s", resp.Status)
	}

	var releases []struct {
		TagName string `json:"tag_name"`
		Assets []struct {
			Name               string `json:"name"`
			BrowserDownloadURL string `json:"browser_download_url"`
		} `json:"assets"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&releases); err != nil {
		return wheelCandidate{}, err
	}

	var best wheelCandidate
	bestScore := -1
	for _, release := range releases {
		for _, asset := range release.Assets {
			if !matchesPrebuiltWheel(asset.Name, info) {
				continue
			}
			score := wheelScore(asset.Name)
			if score > bestScore {
				bestScore = score
				best = wheelCandidate{
					Name:   asset.Name,
					URL:    asset.BrowserDownloadURL,
					Source: "mjun0812/flash-attention-prebuild-wheels@" + release.TagName,
				}
			}
		}
	}
	if best.URL == "" {
		return wheelCandidate{}, errors.New("no matching prebuilt wheel found")
	}
	return best, nil
}

func matchesPrebuiltWheel(name string, info TorchInfo) bool {
	if !strings.HasPrefix(name, packageName+"-") || !strings.HasSuffix(name, ".whl") {
		return false
	}
	cudaLabel := "cu" + strings.ReplaceAll(info.CUDA, ".", "")
	if !strings.Contains(name, "+"+cudaLabel+"torch"+info.Torch+"-") {
		return false
	}
	if !strings.Contains(name, "-"+info.PythonTag+"-"+info.PythonTag+"-") && !strings.Contains(name, "-abi3-") {
		return false
	}
	return platformMatches(name, info.Platform)
}

func platformMatches(name, platform string) bool {
	switch {
	case strings.Contains(platform, "x86_64") || strings.Contains(platform, "amd64"):
		return strings.Contains(name, "x86_64") || strings.Contains(name, "amd64")
	case strings.Contains(platform, "aarch64") || strings.Contains(platform, "arm64"):
		return strings.Contains(name, "aarch64") || strings.Contains(name, "arm64")
	default:
		return strings.Contains(name, platform)
	}
}

func wheelScore(name string) int {
	score := 0
	if strings.Contains(name, "manylinux") {
		score += 100
	}
	// Prefer newer versions
	if strings.Contains(name, "2.8.3") {
		score += 30
	}
	if strings.Contains(name, "2.7.4") {
		score += 20
	}
	if strings.Contains(name, "2.6.3") {
		score += 10
	}
	return score
}

// --- Helpers ---

func getFlashAttentionVersion(logf runutil.LogFunc) string {
	if version := os.Getenv("DASIWA_FLASH_ATTN_VERSION"); version != "" {
		log(logf, "Using FlashAttention version from env: "+version)
		return version
	}
	version, err := latestPyPIVersion()
	if err != nil {
		log(logf, "Could not read latest FlashAttention from PyPI; using "+defaultReleaseVersion+": "+err.Error())
		return defaultReleaseVersion
	}
	return version
}

func latestPyPIVersion() (string, error) {
	client := http.Client{Timeout: 20 * time.Second}
	resp, err := client.Get("https://pypi.org/pypi/" + pypiName + "/json")
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", fmt.Errorf("PyPI returned %s", resp.Status)
	}
	var body struct {
		Info struct {
			Version string `json:"version"`
		} `json:"info"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return "", err
	}
	if body.Info.Version == "" {
		return "", errors.New("PyPI response missing info.version")
	}
	return body.Info.Version, nil
}

func httpHeadExists(ctx context.Context, url string) bool {
	req, err := http.NewRequestWithContext(ctx, http.MethodHead, url, nil)
	if err != nil {
		return false
	}
	req.Header.Set("User-Agent", "DaSiWa-Installer-Go/1.0")
	client := http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	return resp.StatusCode >= 200 && resp.StatusCode < 400
}

func buildMemoryOK() (bool, string, error) {
	data, err := os.ReadFile("/proc/meminfo")
	if err != nil {
		return false, "", err
	}
	values := map[string]uint64{}
	for _, line := range strings.Split(string(data), "\n") {
		fields := strings.Fields(line)
		if len(fields) < 2 {
			continue
		}
		key := strings.TrimSuffix(fields[0], ":")
		var value uint64
		if _, err := fmt.Sscanf(fields[1], "%d", &value); err != nil {
			continue
		}
		values[key] = value * 1024
	}
	available := values["MemAvailable"] + values["SwapFree"]
	if available == 0 {
		return false, "", errors.New("MemAvailable and SwapFree were not present")
	}
	return available >= minBuildMemoryBytes, humanBytes(available), nil
}

func humanBytes(value uint64) string {
	const gib = 1024 * 1024 * 1024
	if value >= gib {
		return fmt.Sprintf("%.1f GiB", float64(value)/float64(gib))
	}
	const mib = 1024 * 1024
	return fmt.Sprintf("%.1f MiB", float64(value)/float64(mib))
}

func envDefault(key, fallback string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return fallback
}

func log(logf runutil.LogFunc, line string) {
	if logf != nil {
		logf(line)
	}
}
