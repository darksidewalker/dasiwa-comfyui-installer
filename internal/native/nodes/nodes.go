package nodes

import (
	"bufio"
	"context"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/runutil"
)

type Stats struct {
	Total   int
	Success int
	Failed  []string
	Skipped int
}

type nodeSpec struct {
	URL     string
	ReqFile string
	IsPkg   bool
}

func Sync(ctx context.Context, env []string, lines []string, comfyPath string, logf runutil.LogFunc) Stats {
	stats := Stats{}
	nodesDir := filepath.Join(comfyPath, "custom_nodes")
	_ = os.MkdirAll(nodesDir, 0o755)
	var clean []string
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		clean = append(clean, line)
	}
	stats.Total = len(clean)
	gitEnv := runutil.SetEnv(env, "GIT_TERMINAL_PROMPT", "0")
	venvPython := filepath.Join(runutil.GetEnv(env, "VIRTUAL_ENV"), "bin", "python")
	if runtime.GOOS == "windows" {
		venvPython = filepath.Join(runutil.GetEnv(env, "VIRTUAL_ENV"), "Scripts", "python.exe")
	}
	for _, line := range clean {
		spec := ParseLine(line)
		if spec.URL == "" || strings.Contains(strings.ToLower(spec.URL), "comfyui-manager") {
			stats.Skipped++
			continue
		}
		name := repoName(spec.URL)
		if name == "" {
			stats.Skipped++
			continue
		}
		nodePath := filepath.Join(nodesDir, name)
		if err := syncOne(ctx, env, gitEnv, venvPython, nodePath, spec, name, logf); err != nil {
			log(logf, fmt.Sprintf("Error syncing node %s: %v", name, err))
			stats.Failed = append(stats.Failed, name)
			continue
		}
		stats.Success++
	}
	return stats
}

func FetchList(source string) ([]string, error) {
	if info, err := os.Stat(source); err == nil && !info.IsDir() {
		return readLines(source)
	}
	var lastErr error
	for attempt := 0; attempt < 3; attempt++ {
		req, err := http.NewRequest(http.MethodGet, source, nil)
		if err != nil {
			return nil, err
		}
		req.Header.Set("User-Agent", "DaSiWa-Installer-Go/1.0")
		resp, err := http.DefaultClient.Do(req)
		if err == nil && resp.StatusCode >= 200 && resp.StatusCode < 300 {
			defer resp.Body.Close()
			var lines []string
			scanner := bufio.NewScanner(resp.Body)
			for scanner.Scan() {
				lines = append(lines, scanner.Text())
			}
			return lines, scanner.Err()
		}
		if resp != nil {
			_ = resp.Body.Close()
			lastErr = fmt.Errorf("HTTP %s", resp.Status)
		} else {
			lastErr = err
		}
		time.Sleep(2 * time.Second)
	}
	return nil, lastErr
}

func ParseLine(line string) nodeSpec {
	parts := strings.Split(line, "|")
	spec := nodeSpec{URL: strings.TrimSpace(parts[0]), ReqFile: "requirements.txt"}
	for _, raw := range parts[1:] {
		flag := strings.TrimSpace(raw)
		low := strings.ToLower(flag)
		switch {
		case low == "pkg":
			spec.IsPkg = true
		case low == "sub":
			// clone is always recursive for compatibility
		case strings.HasPrefix(low, "req:"):
			spec.ReqFile = strings.TrimSpace(flag[4:])
			if spec.ReqFile == "" {
				spec.ReqFile = "requirements.txt"
			}
		}
	}
	return spec
}

func syncOne(ctx context.Context, env, gitEnv []string, venvPython, nodePath string, spec nodeSpec, name string, logf runutil.LogFunc) error {
	if _, err := os.Stat(nodePath); os.IsNotExist(err) {
		log(logf, "Cloning "+name+"...")
		if err := runutil.Command(ctx, logf, "", gitEnv, "git", "clone", "--recursive", spec.URL, nodePath); err != nil {
			return err
		}
	} else {
		log(logf, "Updating "+name+"...")
		if err := resetToOrigin(ctx, gitEnv, nodePath, spec.URL, logf); err != nil {
			return err
		}
	}
	reqPath := filepath.Join(nodePath, spec.ReqFile)
	if _, err := os.Stat(reqPath); err == nil {
		log(logf, "Installing deps via "+spec.ReqFile+"...")
		args := []string{"pip", "install", "--no-deps"}
		if spec.IsPkg {
			args = append(args, "--no-build-isolation", "-e", ".")
		}
		args = append(args, "-r", reqPath)
		if err := runutil.Command(ctx, logf, nodePath, env, "uv", args...); err != nil {
			return err
		}
	} else if spec.IsPkg {
		if err := runutil.Command(ctx, logf, nodePath, env, "uv", "pip", "install", "--no-build-isolation", "-e", "."); err != nil {
			return err
		}
	}
	installScript := filepath.Join(nodePath, "install.py")
	if _, err := os.Stat(installScript); err == nil {
		log(logf, "Running install.py for "+name+"...")
		if err := runutil.Command(ctx, logf, nodePath, env, venvPython, installScript); err != nil {
			return err
		}
	}
	return nil
}

func resetToOrigin(ctx context.Context, gitEnv []string, nodePath, remoteURL string, logf runutil.LogFunc) error {
	if err := runutil.Command(ctx, logf, nodePath, gitEnv, "git", "remote", "set-url", "origin", remoteURL); err != nil {
		return err
	}
	if err := runutil.Command(ctx, logf, nodePath, gitEnv, "git", "fetch", "--prune", "origin"); err != nil {
		return err
	}
	branch := remoteDefaultBranch(ctx, gitEnv, nodePath)
	log(logf, "Resetting managed node to "+branch+"...")
	if err := runutil.Command(ctx, logf, nodePath, gitEnv, "git", "reset", "--hard", branch); err != nil {
		return err
	}
	return runutil.Command(ctx, logf, nodePath, gitEnv, "git", "submodule", "update", "--init", "--recursive")
}

func remoteDefaultBranch(ctx context.Context, gitEnv []string, nodePath string) string {
	out, err := runutil.Output(ctx, nodePath, gitEnv, "git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
	if err == nil {
		branch := strings.TrimSpace(out)
		if branch != "" {
			return branch
		}
	}
	for _, branch := range []string{"origin/master", "origin/main"} {
		if err := runutil.Command(ctx, nil, nodePath, gitEnv, "git", "rev-parse", "--verify", branch); err == nil {
			return branch
		}
	}
	return "origin/master"
}

func readLines(path string) ([]string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	var lines []string
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		lines = append(lines, scanner.Text())
	}
	return lines, scanner.Err()
}

func repoName(rawURL string) string {
	parsed, err := url.Parse(rawURL)
	if err == nil && parsed.Path != "" {
		rawURL = parsed.Path
	}
	name := strings.TrimSuffix(filepath.Base(rawURL), ".git")
	return strings.TrimSpace(name)
}

func log(logf runutil.LogFunc, line string) {
	if logf != nil {
		logf(line)
	}
}
