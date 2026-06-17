package sage

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strconv"
	"strings"
	"time"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/cudahost"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/runutil"
)

var hardcodedWheels = map[string]string{
	"cu128": "https://github.com/woct0rdho/SageAttention/releases/download/v2.2.0-windows.post4/sageattention-2.2.0+cu128torch2.9.0andhigher.post4-cp39-abi3-win_amd64.whl",
	"cu130": "https://github.com/woct0rdho/SageAttention/releases/download/v2.2.0-windows.post4/sageattention-2.2.0+cu130torch2.9.0andhigher.post4-cp39-abi3-win_amd64.whl",
}

type TorchProbe struct {
	Version string
	CUDA    string
	Python  string
}

func IsInstalled(ctx context.Context, python string) bool {
	_, err := runutil.Output(ctx, "", os.Environ(), python, "-c", "import sageattention; print(getattr(sageattention, '__version__', 'ok'))")
	return err == nil
}

func PlanWindowsTorch(pythonDisplay, cudaTarget string) (string, string) {
	cuMM := cudaTarget
	parts := strings.Split(cudaTarget, ".")
	if len(parts) >= 2 {
		cuMM = parts[0] + "." + parts[1]
	}
	if strings.HasPrefix(cuMM, "13.") {
		cuMM = "12.8"
	}
	cuTag := "cu" + strings.ReplaceAll(cuMM, ".", "")
	pyMM := strings.Join(firstN(strings.Split(pythonDisplay, "."), 2), ".")
	fallback := map[string]string{
		"3.12|12.8": "2.9.1", "3.13|12.8": "2.9.1",
		"3.11|12.8": "2.9.1", "3.10|12.8": "2.9.1",
	}
	pin := fallback[pyMM+"|"+cuMM]
	if pin == "" {
		pin = "2.9.1"
	}
	return pin, cuTag
}

func Install(ctx context.Context, env []string, comfyPath string, urls map[string]string, logf runutil.LogFunc) error {
	venv := runutil.EnvWithVenv(comfyPath, env)
	if _, err := os.Stat(venv.Python); err != nil {
		return fmt.Errorf("could not find venv Python at %s", venv.Python)
	}
	if IsInstalled(ctx, venv.Python) {
		log(logf, "SageAttention already installed; skipping.")
		return nil
	}
	if runtime.GOOS == "windows" {
		return installWindows(ctx, venv, logf)
	}
	if err := tryHFInstall(ctx, venv, logf); err == nil {
		return nil
	} else {
		log(logf, fmt.Sprintf("Hugging Face wheel install failed or not available: %v. Falling back to source build...", err))
	}
	if !cudahost.CheckNVCC(ctx) || !cudahost.CheckCPP() {
		log(logf, "Skipping SageAttention source build: no compatible prebuilt wheel was available, and source builds require nvcc plus g++/clang++.")
		return nil
	}
	return sourceBuild(ctx, venv, comfyPath, urls, logf)
}

func installWindows(ctx context.Context, venv runutil.Venv, logf runutil.LogFunc) error {
	probe, err := ProbeTorch(ctx, venv.Python)
	if err != nil {
		return err
	}
	if compareVersion(probe.Version, "2.9.0") < 0 {
		return fmt.Errorf("torch %s is older than 2.9; Sage ABI3 wheel requires torch >= 2.9", probe.Version)
	}
	if probe.CUDA == "" {
		return errors.New("torch is CPU-only; CUDA support missing")
	}
	cuTag := "cu" + strings.ReplaceAll(probe.CUDA, ".", "")
	wheel, err := ResolveWheelURL(ctx, cuTag, logf)
	if err != nil {
		return err
	}
	installEnv := runutil.SetEnv(venv.Env, "UV_SKIP_WHEEL_FILENAME_CHECK", "1")
	log(logf, "Installing SageAttention wheel...")
	if err := runutil.Command(ctx, logf, "", installEnv, "uv", "pip", "install", "--force-reinstall", "--no-cache", "--no-deps", "--python", venv.Python, wheel); err != nil {
		return err
	}
	triton := TritonSpec(probe.Version)
	log(logf, "Installing "+triton+"...")
	_ = runutil.Command(ctx, logf, "", venv.Env, "uv", "pip", "install", "--no-cache", "--no-deps", "--python", venv.Python, triton)
	if !IsInstalled(ctx, venv.Python) {
		return errors.New("SageAttention installed but failed import verification")
	}
	return nil
}

