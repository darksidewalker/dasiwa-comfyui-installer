package sage

import (
	"testing"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/cudahost"
)

func TestPlanSageTorchUsesCUDA130ForCUDA13Requests(t *testing.T) {
	pin, cuTag := PlanWindowsTorch("3.12", "13.2")
	if cuTag != "cu130" {
		t.Fatalf("PlanWindowsTorch() CUDA tag = %q, want cu130", cuTag)
	}
	if pin != "2.11.0" {
		t.Fatalf("PlanWindowsTorch() pin = %q, want 2.11.0", pin)
	}
}

func TestPlanSageTorchNormalizesWindowsCUDA13Plan(t *testing.T) {
	pin, cuTag := PlanWindowsTorch("3.12", "13.0")
	if cuTag != "cu130" {
		t.Fatalf("PlanWindowsTorch() CUDA tag = %q, want cu130", cuTag)
	}
	if pin != "2.11.0" {
		t.Fatalf("PlanWindowsTorch() pin = %q, want 2.11.0", pin)
	}
}

func TestSkipCUDA13MinorMismatch(t *testing.T) {
	tests := []struct {
		torchCUDA string
		toolkit   cudahost.CUDAVersion
		want      bool
	}{
		{torchCUDA: "13.0", toolkit: cudahost.CUDAVersion{Major: 13, Minor: 3}, want: true},
		{torchCUDA: "13.0", toolkit: cudahost.CUDAVersion{Major: 13, Minor: 0}, want: false},
		{torchCUDA: "12.8", toolkit: cudahost.CUDAVersion{Major: 13, Minor: 3}, want: false},
	}
	for _, tt := range tests {
		if got := skipCUDA13MinorMismatch(tt.torchCUDA, tt.toolkit); got != tt.want {
			t.Errorf("skipCUDA13MinorMismatch(%q, %+v) = %t, want %t", tt.torchCUDA, tt.toolkit, got, tt.want)
		}
	}
}
