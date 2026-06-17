package main

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/torch"
)

type target struct {
	GOOS   string
	GOARCH string
	Name   string
}

type cudaMigrationCase struct {
	Name          string
	HW            torch.Hardware
	WantBackend   string
	WantCUDA      string
	WantIndexPart string
}

var defaultTargets = []target{
	{GOOS: "windows", GOARCH: "amd64", Name: "dasiwa-installer-windows-amd64.exe"},
	{GOOS: "linux", GOARCH: "amd64", Name: "dasiwa-installer-linux-amd64"},
}

func main() {
	version := flag.String("version", "dev", "version string embedded into the installer app")
	outDir := flag.String("out", "dist", "output directory")
	currentOnly := flag.Bool("current", false, "build only for the current GOOS/GOARCH")
	checkCUDA := flag.String("check-cuda-migration", "13.2", "candidate CUDA target to verify before release; empty disables the check")
	flag.Parse()

	rootDir, err := repoRoot()
	if err != nil {
		fatal(err)
	}
	outputDir := *outDir
	if !filepath.IsAbs(outputDir) {
		outputDir = filepath.Join(rootDir, outputDir)
	}

	if *checkCUDA != "" {
		if err := checkCUDAMigration(*checkCUDA); err != nil {
			fatal(err)
		}
	}

	targets := defaultTargets
	if *currentOnly {
		name := fmt.Sprintf("dasiwa-installer-%s-%s", runtime.GOOS, runtime.GOARCH)
		if runtime.GOOS == "windows" {
			name += ".exe"
		}
		targets = []target{{GOOS: runtime.GOOS, GOARCH: runtime.GOARCH, Name: name}}
	}

	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		fatal(err)
	}
	for _, target := range targets {
		if err := build(target, *version, rootDir, outputDir); err != nil {
			fatal(err)
		}
	}
}

