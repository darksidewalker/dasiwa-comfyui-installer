package sage

import (
	"reflect"
	"testing"
)

func TestSourceInstallAvoidsOldABICache(t *testing.T) {
	got := sourceInstallArgs("python")
	want := []string{"pip", "install", "--no-cache", "--no-build-isolation", "--no-deps", "--python", "python", "."}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("source args: %v != %v", got, want)
	}
}

func TestTorch214TritonSpec(t *testing.T) {
	for version, want := range map[string]string{"2.14.1": "triton-windows>=3.8,<3.9", "2.11.0": "triton-windows>=3.6,<3.7", "2.12.0": "triton-windows>=3.7,<3.8"} {
		if got := TritonSpec(version); got != want {
			t.Errorf("%s: %s != %s", version, got, want)
		}
	}
}
