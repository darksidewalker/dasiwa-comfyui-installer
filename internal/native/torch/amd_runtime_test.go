package torch

import (
	"context"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestAMDDependencyEnvironmentPreservesPinnedStackWithSpaces(t *testing.T) {
	root := filepath.Join(t.TempDir(), "ComfyUI with spaces")
	if err := os.MkdirAll(root, 0755); err != nil {
		t.Fatal(err)
	}
	env, err := AMDDependencyEnv([]string{"UV_INDEX=https://wrong.invalid", "KEEP=yes"}, root)
	if err != nil {
		t.Fatal(err)
	}
	values := map[string]string{}
	for _, kv := range env {
		k, v, _ := strings.Cut(kv, "=")
		values[k] = v
	}
	if values["UV_INDEX"] != AMDIndexURL || values["KEEP"] != "yes" {
		t.Fatalf("bad environment: %v", env)
	}
	u, err := url.Parse(values["UV_CONSTRAINT"])
	if err != nil || u.Scheme != "file" || strings.Contains(values["UV_CONSTRAINT"], " ") {
		t.Fatalf("constraint path must be an encoded file URI: %q", values["UV_CONSTRAINT"])
	}
	path := filepath.FromSlash(u.Path)
	if len(path) > 2 && path[0] == '/' && path[2] == ':' {
		path = path[1:]
	}
	data, err := os.ReadFile(path)
	if err != nil || !strings.Contains(string(data), "torch==2.13.0+rocm10.0.0") || !strings.Contains(string(data), "torchaudio==2.11.0.2+rocm10.0.0") {
		t.Fatalf("constraints: %s, %v", data, err)
	}
}

func TestAMDProbeRequiresWorkingMatchingGPU(t *testing.T) {
	hw := Hardware{Vendor: "AMD", Name: "Radeon RX 7900 XTX"}
	good := `{"torch":"2.13.0+rocm10.0.0","vision":"0.28.0+rocm10.0.0","audio":"2.11.0.2+rocm10.0.0","cuda":"","hip":"10.0","available":true,"arch":"gfx1100:sramecc-","computed":true,"name":"AMD Radeon RX 7900 XTX"}`
	if err := validateAMDProbe(good, hw); err != nil {
		t.Fatal(err)
	}
	for _, bad := range []string{
		strings.Replace(good, `"available":true`, `"available":false`, 1),
		strings.Replace(good, `"computed":true`, `"computed":false`, 1),
		strings.Replace(good, "gfx1100:sramecc-", "gfx1201", 1),
		strings.Replace(good, "2.13.0+rocm10.0.0", "2.13.0+cu130", 1),
		strings.Replace(good, `"hip":"10.0"`, `"hip":""`, 1),
	} {
		if err := validateAMDProbe(bad, hw); err == nil {
			t.Fatalf("accepted invalid AMD probe %s", bad)
		}
	}
}

func TestAMDVerifierRejectsUnknownGPUWithoutExecutingPython(t *testing.T) {
	if err := VerifyAMD(context.Background(), nil, "missing-python", Hardware{Vendor: "AMD", Name: "Manual: AMD"}, nil); err == nil || !strings.Contains(err.Error(), "not recognized") {
		t.Fatalf("unexpected verifier error: %v", err)
	}
}
