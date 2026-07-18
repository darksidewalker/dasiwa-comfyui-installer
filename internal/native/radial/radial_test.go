package radial

import (
	"reflect"
	"testing"
)

func TestSourceInstallArgsPreserveSelectedTorchStack(t *testing.T) {
	got := sourceInstallArgs("/venv/bin/python")
	want := []string{"pip", "install", "--no-build-isolation", "--no-deps", "--python", "/venv/bin/python", "."}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("sourceInstallArgs() = %q, want %q", got, want)
	}
}
