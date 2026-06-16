package cudahost

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/runutil"
)

type CUDAVersion struct{ Major, Minor int }

type Resolution struct {
	Status       string // ok | override | incompatible
	GCCPath      string
	GXXPath      string
	DefaultMajor int
	MaxMajor     int
	CUDA         CUDAVersion
}

var cudaMaxGCC = map[CUDAVersion]int{
	{11, 0}: 9, {11, 1}: 10, {11, 4}: 11,
	{12, 0}: 12, {12, 4}: 13, {12, 8}: 14,
	{13, 0}: 15, {13, 1}: 15, {13, 2}: 15, {13, 3}: 15,
}

func MaxGCCForCUDA(cuda CUDAVersion) (int, bool) {
	best := CUDAVersion{}
	ok := false
	for candidate := range cudaMaxGCC {
		if lessEq(candidate, cuda) && (!ok || lessEq(best, candidate)) {
			best = candidate
			ok = true
		}
	}
	if !ok {
		return 0, false
	}
	return cudaMaxGCC[best], true
}

func ProbeNVCC(ctx context.Context) (CUDAVersion, bool) {
	out, err := runutil.Output(ctx, "", os.Environ(), "nvcc", "--version")
	if err != nil {
		return CUDAVersion{}, false
	}
	re := regexp.MustCompile(`release\s+(\d+)\.(\d+)`)
	m := re.FindStringSubmatch(out)
	if len(m) != 3 {
		return CUDAVersion{}, false
	}
	major, _ := strconv.Atoi(m[1])
	minor, _ := strconv.Atoi(m[2])
	return CUDAVersion{major, minor}, true
}

func ProbeGCCMajor(ctx context.Context, executable string) (int, bool) {
	out, err := runutil.Output(ctx, "", os.Environ(), executable, "-dumpfullversion", "-dumpversion")
	if err != nil {
		return 0, false
	}
	for _, line := range strings.Split(out, "\n") {
		line = strings.TrimSpace(line)
		if line == "" || line[0] < '0' || line[0] > '9' {
			continue
		}
		major, err := strconv.Atoi(strings.Split(line, ".")[0])
		if err == nil {
			return major, true
		}
	}
	return 0, false
}

func Resolve(ctx context.Context, logf runutil.LogFunc) Resolution {
	return ResolveWithEnv(ctx, os.Environ(), logf)
}

func ResolveWithEnv(ctx context.Context, env []string, logf runutil.LogFunc) Resolution {
	cuda, ok := ProbeNVCC(ctx)
	if !ok {
		return Resolution{Status: "ok"}
	}
	maxGCC, ok := MaxGCCForCUDA(cuda)
	if !ok {
		return Resolution{Status: "ok", CUDA: cuda}
	}
	limit := maxGCC
	if limit > 14 {
		limit = 14 // PyTorch headers are incompatible with GCC 15+ template compilation rules
	}
	defaultMajor, ok := ProbeGCCMajor(ctx, "g++")
	if !ok || defaultMajor <= limit {
		return Resolution{Status: "ok", CUDA: cuda, DefaultMajor: defaultMajor, MaxMajor: limit}
	}
	log(logf, fmt.Sprintf("Default g++ is %d; CUDA %d.%d supports up to GCC %d, capped at GCC %d for PyTorch extension compatibility. Searching compatible compiler...", defaultMajor, cuda.Major, cuda.Minor, maxGCC, limit))
	if cc, cxx := requestedCompiler(env); cxx != "" {
		if probed, ok := ProbeGCCMajor(ctx, cxx); ok && probed <= limit {
			if cc == "" {
				cc = inferCC(cxx)
			}
			log(logf, fmt.Sprintf("Using requested CXX %s with GCC-compatible major %d.", cxx, probed))
			return Resolution{Status: "override", GCCPath: cc, GXXPath: cxx, CUDA: cuda, DefaultMajor: defaultMajor, MaxMajor: limit}
		}
		log(logf, "Requested CXX "+cxx+" is not compatible with this CUDA/PyTorch build.")
	}
	for major := limit; major > 10; major-- {
		gcc, gccErr := exec.LookPath(fmt.Sprintf("gcc-%d", major))
		gxx, gxxErr := exec.LookPath(fmt.Sprintf("g++-%d", major))
		if gccErr == nil && gxxErr == nil {
			if probed, ok := ProbeGCCMajor(ctx, gxx); ok && probed == major {
				return Resolution{Status: "override", GCCPath: gcc, GXXPath: gxx, CUDA: cuda, DefaultMajor: defaultMajor, MaxMajor: limit}
			}
		}
	}
	return Resolution{Status: "incompatible", CUDA: cuda, DefaultMajor: defaultMajor, MaxMajor: limit}
}

