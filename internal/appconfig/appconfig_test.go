package appconfig

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestMergeJSONBytesAppliesSupportedOverrideSections(t *testing.T) {
	base := []byte(`{
		"python": {"display_name": "3.12"},
		"cuda": {"global": "13.0"},
		"comfyui": {"version": "latest"},
		"custom_nodes": ["https://github.com/default/node"],
		"optional_downloads": [{"name": "base"}]
	}`)
	overrides := map[string]any{
		"python":             map[string]any{"display_name": "3.13"},
		"cuda":               map[string]any{"global": "12.8"},
		"custom_nodes":       []any{"https://github.com/local/node"},
		"optional_downloads": []any{map[string]any{"name": "local"}},
	}

	mergedBytes, err := MergeJSONBytes(base, overrides)
	if err != nil {
		t.Fatal(err)
	}
	var merged map[string]any
	if err := json.Unmarshal(mergedBytes, &merged); err != nil {
		t.Fatal(err)
	}
	python := merged["python"].(map[string]any)
	cuda := merged["cuda"].(map[string]any)
	if python["display_name"] != "3.13" {
		t.Fatalf("python.display_name = %v", python["display_name"])
	}
	if cuda["global"] != "12.8" {
		t.Fatalf("cuda.global = %v", cuda["global"])
	}
	customNodes := merged["custom_nodes"].([]any)
	if customNodes[0] != "https://github.com/local/node" {
		t.Fatalf("custom_nodes override = %v", customNodes)
	}
	downloads := merged["optional_downloads"].([]any)
	if downloads[0].(map[string]any)["name"] != "local" {
		t.Fatalf("optional_downloads override = %v", downloads)
	}
}

func TestLoadMergedJSONUsesEmbeddedDefaultsOnly(t *testing.T) {
	root := t.TempDir()
	write(t, filepath.Join(root, "config.json"), `{"python":{"display_name":"3.12"}}`)
	mergedBytes, err := LoadMergedJSON(root)
	if err != nil {
		t.Fatal(err)
	}
	var merged map[string]any
	if err := json.Unmarshal(mergedBytes, &merged); err != nil {
		t.Fatal(err)
	}
	python := merged["python"].(map[string]any)
	if python["display_name"] != "3.12" {
		t.Fatalf("config defaults should be preserved")
	}
}

func write(t *testing.T, path, content string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}
