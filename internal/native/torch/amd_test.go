package torch

import (
	"reflect"
	"strings"
	"testing"
)

func TestAMDUsesStablePinnedDevicePackages(t *testing.T) {
	for _, name := range []string{"AMD Radeon RX 7900 XTX", "AMD Radeon RX 9070 XT", "AMD Radeon RX 6800 XT"} {
		t.Run(name, func(t *testing.T) {
			plan := PlanInstall(Hardware{Vendor: "amd", Name: name}, "13.2", CUDAConfig{}, "2.11.0")
			if plan.IndexURL != "https://stable.repo.amd.com/rocm/whl-next/" {
				t.Fatalf("AMD index = %q, want stable multi-architecture index", plan.IndexURL)
			}
			target := "gfx1100"
			if strings.Contains(name, "9070") {
				target = "gfx1201"
			}
			if strings.Contains(name, "6800") {
				target = "gfx1030"
			}
			want := []string{"torch[device-" + target + "]==2.13.0+rocm10.0.0", "torchvision[device-" + target + "]==0.28.0+rocm10.0.0", "torchaudio==2.11.0.2+rocm10.0.0"}
			if plan.Backend != "rocm" || plan.EffectiveCUDA != "" || !reflect.DeepEqual(plan.Packages, want) {
				t.Fatalf("AMD plan = %+v, want packages %v without CUDA", plan, want)
			}
		})
	}
}

func TestAMDTargetMapping(t *testing.T) {
	cases := map[string]string{
		"Radeon RX 6800 XT": "gfx1030", "Radeon RX 6900 XT": "gfx1030",
		"Radeon RX 6950 XT": "gfx1030", "Radeon PRO W6800": "gfx1030",
		"Radeon RX 7600 XT": "gfx1102", "Radeon RX 7700 XT": "gfx1101",
		"Radeon RX 7800 XT": "gfx1101", "Radeon RX 7900 XT": "gfx1100",
		"Radeon PRO W7900": "gfx1100", "Radeon PRO W7800": "gfx1100",
		"Radeon RX 9060 XT": "gfx1200", "Radeon RX 9070 XT": "gfx1201",
		"Radeon AI PRO R9700": "gfx1201", "Radeon 8060S": "gfx1151",
		"Radeon 8050S": "gfx1151", "Radeon 8040S": "gfx1151",
		"AMD GPU gfx1100": "gfx1100", "Radeon RX 7900 XTX GFX1100": "gfx1100",
		"Radeon RX7900XTX": "gfx1100", "Radeon RX7800XT": "gfx1101",
	}
	for name, want := range cases {
		t.Run(name, func(t *testing.T) {
			got, err := AMDTarget(Hardware{Vendor: "AMD", Name: name})
			if err != nil || got != want {
				t.Fatalf("AMDTarget(%q) = %q, %v; want %q", name, got, err, want)
			}
		})
	}
}

func TestAMDRejectsUnknownMobileOrConflictingTargets(t *testing.T) {
	for _, name := range []string{"Manual: AMD", "Radeon RX 7000", "Radeon RX 9000", "Radeon RX 580", "Radeon RX 580 gfx1100", "Radeon RX 7900 GRE gfx1100", "Radeon RX 7900M", "Radeon RX 7600M XT", "Radeon RX 6800 XT gfx1100", "AMD gfx900", "AMD gfx1100 gfx1201", "Radeon RX 9070 Laptop GPU"} {
		t.Run(name, func(t *testing.T) {
			plan := PlanInstall(Hardware{Vendor: "AMD", Name: name}, "", CUDAConfig{}, "")
			if plan.Err == nil || len(plan.Packages) != 0 {
				t.Fatalf("unsupported AMD plan did not fail safely: %+v", plan)
			}
		})
	}
}

func TestAMDPinnedBackendRejectsWrongStack(t *testing.T) {
	plan := PlanInstall(Hardware{Vendor: "AMD", Name: "Radeon RX 7900 XTX"}, "", CUDAConfig{}, "")
	if installedSatisfiesPlan(installedProbe{TorchVersion: "2.9.1+rocm7.2.1", HIP: "7.2.1"}, plan) {
		t.Fatal("AMD reassert accepted obsolete ROCm stack just because HIP is nonempty")
	}
}

func TestAMDNeverInstallsCUDATritonWhenSageRequested(t *testing.T) {
	for _, windows := range []bool{false, true} {
		args := PriorityInstallArgs(true, windows, "", Hardware{Vendor: "AMD", Name: "Radeon RX 7900 XTX"}, "13.2")
		for _, arg := range args {
			if strings.HasPrefix(arg, "triton") {
				t.Fatalf("AMD priority args contain CUDA Triton: %v", args)
			}
		}
	}
}