func sourceBuild(ctx context.Context, venv runutil.Venv, comfyPath string, urls map[string]string, logf runutil.LogFunc) error {
	repoURL := urls["sage_repo"]
	if repoURL == "" {
		repoURL = "https://github.com/thu-ml/SageAttention.git"
	}
	dir := filepath.Join(comfyPath, "SageAttention")
	if _, err := os.Stat(dir); os.IsNotExist(err) {
		if err := runutil.Command(ctx, logf, "", os.Environ(), "git", "clone", "--depth", "1", repoURL, dir); err != nil {
			return err
		}
	} else {
		_ = runutil.Command(ctx, logf, dir, os.Environ(), "git", "pull", "--ff-only")
	}
	buildEnv, res := cudahost.ApplyToEnv(ctx, venv.Env, logf)
	if res.Status == "incompatible" {
		log(logf, "Skipping SageAttention source build: "+cudahost.Hint(res))
		return nil
	}
	buildEnv = runutil.SetEnv(buildEnv, "MAX_JOBS", envDefault("DASIWA_SAGE_MAX_JOBS", "2"))
	buildEnv = runutil.SetEnv(buildEnv, "EXT_PARALLEL", envDefault("DASIWA_SAGE_EXT_PARALLEL", "2"))
	buildEnv = runutil.SetEnv(buildEnv, "NVCC_APPEND_FLAGS", envDefault("DASIWA_SAGE_NVCC_THREADS", "--threads 4"))
	return runutil.Command(ctx, logf, dir, buildEnv, "uv", "pip", "install", "--no-build-isolation", "--python", venv.Python, ".")
}

func ProbeTorch(ctx context.Context, python string) (TorchProbe, error) {
	out, err := runutil.Output(ctx, "", os.Environ(), python, "-c", "import torch, sys; print(torch.__version__.split('+')[0]); print(torch.version.cuda or ''); print(f'{sys.version_info.major}.{sys.version_info.minor}')")
	if err != nil {
		return TorchProbe{}, err
	}
	lines := strings.Split(strings.TrimSpace(out), "\n")
	if len(lines) < 3 {
		return TorchProbe{}, errors.New("could not parse torch probe")
	}
	return TorchProbe{Version: strings.TrimSpace(lines[0]), CUDA: strings.TrimSpace(lines[1]), Python: strings.TrimSpace(lines[2])}, nil
}

func ResolveWheelURL(ctx context.Context, cuTag string, logf runutil.LogFunc) (string, error) {
	api := "https://api.github.com/repos/woct0rdho/SageAttention/releases?per_page=5"
	pat := regexp.MustCompile(`sageattention-.*\+` + regexp.QuoteMeta(cuTag) + `torch.*andhigher.*-cp39-abi3-win_amd64\.whl`)
	for attempt := 0; attempt < 3; attempt++ {
		var releases []struct {
			Assets []struct {
				Name               string `json:"name"`
				BrowserDownloadURL string `json:"browser_download_url"`
			} `json:"assets"`
		}
		if err := getJSON(ctx, api, &releases); err == nil {
			for _, rel := range releases {
				for _, asset := range rel.Assets {
					if pat.MatchString(asset.Name) && asset.BrowserDownloadURL != "" {
						return asset.BrowserDownloadURL, nil
					}
				}
			}
		}
		time.Sleep(time.Second)
	}
	if url := hardcodedWheels[cuTag]; url != "" {
		log(logf, "Using hardcoded SageAttention wheel for "+cuTag)
		return url, nil
	}
	return "", fmt.Errorf("no SageAttention wheel found for %s", cuTag)
}

func TritonSpec(torchVersion string) string {
	pairs := []struct {
		major, minor int
		spec         string
	}{{2, 12, "triton-windows>=3.7,<3.8"}, {2, 11, "triton-windows>=3.6,<3.7"}, {2, 10, "triton-windows>=3.6,<3.7"}, {2, 9, "triton-windows>=3.5,<3.6"}, {2, 8, "triton-windows>=3.4,<3.5"}, {2, 7, "triton-windows>=3.3,<3.4"}}
	parts := strings.Split(torchVersion, ".")
	maj, min := 0, 0
	if len(parts) > 0 {
		maj, _ = strconv.Atoi(parts[0])
	}
	if len(parts) > 1 {
		min, _ = strconv.Atoi(parts[1])
	}
	for _, p := range pairs {
		if maj > p.major || (maj == p.major && min >= p.minor) {
			return p.spec
		}
	}
	return "triton-windows"
}