func ApplyToEnv(ctx context.Context, env []string, logf runutil.LogFunc) ([]string, Resolution) {
	res := ResolveWithEnv(ctx, env, logf)
	if res.Status == "override" {
		env = runutil.SetEnv(env, "CC", res.GCCPath)
		env = runutil.SetEnv(env, "CXX", res.GXXPath)
		env = runutil.SetEnv(env, "NVCC_CCBIN", res.GXXPath)
		log(logf, "Using "+res.GXXPath+" as nvcc host compiler.")
	}
	return env, res
}

func Hint(res Resolution) string {
	if res.Status != "incompatible" {
		return ""
	}
	return fmt.Sprintf("No compatible host C++ compiler found. Default g++ is %d; CUDA %d.%d supports up to GCC %d. Install gcc-%d and g++-%d, or set CC/CXX/NVCC_CCBIN to a compatible compiler, then rerun.", res.DefaultMajor, res.CUDA.Major, res.CUDA.Minor, res.MaxMajor, res.MaxMajor, res.MaxMajor)
}

func CheckNVCC(ctx context.Context) bool {
	if _, ok := ProbeNVCC(ctx); ok {
		return true
	}
	for _, key := range []string{"CUDA_HOME", "CUDA_PATH"} {
		if root := os.Getenv(key); root != "" {
			if _, err := os.Stat(root + string(os.PathSeparator) + "bin" + string(os.PathSeparator) + exe("nvcc")); err == nil {
				return true
			}
		}
	}
	for _, path := range []string{"/opt/cuda/bin/nvcc", "/usr/local/cuda/bin/nvcc"} {
		if _, err := os.Stat(path); err == nil {
			return true
		}
	}
	return false
}

func CheckCPP() bool {
	for _, compiler := range []string{"g++", "clang++"} {
		if _, err := exec.LookPath(compiler); err == nil {
			return true
		}
	}
	return false
}

func lessEq(a, b CUDAVersion) bool {
	return a.Major < b.Major || (a.Major == b.Major && a.Minor <= b.Minor)
}

func requestedCompiler(env []string) (string, string) {
	cc := runutil.GetEnv(env, "CC")
	cxx := runutil.GetEnv(env, "NVCC_CCBIN")
	if cxx == "" {
		cxx = runutil.GetEnv(env, "CXX")
	}
	return cc, cxx
}

func inferCC(cxx string) string {
	base := filepath.Base(cxx)
	dir := filepath.Dir(cxx)
	switch {
	case strings.HasPrefix(base, "g++"):
		return filepath.Join(dir, "gcc"+strings.TrimPrefix(base, "g++"))
	case strings.HasPrefix(base, "clang++"):
		return filepath.Join(dir, "clang"+strings.TrimPrefix(base, "clang++"))
	default:
		return strings.TrimSuffix(cxx, "++")
	}
}

func exe(name string) string {
	if os.PathSeparator == '\\' {
		return name + ".exe"
	}
	return name
}

func log(logf runutil.LogFunc, line string) {
	if logf != nil {
		logf(line)
	}
}
