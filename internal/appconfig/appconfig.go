package appconfig

import (
	"encoding/json"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
)

var overrideSections = []string{"python", "comfyui", "cuda", "urls", "custom_nodes", "optional_downloads"}

func LoadMergedJSON(root string) ([]byte, error) {
	return LoadMergedJSONWithFallback(root, nil)
}

func LoadMergedJSONWithFallback(root string, fallback fs.FS) ([]byte, error) {
	configPath := filepath.Join(root, "config.json")
	baseBytes, err := os.ReadFile(configPath)
	if err != nil {
		if fallback == nil || !errors.Is(err, os.ErrNotExist) {
			return nil, err
		}
		baseBytes, err = fs.ReadFile(fallback, "config.json")
		if err != nil {
			return nil, err
		}
	}
	return MergeJSONBytes(baseBytes, nil)
}

func MergeJSONBytes(baseBytes []byte, overrides map[string]any) ([]byte, error) {
	var base map[string]any
	if err := json.Unmarshal(baseBytes, &base); err != nil {
		return nil, err
	}
	for _, section := range overrideSections {
		value, ok := overrides[section]
		if !ok {
			continue
		}
		localMap, localIsMap := value.(map[string]any)
		baseMap, baseIsMap := base[section].(map[string]any)
		if localIsMap && baseIsMap {
			for key, nestedValue := range localMap {
				baseMap[key] = nestedValue
			}
			base[section] = baseMap
		} else {
			base[section] = value
		}
	}
	return json.Marshal(base)
}
