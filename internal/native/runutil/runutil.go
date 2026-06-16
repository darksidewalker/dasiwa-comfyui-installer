package runutil

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
)

type LogFunc func(string)

type Venv struct {
	Root      string
	BinDir    string
	Python    string
	Env       []string
	UVCommand string
}

func EnvWithVenv(comfyPath string, base []string) Venv {
	if base == nil {
		base = os.Environ()
	}
	binName := "bin"
	pythonName := "python"
	if runtime.GOOS == "windows" {
		binName = "Scripts"
		pythonName = "python.exe"
	}
	root := filepath.Join(comfyPath, "venv")
	binDir := filepath.Join(root, binName)
	env := SetEnv(base, "VIRTUAL_ENV", root)
	env = SetEnv(env, "PATH", binDir+string(os.PathListSeparator)+GetEnv(base, "PATH"))
	return Venv{
		Root:      root,
		BinDir:    binDir,
		Python:    filepath.Join(binDir, pythonName),
		Env:       env,
		UVCommand: "uv",
	}
}

func SetEnv(env []string, key, value string) []string {
	prefix := key + "="
	out := append([]string(nil), env...)
	for i, item := range out {
		if strings.HasPrefix(item, prefix) {
			out[i] = prefix + value
			return out
		}
	}
	return append(out, prefix+value)
}

func GetEnv(env []string, key string) string {
	prefix := key + "="
	for _, item := range env {
		if strings.HasPrefix(item, prefix) {
			return strings.TrimPrefix(item, prefix)
		}
	}
	return os.Getenv(key)
}

func Command(ctx context.Context, logf LogFunc, dir string, env []string, name string, args ...string) error {
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Dir = dir
	cmd.Env = env
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return err
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return err
	}
	if err := cmd.Start(); err != nil {
		return err
	}
	var wg sync.WaitGroup
	wg.Add(2)
	go stream(&wg, logf, stdout)
	go stream(&wg, logf, stderr)
	wg.Wait()
	if err := cmd.Wait(); err != nil {
		return fmt.Errorf("%s %s: %w", name, strings.Join(args, " "), err)
	}
	return nil
}

func Output(ctx context.Context, dir string, env []string, name string, args ...string) (string, error) {
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Dir = dir
	cmd.Env = env
	out, err := cmd.CombinedOutput()
	return string(out), err
}

func stream(wg *sync.WaitGroup, logf LogFunc, r io.Reader) {
	defer wg.Done()
	if logf == nil {
		_, _ = io.Copy(io.Discard, r)
		return
	}
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	for scanner.Scan() {
		logf(scanner.Text())
	}
	if err := scanner.Err(); err != nil {
		logf("stream error: " + err.Error())
	}
}
