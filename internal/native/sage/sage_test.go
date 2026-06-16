package sage

import "testing"

func TestPlanSageTorchKeepsCUDA132OnTorch212(t *testing.T) {
	pin, cuTag := PlanWindowsTorch("3.12", "13.2")
	if cuTag != "cu132" {
		t.Fatalf("PlanWindowsTorch() CUDA tag = %q, want cu132", cuTag)
	}
	if pin != "2.12.0" {
		t.Fatalf("PlanWindowsTorch() pin = %q, want 2.12.0", pin)
	}
}

func TestPlanSageTorchKeepsWindowsCUDA13Plan(t *testing.T) {
	pin, cuTag := PlanWindowsTorch("3.12", "13.0")
	if cuTag != "cu130" {
		t.Fatalf("PlanWindowsTorch() CUDA tag = %q, want cu130", cuTag)
	}
	if pin != "2.12.0+cu130" {
		t.Fatalf("PlanWindowsTorch() pin = %q, want 2.12.0+cu130", pin)
	}
}
