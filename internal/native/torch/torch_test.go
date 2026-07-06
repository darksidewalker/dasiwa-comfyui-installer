package torch

import (
	"reflect"
	"strings"
	"testing"
)

func TestInstallArgsMatchInstallPlan(t *testing.T) {
	hw := Hardware{Vendor: "NVIDIA", Name: "GeForce RTX 4090"}
	cfg := CUDAConfig{Global: "13.2", MinCUDAFor50x: "13.2"}
	plan := PlanInstall(hw, "", cfg, "")
	want := []string{"pip", "install"}
	want = append(want, plan.Packages...)
	want = append(want, "--index-url", plan.IndexURL)
	if got := InstallArgs(hw, "", cfg, ""); !reflect.DeepEqual(got, want) {
		t.Fatalf("InstallArgs() drifted from PlanInstall():\n got %v\nwant %v", got, want)
	}
}

func TestCU132MigrationSafetyMatrix(t *testing.T) {
	cfg := CUDAConfig{Global: "13.2", MinCUDAFor50x: "13.2"}
	cases := []struct {
		name          string
		hw            Hardware
		backend       string
		effectiveCUDA string
		indexContains string
	}{
		{name: "amd stable rocm", hw: Hardware{Vendor: "AMD", Name: "Radeon RX 6800 XT"}, backend: "rocm", indexContains: "gfx110X-all"},
		{name: "amd gfx110 nightly", hw: Hardware{Vendor: "AMD", Name: "Radeon RX 7900 XTX GFX1100"}, backend: "rocm", indexContains: "gfx110X-all"},
		{name: "intel xpu", hw: Hardware{Vendor: "INTEL", Name: "Intel Arc B580"}, backend: "xpu", indexContains: "/xpu"},
		{name: "nvidia gtx 10 legacy", hw: Hardware{Vendor: "NVIDIA", Name: "GeForce GTX 1080 Ti"}, backend: "cuda", effectiveCUDA: "12.1", indexContains: "cu121"},
		{name: "nvidia rtx 20", hw: Hardware{Vendor: "NVIDIA", Name: "GeForce RTX 2080 Ti"}, backend: "cuda", effectiveCUDA: "12.8", indexContains: "cu128"},
		{name: "nvidia rtx 30", hw: Hardware{Vendor: "NVIDIA", Name: "GeForce RTX 3090"}, backend: "cuda", effectiveCUDA: "12.8", indexContains: "cu128"},
		{name: "nvidia rtx 40", hw: Hardware{Vendor: "NVIDIA", Name: "GeForce RTX 4090"}, backend: "cuda", effectiveCUDA: "12.8", indexContains: "cu128"},
		{name: "nvidia rtx 50", hw: Hardware{Vendor: "NVIDIA", Name: "GeForce RTX 5090"}, backend: "cuda", effectiveCUDA: "12.8", indexContains: "cu128"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			plan := PlanInstall(tc.hw, "", cfg, "")
			if plan.Backend != tc.backend {
				t.Fatalf("backend = %q, want %q", plan.Backend, tc.backend)
			}
			if plan.EffectiveCUDA != tc.effectiveCUDA {
				t.Fatalf("effective CUDA = %q, want %q", plan.EffectiveCUDA, tc.effectiveCUDA)
			}
			if !strings.Contains(plan.IndexURL, tc.indexContains) {
				t.Fatalf("index URL = %q, want it to contain %q", plan.IndexURL, tc.indexContains)
			}
		})
	}
}

func TestGTX10StaysOnLegacyTorch(t *testing.T) {
	plan := PlanInstall(Hardware{Vendor: "NVIDIA", Name: "GeForce GTX 1070"}, "", CUDAConfig{Global: "13.2", MinCUDAFor50x: "13.2"}, "")
	want := []string{"torch==2.4.1", "torchvision==0.19.1", "torchaudio==2.4.1"}
	if !reflect.DeepEqual(plan.Packages, want) {
		t.Fatalf("GTX 10 packages = %v, want %v", plan.Packages, want)
	}
}

func TestRTX50UsesInstallableCUDA128TorchWithTorchaudio(t *testing.T) {
	hw := Hardware{Vendor: "NVIDIA", Name: "NVIDIA GeForce RTX 5090"}
	cfg := CUDAConfig{Global: "13.2", MinCUDAFor50x: "13.2"}
	plan := PlanInstall(hw, "", cfg, "")
	if plan.IndexURL != "https://download.pytorch.org/whl/cu128" {
		t.Fatalf("RTX 50 index URL = %q, want official cu128", plan.IndexURL)
	}
	wantPackages := []string{"torch==2.9.1", "torchvision==0.24.1", "torchaudio==2.9.1"}
	if !reflect.DeepEqual(plan.Packages, wantPackages) {
		t.Fatalf("RTX 50 packages = %v, want %v", plan.Packages, wantPackages)
	}
	wantArgs := []string{"pip", "install", "torch==2.9.1", "torchvision==0.24.1", "torchaudio==2.9.1", "--index-url", plan.IndexURL}
	if got := InstallArgs(hw, "", cfg, ""); !reflect.DeepEqual(got, wantArgs) {
		t.Fatalf("RTX 50 install args = %v, want %v", got, wantArgs)
	}
}

