package torch

import (
	"context"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestReassertRejectsUnrepairedStack(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("POSIX command fixture")
	}
	dir := t.TempDir()
	python := filepath.Join(dir, "python")
	if err := os.WriteFile(python, []byte("#!/bin/sh\nprintf '%s\\n' '{\"torch\":\"2.11.0+cu130\",\"vision\":\"0.26.0+cu130\",\"audio\":\"2.11.0+cu130\",\"cuda\":\"13.0\",\"hip\":\"\"}'\n"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "uv"), []byte("#!/bin/sh\nexit 0\n"), 0755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", dir+string(os.PathListSeparator)+os.Getenv("PATH"))
	err := Reassert(context.Background(), os.Environ(), python, Hardware{Vendor: "NVIDIA", Name: "RTX 4090"}, "13.2", CUDAConfig{}, "", nil)
	if err == nil || !strings.Contains(err.Error(), "verification") {
		t.Fatalf("successful uv exit must not validate wrong stack: %v", err)
	}
}

func TestCUDAPlanRequiresExactStack(t *testing.T) {
	plan := PlanInstall(Hardware{Vendor: "NVIDIA", Name: "RTX 4090"}, "13.2", CUDAConfig{}, "")
	good := installedProbe{TorchVersion: "2.14.1+cu130", VisionVersion: "0.29.1+cu130", AudioVersion: "2.11.0+cu130", CUDA: "13.0"}
	if !installedSatisfiesPlan(good, plan) {
		t.Fatal("matching stable ABI stack rejected")
	}
	for _, pkg := range []string{"torch", "vision", "audio"} {
		bad := good
		switch pkg {
		case "torch":
			bad.TorchVersion = "2.11.0+cu130"
		case "vision":
			bad.VisionVersion = "0.26.0+cu130"
		case "audio":
			bad.AudioVersion = "2.10.0+cu130"
		}
		if installedSatisfiesPlan(bad, plan) {
			t.Errorf("accepted wrong %s version", pkg)
		}
	}
}

func TestTorch214PriorityMatrix(t *testing.T) {
	for _, windows := range []bool{false, true} {
		for _, sage := range []bool{false, true} {
			for _, pin := range []string{"", "2.14.1"} {
				args := PriorityInstallArgs(sage, windows, pin, Hardware{Vendor: "NVIDIA", Name: "RTX 4090"}, "13.2")
				spec := "triton>=3.8,<3.9.dev0"
				if windows {
					spec = "triton-windows>=3.8,<3.9"
				}
				if (windows || sage) && !contains(args, spec) {
					t.Errorf("windows=%v sage=%v pin=%q: %v", windows, sage, pin, args)
				}
			}
		}
	}
}

func TestLegacyPriorityKeepsCUDA121WithoutNewTriton(t *testing.T) {
	for _, windows := range []bool{false, true} {
		args := PriorityInstallArgs(true, windows, "2.4.1", Hardware{Vendor: "NVIDIA", Name: "GTX 1080 Ti"}, "13.2")
		if !contains(args, "https://download.pytorch.org/whl/cu121") {
			t.Errorf("legacy CUDA index: %v", args)
		}
		for _, arg := range args {
			if strings.HasPrefix(arg, "triton") {
				t.Errorf("legacy Triton must be supplied by Torch: %v", args)
			}
		}
	}
}

func TestEarlierWindowsTritonMappings(t *testing.T) {
	for version, want := range map[string]string{"2.9.1": "triton-windows>=3.5,<3.6", "2.10.0": "triton-windows>=3.6,<3.7", "2.11.0": "triton-windows>=3.6,<3.7", "2.12.0": "triton-windows>=3.7,<3.8"} {
		if got := windowsTritonSpec(version); got != want {
			t.Errorf("%s: %s != %s", version, got, want)
		}
	}
}
