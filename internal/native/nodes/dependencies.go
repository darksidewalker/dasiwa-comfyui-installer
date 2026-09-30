package nodes

import (
	"context"
	"fmt"
	"os"
	"regexp"
	"strings"
	"sync"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/runutil"
)

var llamaRequirement = regexp.MustCompile(`(?i)^llama[-_]cpp[-_]python\b`)
var cudaVersion = regexp.MustCompile(`^[0-9]+\.[0-9]+$`)

func llamaIndex(cuda string) (string, error) {
	cuda = strings.TrimSpace(cuda)
	tag := "cpu"
	if cuda != "" {
		if !cudaVersion.MatchString(cuda) {
			return "", fmt.Errorf("invalid Torch CUDA version %q", cuda)
		}
		tag = "cu" + strings.ReplaceAll(cuda, ".", "")
	}
	return "https://abetlen.github.io/llama-cpp-python/whl/" + tag, nil
}

// Install this native dependency separately so its runtime dependencies are
// resolved despite the deliberately --no-deps bulk node install.
func prepareLlama(ctx context.Context, env []string, python, reqPath string, logf runutil.LogFunc) error {
	data, err := os.ReadFile(reqPath)
	if err != nil {
		return err
	}
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(strings.SplitN(line, "#", 2)[0])
		if !llamaRequirement.MatchString(line) {
			continue
		}
		cuda, err := runutil.Output(ctx, "", env, python, "-c", "import torch; print(torch.version.cuda or '')")
		if err != nil {
			return fmt.Errorf("cannot select llama-cpp-python wheel: Torch CUDA probe failed: %s: %w", strings.TrimSpace(cuda), err)
		}
		index, err := llamaIndex(cuda)
		if err != nil {
			return err
		}
		log(logf, "Installing llama-cpp-python binary wheel from "+index+" (Python/platform compatibility checked by uv; no source build)...")
		args := []string{"pip", "install", "--python", python, "--only-binary", "llama-cpp-python", "--reinstall-package", "llama-cpp-python", "--index", index, line}
		if err := runutil.Command(ctx, logf, "", env, "uv", args...); err != nil {
			return fmt.Errorf("llama-cpp-python wheel installation from %s did not complete; requires a wheel matching the requirement, Python, OS/architecture, Linux glibc and Torch CUDA backend. No compiler build or CPU fallback was attempted: %w", index, err)
		}
	}
	return nil
}

type dependencyLog struct {
	mu   sync.Mutex
	text string
}

func (d *dependencyLog) capture(logf runutil.LogFunc) runutil.LogFunc {
	return func(line string) {
		d.mu.Lock()
		d.text += line + "\n"
		if len(d.text) > 32768 {
			d.text = d.text[len(d.text)-32768:]
		}
		d.mu.Unlock()
		log(logf, line)
	}
}

func dependencyFailure(output string) string {
	lower := strings.ToLower(output)
	var details []string
	for _, line := range strings.Split(output, "\n") {
		low := strings.ToLower(line)
		if strings.Contains(low, "failed to build") || strings.Contains(low, "failed to download") ||
			strings.Contains(low, "fatal error:") || strings.Contains(low, "error:") ||
			strings.Contains(low, "could not find") || strings.Contains(low, "no solution found") ||
			strings.Contains(low, "no module named") || strings.Contains(low, "microsoft visual c++") {
			details = append(details, strings.TrimSpace(line))
		}
	}
	if strings.Contains(lower, "nmake") && (strings.Contains(lower, "no such file") || strings.Contains(lower, "not found")) {
		details = append(details, "Missing build tool: nmake (not found in the build environment).")
	}
	if strings.Contains(lower, "cmake_c_compiler not set") {
		details = append(details, "Missing C compiler: CMAKE_C_COMPILER is not set.")
	}
	if strings.Contains(lower, "cmake_cxx_compiler not set") {
		details = append(details, "Missing C++ compiler: CMAKE_CXX_COMPILER is not set.")
	}
	if len(details) == 0 {
		return "See the preceding build/resolver output for the exact cause; no missing tool could be identified reliably."
	}
	return strings.Join(details, " ")
}
