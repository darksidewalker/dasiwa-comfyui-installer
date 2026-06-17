package sage

import "testing"

func TestPlanSageTorchFallsBackToCUDA128(t *testing.T) {
	pin, cuTag := PlanWindowsTorch("3.12", "13.2")
	if cuTag != "cu128" {
		t.Fatalf("PlanWindowsTorch() CUDA tag = %q, want cu128", cuTag)
	}
	if pin != "2.9.1" {
		t.Fatalf("PlanWindowsTorch() pin = %q, want 2.9.1", pin)
	}
}

func TestPlanSageTorchNormalizesWindowsCUDA13Plan(t *testing.T) {
	pin, cuTag := PlanWindowsTorch("3.12", "13.0")
	if cuTag != "cu128" {
		t.Fatalf("PlanWindowsTorch() CUDA tag = %q, want cu128", cuTag)
	}
	if pin != "2.9.1" {
		t.Fatalf("PlanWindowsTorch() pin = %q, want 2.9.1", pin)
	}
}