func TestModernNVIDIAUsesTorch291CUDA128WithTorchaudio(t *testing.T) {
	hw := Hardware{Vendor: "NVIDIA", Name: "NVIDIA GeForce RTX 4090"}
	cfg := CUDAConfig{Global: "13.2", MinCUDAFor50x: "13.2"}
	plan := PlanInstall(hw, "", cfg, "")
	if plan.IndexURL != "https://download.pytorch.org/whl/cu128" {
		t.Fatalf("RTX 40 index URL = %q, want official cu128", plan.IndexURL)
	}
	wantPackages := []string{"torch==2.9.1", "torchvision==0.24.1", "torchaudio==2.9.1"}
	if !reflect.DeepEqual(plan.Packages, wantPackages) {
		t.Fatalf("RTX 40 packages = %v, want %v", plan.Packages, wantPackages)
	}
}

func TestPriorityInstallDoesNotResolveTorchDependencies(t *testing.T) {
	args := PriorityInstallArgs(true, false, "", Hardware{Vendor: "NVIDIA", Name: "GeForce RTX 5090"}, "13.2")
	if !contains(args, "--no-deps") {
		t.Fatalf("priority install args = %v, want --no-deps to prevent Torch replacement", args)
	}
	if contains(args, "torch") || contains(args, "torchvision") || contains(args, "torchaudio") {
		t.Fatalf("priority install args = %v, should not install unpinned Torch packages", args)
	}
	if !contains(args, "triton>=3.7,<3.8") {
		t.Fatalf("priority install args = %v, want triton 3.7 range instead of exact downgrade pin", args)
	}
}

func TestPinnedPriorityInstallUsesEffectiveCUDAIndexWithoutDeps(t *testing.T) {
	args := PriorityInstallArgs(true, true, "2.9.1", Hardware{Vendor: "NVIDIA", Name: "GeForce RTX 5090"}, "13.2")
	if !contains(args, "--no-deps") {
		t.Fatalf("pinned priority install args = %v, want --no-deps", args)
	}
	if !contains(args, "torch==2.9.1") {
		t.Fatalf("pinned priority install args = %v, want exact pinned Torch", args)
	}
	if !contains(args, "triton-windows>=3.5,<3.6") {
		t.Fatalf("pinned priority install args = %v, want Sage-compatible triton-windows", args)
	}
	if !contains(args, "https://download.pytorch.org/whl/cu128") {
		t.Fatalf("pinned priority install args = %v, want effective CUDA wheel index", args)
	}
}

func contains(items []string, want string) bool {
	for _, item := range items {
		if item == want {
			return true
		}
	}
	return false
}

func TestInstalledSatisfiesCUDAPlan(t *testing.T) {
	plan := InstallPlan{Backend: "cuda", EffectiveCUDA: "12.8"}
	if !installedSatisfiesPlan(installedProbe{TorchVersion: "2.9.1+cu128", CUDA: "12.8"}, plan) {
		t.Fatal("installedSatisfiesPlan() rejected matching CUDA 12.8 torch")
	}
	if installedSatisfiesPlan(installedProbe{TorchVersion: "2.12.0"}, plan) {
		t.Fatal("installedSatisfiesPlan() accepted CPU-only torch for CUDA plan")
	}
	if installedSatisfiesPlan(installedProbe{TorchVersion: "2.14.0", CUDA: "13.2"}, plan) {
		t.Fatal("installedSatisfiesPlan() accepted CUDA 13.2 torch for CUDA 12.8 plan")
	}
}

func TestParseInstalledProbeAllowsEmptyHIP(t *testing.T) {
	probe, err := parseInstalledProbe(`{"torch":"2.9.1+cu128","cuda":"12.8","hip":""}`)
	if err != nil {
		t.Fatalf("parseInstalledProbe() = %v, want nil", err)
	}
	if probe.TorchVersion != "2.9.1+cu128" || probe.CUDA != "12.8" || probe.HIP != "" {
		t.Fatalf("parseInstalledProbe() = %+v, want CUDA torch with empty HIP", probe)
	}
}

func TestSameMajorMinor(t *testing.T) {
	if !sameMajorMinor("13.2", "13.2") {
		t.Fatal("sameMajorMinor() rejected equal version")
	}
	if sameMajorMinor("13.3", "13.2") {
		t.Fatal("sameMajorMinor() accepted different CUDA minor")
	}
}

func TestPinnedVersionMatchesCUDAWheelLocalSuffix(t *testing.T) {
	if !pinnedVersionMatches("2.10.0+cu128", "2.10.0") {
		t.Fatal("pinnedVersionMatches() rejected CUDA wheel local suffix")
	}
	if pinnedVersionMatches("2.10.0+cu128", "2.10.0+cu130") {
		t.Fatal("pinnedVersionMatches() accepted different exact local suffix")
	}
}
