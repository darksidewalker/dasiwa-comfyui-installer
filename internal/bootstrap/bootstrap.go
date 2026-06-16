package bootstrap

import (
	"archive/tar"
	"archive/zip"
	"compress/gzip"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
)

const uvLatestAPI = "https://api.github.com/repos/astral-sh/uv/releases/latest"

type PythonRunner struct {
	Python string
	Env    []string
}

type releaseAsset struct {
	Name string `json:"name"`
	URL  string `json:"browser_download_url"`
}

type releaseResponse struct {
	Assets []releaseAsset `json:"assets"`
}

func PreparePython(root, pythonVersion string, logf func(string)) (*PythonRunner, error) {
	if pythonVersion == "" {
		pythonVersion = "3.12"
	}
	stateDir := filepath.Join(root, ".dasiwa")
	binDir := filepath.Join(stateDir, "bin")
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		return nil, err
	}

	uvPath, err := ensureUV(binDir, logf)
	if err != nil {
		return nil, err
	}
	env := bootstrapEnv(root, binDir)

	logf(fmt.Sprintf("Ensuring Python %s via uv...", pythonVersion))
	if err := runLogged(logf, env, uvPath, "python", "install", "--managed-python", "--no-bin", pythonVersion); err != nil {
		return nil, err
	}

	pythonPath, err := outputLogged(env, uvPath, "python", "find", "--managed-python", pythonVersion)
	if err != nil {
		return nil, err
	}
	pythonPath = strings.TrimSpace(pythonPath)
	if pythonPath == "" {
		return nil, errors.New("uv did not return a Python interpreter path")
	}
	logf("Using Python: " + pythonPath)
	return &PythonRunner{Python: pythonPath, Env: env}, nil
}

func ensureUV(binDir string, logf func(string)) (string, error) {
	uvName := executableName("uv")
	localUV := filepath.Join(binDir, uvName)
	if fileExists(localUV) {
		logf("Using bundled uv: " + localUV)
		return localUV, nil
	}
	if path, err := exec.LookPath(uvName); err == nil {
		logf("Using uv from PATH: " + path)
		return path, nil
	}
	logf("uv not found; downloading a local uv binary...")
	if err := downloadUV(binDir); err != nil {
		return "", err
	}
	if !fileExists(localUV) {
		return "", errors.New("uv download completed but uv binary was not found")
	}
	return localUV, nil
}

func downloadUV(binDir string) error {
	asset, err := findUVAsset()
	if err != nil {
		return err
	}
	resp, err := http.Get(asset.URL)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("uv download failed: %s", resp.Status)
	}

	tmp, err := os.CreateTemp("", "uv-*"+archiveSuffix(asset.Name))
	if err != nil {
		return err
	}
	tmpPath := tmp.Name()
	defer os.Remove(tmpPath)
	if _, err := io.Copy(tmp, resp.Body); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}

	if strings.HasSuffix(asset.Name, ".zip") {
		return extractUVZip(tmpPath, binDir)
	}
	return extractUVTarGz(tmpPath, binDir)
}

func findUVAsset() (*releaseAsset, error) {
	req, err := http.NewRequest(http.MethodGet, uvLatestAPI, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "DaSiWa-Installer-App/1.0")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("GitHub API returned %s", resp.Status)
	}
	var release releaseResponse
	if err := json.NewDecoder(resp.Body).Decode(&release); err != nil {
		return nil, err
	}
	target := uvTargetToken()
	for _, asset := range release.Assets {
		name := asset.Name
		if strings.Contains(name, target) && (strings.HasSuffix(name, ".zip") || strings.HasSuffix(name, ".tar.gz")) {
			return &asset, nil
		}
	}
	return nil, fmt.Errorf("no uv release asset found for %s", target)
}

func uvTargetToken() string {
	arch := runtime.GOARCH
	if arch == "amd64" {
		arch = "x86_64"
	} else if arch == "arm64" {
		arch = "aarch64"
	}
	switch runtime.GOOS {
	case "windows":
		return arch + "-pc-windows-msvc"
	case "darwin":
		return arch + "-apple-darwin"
	default:
		return arch + "-unknown-linux-gnu"
	}
}

func extractUVZip(path, binDir string) error {
	reader, err := zip.OpenReader(path)
	if err != nil {
		return err
	}
	defer reader.Close()
	for _, file := range reader.File {
		if filepath.Base(file.Name) != executableName("uv") {
			continue
		}
		src, err := file.Open()
		if err != nil {
			return err
		}
		defer src.Close()
		return writeExecutable(filepath.Join(binDir, executableName("uv")), src)
	}
	return errors.New("uv executable not found in zip archive")
}

func extractUVTarGz(path, binDir string) error {
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()
	gz, err := gzip.NewReader(file)
	if err != nil {
		return err
	}
	defer gz.Close()
	tr := tar.NewReader(gz)
	for {
		header, err := tr.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return err
		}
		if header.Typeflag != tar.TypeReg || filepath.Base(header.Name) != executableName("uv") {
			continue
		}
		return writeExecutable(filepath.Join(binDir, executableName("uv")), tr)
	}
	return errors.New("uv executable not found in tar.gz archive")
}

func writeExecutable(path string, src io.Reader) error {
	tmp := path + ".tmp"
	out, err := os.OpenFile(tmp, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o755)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, src); err != nil {
		_ = out.Close()
		return err
	}
	if err := out.Close(); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

func runLogged(logf func(string), env []string, command string, args ...string) error {
	cmd := exec.Command(command, args...)
	cmd.Env = env
	output, err := cmd.CombinedOutput()
	if len(output) > 0 {
		for _, line := range strings.Split(strings.TrimRight(string(output), "\r\n"), "\n") {
			if line != "" {
				logf(line)
			}
		}
	}
	return err
}

func outputLogged(env []string, command string, args ...string) (string, error) {
	cmd := exec.Command(command, args...)
	cmd.Env = env
	output, err := cmd.CombinedOutput()
	return string(output), err
}

func bootstrapEnv(root, binDir string) []string {
	env := os.Environ()
	env = setEnv(env, "PATH", binDir+string(os.PathListSeparator)+os.Getenv("PATH"))
	env = setEnv(env, "UV_PYTHON_INSTALL_DIR", filepath.Join(root, ".dasiwa", "python"))
	env = setEnv(env, "UV_MANAGED_PYTHON", "1")
	env = setEnv(env, "UV_CACHE_DIR", filepath.Join(root, ".dasiwa", "uv-cache"))
	env = setEnv(env, "UV_TOOL_DIR", filepath.Join(root, ".dasiwa", "tools"))
	env = setEnv(env, "PYTHONUNBUFFERED", "1")
	return env
}

func setEnv(env []string, key, value string) []string {
	prefix := key + "="
	for i, item := range env {
		if strings.HasPrefix(item, prefix) {
			env[i] = prefix + value
			return env
		}
	}
	return append(env, prefix+value)
}

func executableName(name string) string {
	if runtime.GOOS == "windows" {
		return name + ".exe"
	}
	return name
}

func archiveSuffix(name string) string {
	if strings.HasSuffix(name, ".zip") {
		return ".zip"
	}
	return ".tar.gz"
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
