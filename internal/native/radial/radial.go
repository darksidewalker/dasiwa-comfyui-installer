package radial

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
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/sage"
)

const defaultSpargeRepo = "https://github.com/woct0rdho/SpargeAttn.git"
const defaultRadialNodeRepo = "https://github.com/woct0rdho/ComfyUI-RadialAttn.git"

var hardcodedSpargeWheels = map[string]string{
	"cu128": "https://github.com/woct0rdho/SpargeAttn/releases/download/v0.1.0-windows.post4/spas_sage_attn-0.1.0+cu128torch2.9.0andhigher.post4-cp39-abi3-win_amd64.whl",
	"cu130": "https://github.com/woct0rdho/SpargeAttn/releases/download/v0.1.0-windows.post4/spas_sage_attn-0.1.0+cu130torch2.9.0andhigher.post4-cp39-abi3-win_amd64.whl",
}

func IsKernelInstalled(ctx context.Context, python string) bool {
	_, err := runutil.Output(ctx, "", os.Environ(), python, "-c", "import spas_sage_attn")
	return err == nil
}

func IsNodeInstalled(comfyPath string) bool {
	_, err := os.Stat(filepath.Join(comfyPath, "custom_nodes", "ComfyUI-RadialAttn", "__init__.py"))
	return err == nil
}

func IsInstalled(ctx context.Context, python, comfyPath string) bool {
	return IsKernelInstalled(ctx, python) && IsNodeInstalled(comfyPath)
}

func Install(ctx context.Context, env []string, comfyPath string, urls map[string]string, logf runutil.LogFunc) error {
	venv := runutil.EnvWithVenv(comfyPath, env)
	if _, err := os.Stat(venv.Python); err != nil {
		return fmt.Errorf("could not find venv Python at %s", venv.Python)
	}
	if !IsKernelInstalled(ctx, venv.Python) {
		if runtime.GOOS == "windows" {
			if err := installSpargeWindows(ctx, venv, logf); err != nil {
				return err
			}
		} else {
			if !cudahost.CheckNVCC(ctx) || !cudahost.CheckCPP() {
				return errors.New("SpargeAttention source build requires nvcc and g++/clang++")
			}
			if err := installSpargeLinux(ctx, venv, comfyPath, urls, logf); err != nil {
				return err
			}
		}
	}
	return installRadialNode(ctx, env, comfyPath, urls, logf)
}

func installSpargeWindows(ctx context.Context, venv runutil.Venv, logf runutil.LogFunc) error {
	probe, err := sage.ProbeTorch(ctx, venv.Python)
	if err != nil {
		return err
	}
	if cmpVersion(probe.Version, "2.9.0") < 0 {
		return fmt.Errorf("torch %s is older than 2.9; SpargeAttention ABI3 wheel requires torch >= 2.9", probe.Version)
	}
	if probe.CUDA == "" {
		return errors.New("torch is CPU-only; CUDA support missing")
	}
	cuTag := "cu" + strings.ReplaceAll(probe.CUDA, ".", "")
	wheel, err := ResolveSpargeWheelURL(ctx, cuTag, logf)
	if err != nil {
		return err
	}
	installEnv := runutil.SetEnv(venv.Env, "UV_SKIP_WHEEL_FILENAME_CHECK", "1")
	if err := runutil.Command(ctx, logf, "", installEnv, "uv", "pip", "install", "--force-reinstall", "--no-deps", "--no-cache", "--python", venv.Python, wheel); err != nil {
		return err
	}
	if !IsKernelInstalled(ctx, venv.Python) {
		return errors.New("SpargeAttention installed but failed import verification")
	}
	return nil
}

func installSpargeLinux(ctx context.Context, venv runutil.Venv, comfyPath string, urls map[string]string, logf runutil.LogFunc) error {
	repoURL := urls["sparge_repo"]
	if repoURL == "" {
		repoURL = defaultSpargeRepo
	}
	dir := filepath.Join(comfyPath, "SpargeAttn")
	if _, err := os.Stat(dir); os.IsNotExist(err) {
		if err := runutil.Command(ctx, logf, "", os.Environ(), "git", "clone", "--depth", "1", repoURL, dir); err != nil {
			return err
		}
	} else {
		_ = runutil.Command(ctx, logf, dir, os.Environ(), "git", "pull", "--ff-only")
	}
	buildEnv, res := cudahost.ApplyToEnv(ctx, venv.Env, logf)
	if res.Status == "incompatible" {
		return errors.New(cudahost.Hint(res))
	}
	return runutil.Command(ctx, logf, dir, buildEnv, "uv", "pip", "install", "--no-build-isolation", "--python", venv.Python, ".")
}

func installRadialNode(ctx context.Context, env []string, comfyPath string, urls map[string]string, logf runutil.LogFunc) error {
	if IsNodeInstalled(comfyPath) {
		log(logf, "ComfyUI-RadialAttn already cloned.")
		return nil
	}
	repoURL := urls["radial_node_repo"]
	if repoURL == "" {
		repoURL = defaultRadialNodeRepo
	}
	nodesDir := filepath.Join(comfyPath, "custom_nodes")
	_ = os.MkdirAll(nodesDir, 0o755)
	nodeDir := filepath.Join(nodesDir, "ComfyUI-RadialAttn")
	gitEnv := runutil.SetEnv(env, "GIT_TERMINAL_PROMPT", "0")
	return runutil.Command(ctx, logf, "", gitEnv, "git", "clone", repoURL, nodeDir)
}

func ResolveSpargeWheelURL(ctx context.Context, cuTag string, logf runutil.LogFunc) (string, error) {
	api := "https://api.github.com/repos/woct0rdho/SpargeAttn/releases?per_page=5"
	pat := regexp.MustCompile(`spas_sage_attn-.*\+` + regexp.QuoteMeta(cuTag) + `torch.*andhigher.*-cp39-abi3-win_amd64\.whl`)
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
	if url := hardcodedSpargeWheels[cuTag]; url != "" {
		log(logf, "Using hardcoded SpargeAttention wheel for "+cuTag)
		return url, nil
	}
	return "", fmt.Errorf("no SpargeAttention wheel found for %s", cuTag)
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

func cmpVersion(a, b string) int {
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
func log(logf runutil.LogFunc, line string) {
	if logf != nil {
		logf(line)
	}
}
