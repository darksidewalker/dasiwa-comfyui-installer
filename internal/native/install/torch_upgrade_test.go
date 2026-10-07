package install

import (
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/torch"
	"reflect"
	"testing"
)

func TestAttentionResetOnTorchABIChange(t *testing.T) {
	plan := torch.PlanInstall(torch.Hardware{Vendor: "NVIDIA", Name: "RTX 4090"}, "13.2", torch.CUDAConfig{}, "")
	for _, old := range []string{"2.11.0+cu130", "2.14.1+cu128"} {
		got := attentionResetArgs(old, plan)
		want := []string{"pip", "uninstall", "sageattention", "flash-attn"}
		if !reflect.DeepEqual(got, want) {
			t.Errorf("old=%s: %v != %v", old, got, want)
		}
	}
	for _, old := range []string{"", "2.14.1+cu130"} {
		if got := attentionResetArgs(old, plan); len(got) != 0 {
			t.Errorf("old=%q: unexpected reset %v", old, got)
		}
	}
	amd := torch.PlanInstall(torch.Hardware{Vendor: "AMD", Name: "Radeon RX 7900 XTX"}, "", torch.CUDAConfig{}, "")
	if got := attentionResetArgs("2.11.0", amd); len(got) != 0 {
		t.Fatal("AMD must not reset CUDA extensions")
	}
}

func TestSagePlanPreservesLegacyTorch(t *testing.T) {
	pin, _ := sageTorchPlan(torch.Hardware{Vendor: "NVIDIA", Name: "GTX 1080 Ti"}, "3.12", "13.2", torch.CUDAConfig{Global: "13.2"})
	if pin != "2.4.1" {
		t.Fatalf("legacy Sage pin=%s", pin)
	}
	pin, _ = sageTorchPlan(torch.Hardware{Vendor: "NVIDIA", Name: "RTX 4090"}, "3.12", "13.2", torch.CUDAConfig{Global: "13.2"})
	if pin != "2.14.1" {
		t.Fatalf("modern Sage pin=%s", pin)
	}
}
