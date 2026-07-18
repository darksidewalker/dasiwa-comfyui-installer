package install

import (
	"encoding/json"
	"testing"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/downloader"
)

func TestSelectedDownloadsUsesSubmittedIndicesForWorkflowChoices(t *testing.T) {
	var choices Choices
	if err := json.Unmarshal([]byte(`{"downloads":"selected","download_indices":[1]}`), &choices); err != nil {
		t.Fatalf("unmarshal choices: %v", err)
	}
	items := []downloader.Item{
		{Name: "First workflow", Type: "user/default/workflows", RepoPath: "owner/workflows", Folder: "first", Version: "latest"},
		{Name: "Selected workflow", Type: "user/default/workflows", RepoPath: "owner/workflows", Folder: "selected", Version: "latest"},
	}

	got := selectedDownloads(items, choices, t.TempDir())
	if len(got) != 1 || got[0].Name != "Selected workflow" {
		t.Fatalf("selectedDownloads() = %#v, want only Selected workflow", got)
	}
}