func checkCUDAMigration(candidate string) error {
	candidate = strings.TrimSpace(candidate)
	if candidate == "" {
		return nil
	}
	cfg := torch.CUDAConfig{Global: candidate, MinCUDAFor50x: candidate}
	nvidiaCUDA := candidate
	if strings.HasPrefix(nvidiaCUDA, "13.") {
		nvidiaCUDA = "12.8"
	}
	cuTag := "cu" + strings.ReplaceAll(nvidiaCUDA, ".", "")
	cases := []cudaMigrationCase{
		{Name: "AMD RDNA2/ROCm stable", HW: torch.Hardware{Vendor: "AMD", Name: "Radeon RX 6800 XT"}, WantBackend: "rocm", WantIndexPart: "rocm"},
		{Name: "AMD RDNA3/GFX110 nightly", HW: torch.Hardware{Vendor: "AMD", Name: "Radeon RX 7900 XTX GFX1100"}, WantBackend: "rocm", WantIndexPart: "gfx110X-all"},
		{Name: "AMD RDNA3.5/GFX1151 nightly", HW: torch.Hardware{Vendor: "AMD", Name: "Radeon 8060S GFX1151 Strix"}, WantBackend: "rocm", WantIndexPart: "gfx1151"},
		{Name: "AMD RDNA4/GFX120 nightly", HW: torch.Hardware{Vendor: "AMD", Name: "Radeon RX 9070 XT GFX1201"}, WantBackend: "rocm", WantIndexPart: "gfx120X-all"},
		{Name: "Intel Arc/XPU", HW: torch.Hardware{Vendor: "INTEL", Name: "Intel Arc B580"}, WantBackend: "xpu", WantIndexPart: "/xpu"},
		{Name: "NVIDIA GTX 10/Pascal legacy", HW: torch.Hardware{Vendor: "NVIDIA", Name: "GeForce GTX 1080 Ti"}, WantBackend: "cuda", WantCUDA: "12.1", WantIndexPart: "cu121"},
		{Name: "NVIDIA RTX 20/Turing", HW: torch.Hardware{Vendor: "NVIDIA", Name: "GeForce RTX 2080 Ti"}, WantBackend: "cuda", WantCUDA: nvidiaCUDA, WantIndexPart: cuTag},
		{Name: "NVIDIA RTX 30/Ampere", HW: torch.Hardware{Vendor: "NVIDIA", Name: "GeForce RTX 3090"}, WantBackend: "cuda", WantCUDA: nvidiaCUDA, WantIndexPart: cuTag},
		{Name: "NVIDIA RTX 40/Ada", HW: torch.Hardware{Vendor: "NVIDIA", Name: "GeForce RTX 4090"}, WantBackend: "cuda", WantCUDA: nvidiaCUDA, WantIndexPart: cuTag},
		{Name: "NVIDIA RTX 50/Blackwell", HW: torch.Hardware{Vendor: "NVIDIA", Name: "GeForce RTX 5090"}, WantBackend: "cuda", WantCUDA: nvidiaCUDA, WantIndexPart: cuTag},
	}
	fmt.Printf("Checking CUDA %s migration safety matrix...\n", candidate)
	var errs []string
	for _, tc := range cases {
		plan := torch.PlanInstall(tc.HW, "", cfg, "")
		if plan.Backend != tc.WantBackend {
			errs = append(errs, fmt.Sprintf("%s: backend %q, want %q", tc.Name, plan.Backend, tc.WantBackend))
		}
		if plan.EffectiveCUDA != tc.WantCUDA {
			errs = append(errs, fmt.Sprintf("%s: CUDA %q, want %q", tc.Name, plan.EffectiveCUDA, tc.WantCUDA))
		}
		if !strings.Contains(plan.IndexURL, tc.WantIndexPart) {
			errs = append(errs, fmt.Sprintf("%s: index %q, want it to contain %q", tc.Name, plan.IndexURL, tc.WantIndexPart))
		}
		fmt.Printf("  ok %-32s -> %-4s %-4s %s\n", tc.Name, plan.Backend, dashIfEmpty(plan.EffectiveCUDA), plan.IndexURL)
	}
	if len(errs) > 0 {
		return errors.New("CUDA migration check failed:\n  - " + strings.Join(errs, "\n  - "))
	}
	return nil
}

func dashIfEmpty(value string) string {
	if value == "" {
		return "-"
	}
	return value
}

func build(target target, version, rootDir, outDir string) error {
	outPath := filepath.Join(outDir, target.Name)
	args := []string{
		"build",
		"-trimpath",
		"-ldflags",
		fmt.Sprintf("-s -w -X main.version=%s", version),
		"-o",
		outPath,
		"./cmd/installer-app",
	}
	cmd := exec.Command("go", args...)
	cmd.Dir = rootDir
	cmd.Env = append(os.Environ(), "CGO_ENABLED=0", "GOOS="+target.GOOS, "GOARCH="+target.GOARCH)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	fmt.Printf("Building %s/%s -> %s\n", target.GOOS, target.GOARCH, outPath)
	if err := cmd.Run(); err != nil {
		return err
	}
	rootOut := filepath.Join(rootDir, target.Name)
	if samePath(outPath, rootOut) {
		return nil
	}
	fmt.Printf("Copying %s -> %s\n", outPath, rootOut)
	return copyFile(outPath, rootOut)
}

func repoRoot() (string, error) {
	dir, err := os.Getwd()
	if err != nil {
		return "", err
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return "", errors.New("could not find repository root with go.mod")
		}
		dir = parent
	}
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	info, err := in.Stat()
	if err != nil {
		return err
	}
	out, err := os.OpenFile(dst, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, info.Mode())
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		_ = out.Close()
		return err
	}
	return out.Close()
}

func samePath(a, b string) bool {
	aa, errA := filepath.Abs(a)
	bb, errB := filepath.Abs(b)
	if errA == nil && errB == nil {
		return aa == bb
	}
	return a == b
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "error:", err)
	os.Exit(1)
}
