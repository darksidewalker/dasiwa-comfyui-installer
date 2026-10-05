package install

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/torch"
)

func TestAMDPlatformCompatibility(t *testing.T) {
	for _, tc := range []struct {
		os, arch, build string
		ok              bool
	}{
		{"windows", "amd64", "26200", true}, {"windows", "amd64", "28000", true},
		{"windows", "amd64", "26100", false}, {"windows", "amd64", "19045", false},
		{"windows", "amd64", "bad", false}, {"linux", "amd64", "", true},
		{"linux", "arm64", "", false}, {"darwin", "amd64", "", false},
	} {
		if err := validateAMDPlatform(tc.os, tc.arch, tc.build); (err == nil) != tc.ok {
			t.Errorf("platform %+v: %v", tc, err)
		}
	}
}

func TestAMDUpdateChecksExistingABIWithoutMutation(t *testing.T) {
	for _, version := range []string{"3.11.9", "3.12.13", "3.13.7"} {
		root := t.TempDir()
		venv := filepath.Join(root, "venv")
		if err := os.Mkdir(venv, 0755); err != nil {
			t.Fatal(err)
		}
		cfg := "version = " + version + "\n"
		path := filepath.Join(venv, "pyvenv.cfg")
		if err := os.WriteFile(path, []byte(cfg), 0644); err != nil {
			t.Fatal(err)
		}
		err := validateAMDSelection(root, "update", "3.12")
		if (err == nil) != (version != "3.11.9") {
			t.Errorf("existing ABI %s: %v", version, err)
		}
		data, err := os.ReadFile(path)
		if err != nil || string(data) != cfg {
			t.Fatalf("preflight mutated metadata: %s, %v", data, err)
		}
	}
}

func TestAMDInvalidSelectionFailsBeforeWipe(t *testing.T) {
	for _, tc := range []struct {
		name    string
		choices Choices
		want    string
	}{
		{name: "unknown GPU", choices: Choices{HW: torch.Hardware{Vendor: "AMD", Name: "Manual: AMD"}}, want: "not recognized"},
		{name: "CUDA Sage", choices: Choices{HW: torch.Hardware{Vendor: "AMD", Name: "Radeon RX 7900 XTX"}, WantSage: true}, want: "NVIDIA"},
		{name: "CUDA Radial", choices: Choices{HW: torch.Hardware{Vendor: "AMD", Name: "Radeon RX 7900 XTX"}, WantRadial: true}, want: "NVIDIA"},
		{name: "CUDA Flash", choices: Choices{HW: torch.Hardware{Vendor: "AMD", Name: "Radeon RX 7900 XTX"}, WantFlash: true}, want: "NVIDIA"},
		{name: "Python 3.11", choices: Choices{HW: torch.Hardware{Vendor: "AMD", Name: "Radeon RX 7900 XTX"}, ConfigOverrides: map[string]any{"python": map[string]any{"display_name": "3.11"}}}, want: "3.12 or 3.13"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			root := t.TempDir()
			comfy := filepath.Join(root, "ComfyUI")
			if err := os.MkdirAll(comfy, 0755); err != nil {
				t.Fatal(err)
			}
			marker := filepath.Join(comfy, "keep.txt")
			if err := os.WriteFile(marker, []byte("preserved"), 0644); err != nil {
				t.Fatal(err)
			}
			choices := tc.choices
			choices.InstallMode = "wipe"
			choices.ConfirmWipe = true
			choices.ComfyPath = comfy
			ctx, cancel := context.WithCancel(context.Background())
			cancel()
			err := Run(ctx, root, choices, nil)
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("Run() = %v, want preflight error containing %q", err, tc.want)
			}
			data, err := os.ReadFile(marker)
			if err != nil || string(data) != "preserved" {
				t.Fatalf("preflight modified existing installation: %q, %v", data, err)
			}
		})
	}
}