func getJSON(ctx context.Context, rawURL string, out any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", "DaSiWa-Installer-Go/1.0")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("GitHub returned %s", resp.Status)
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

func compareVersion(a, b string) int {
	ap, bp := strings.Split(a, "."), strings.Split(b, ".")
	for i := 0; i < 3; i++ {
		av, bv := 0, 0
		if i < len(ap) {
			av, _ = strconv.Atoi(numPrefix(ap[i]))
		}
		if i < len(bp) {
			bv, _ = strconv.Atoi(numPrefix(bp[i]))
		}
		if av < bv {
			return -1
		}
		if av > bv {
			return 1
		}
	}
	return 0
}
func numPrefix(s string) string {
	out := ""
	for _, r := range s {
		if r < '0' || r > '9' {
			break
		}
		out += string(r)
	}
	return out
}
func firstN(in []string, n int) []string {
	if len(in) < n {
		return in
	}
	return in[:n]
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

func tryHFInstall(ctx context.Context, venv runutil.Venv, logf runutil.LogFunc) error {
	log(logf, "Attempting to install SageAttention from Hugging Face precompiled wheels...")
	probe, err := ProbeTorch(ctx, venv.Python)
	if err != nil {
		return fmt.Errorf("failed to probe torch: %w", err)
	}
	if err := checkHFCompatibility(probe, runtime.GOOS); err != nil {
		return err
	}
	wheelURL, err := ResolveHFWheel(ctx, probe.Python, runtime.GOOS)
	if err != nil {
		return err
	}
	log(logf, "Found precompiled wheel: "+wheelURL)
	installEnv := runutil.SetEnv(venv.Env, "UV_SKIP_WHEEL_FILENAME_CHECK", "1")
	log(logf, "Installing Hugging Face SageAttention wheel...")
	if err := runutil.Command(ctx, logf, "", installEnv, "uv", "pip", "install", "--force-reinstall", "--no-cache", "--no-deps", "--python", venv.Python, wheelURL); err != nil {
		return fmt.Errorf("failed to install wheel: %w", err)
	}
	if runtime.GOOS == "windows" {
		triton := TritonSpec(probe.Version)
		log(logf, "Installing "+triton+"...")
		_ = runutil.Command(ctx, logf, "", venv.Env, "uv", "pip", "install", "--no-cache", "--no-deps", "--python", venv.Python, triton)
	} else if runtime.GOOS == "linux" {
		log(logf, "Installing nvidia-cuda-runtime-cu12 for precompiled wheel compatibility...")
		_ = runutil.Command(ctx, logf, "", venv.Env, "uv", "pip", "install", "--no-cache", "--python", venv.Python, "nvidia-cuda-runtime-cu12")
	}
	if !IsInstalled(ctx, venv.Python) {
		// Uninstall it to leave env clean for fallback
		_ = runutil.Command(ctx, nil, "", venv.Env, "uv", "pip", "uninstall", "-y", "sageattention")
		return errors.New("SageAttention installed from Hugging Face wheel but failed import verification")
	}
	log(logf, "SageAttention successfully installed from Hugging Face precompiled wheel!")
	return nil
}

func checkHFCompatibility(probe TorchProbe, goos string) error {
	if probe.CUDA == "" {
		return errors.New("torch is CPU-only; CUDA support missing")
	}
	if goos == "linux" && cudaMajor(probe.CUDA) >= 13 {
		return fmt.Errorf("Hugging Face SageAttention wheels use CUDA 12 runtime dependencies; torch reports CUDA %s", probe.CUDA)
	}
	return nil
}

func cudaMajor(version string) int {
	parts := strings.Split(version, ".")
	if len(parts) == 0 {
		return 0
	}
	major, _ := strconv.Atoi(parts[0])
	return major
}

func ResolveHFWheel(ctx context.Context, pythonVersion, goos string) (string, error) {
	pyTag := "cp" + strings.ReplaceAll(pythonVersion, ".", "")
	osTag := ""
	if goos == "windows" {
		osTag = "win_amd64"
	} else if goos == "linux" {
		osTag = "linux_x86_64"
	} else {
		return "", errors.New("unsupported OS")
	}

	api := "https://huggingface.co/api/models/Kijai/PrecompiledWheels/tree/main"
	var files []struct {
		Type string `json:"type"`
		Path string `json:"path"`
	}

	if err := getJSON(ctx, api, &files); err != nil {
		return "", err
	}

	var bestPath string
	var bestVer string
	prefix := "sageattention-"
	suffix := "-" + pyTag + "-" + pyTag + "-" + osTag + ".whl"

	for _, f := range files {
		if f.Type == "file" && strings.HasPrefix(f.Path, prefix) && strings.HasSuffix(f.Path, suffix) {
			ver := f.Path[len(prefix) : len(f.Path)-len(suffix)]
			if compareVersion(ver, bestVer) > 0 {
				bestVer = ver
				bestPath = f.Path
			}
		}
	}

	if bestPath != "" {
		return "https://huggingface.co/Kijai/PrecompiledWheels/resolve/main/" + bestPath, nil
	}

	return "", fmt.Errorf("no Hugging Face wheel found for %s %s", pyTag, osTag)
}
