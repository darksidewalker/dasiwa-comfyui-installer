package downloader

import "testing"

func TestSelectLatestJSONFileUsesHighestTrailingRevision(t *testing.T) {
	files := []githubContentFile{
		{Name: "DaSiWa WAN 2.2 i2v FastFidelity C-AiO-18.json", DownloadURL: "https://example.test/18"},
		{Name: "DaSiWa WAN 2.2 i2v FastFidelity C-AiO-85.json", DownloadURL: "https://example.test/85"},
		{Name: "README.md", DownloadURL: "https://example.test/readme"},
		{Name: "DaSiWa WAN 2.2 i2v FastFidelity C-AiO-9.json", DownloadURL: "https://example.test/9"},
	}

	got, err := selectLatestJSONFile(files)
	if err != nil {
		t.Fatalf("selectLatestJSONFile() error = %v", err)
	}
	if got.Name != "DaSiWa WAN 2.2 i2v FastFidelity C-AiO-85.json" {
		t.Fatalf("selectLatestJSONFile() = %q, want highest revision", got.Name)
	}
}

func TestSelectLatestJSONFileUsesNameWhenNoRevisionExists(t *testing.T) {
	files := []githubContentFile{
		{Name: "beta.json", DownloadURL: "https://example.test/beta"},
		{Name: "alpha.json", DownloadURL: "https://example.test/alpha"},
	}

	got, err := selectLatestJSONFile(files)
	if err != nil {
		t.Fatalf("selectLatestJSONFile() error = %v", err)
	}
	if got.Name != "beta.json" {
		t.Fatalf("selectLatestJSONFile() = %q, want lexically latest fallback", got.Name)
	}
}

func TestRawGitHubURLUsesHeadAndEscapesWorkflowPath(t *testing.T) {
	got, err := rawGitHubURL("darksidewalker/dasiwa-comfyui-workflows", "C-AiO", "DaSiWa Workflow 85.json")
	if err != nil {
		t.Fatalf("rawGitHubURL() error = %v", err)
	}
	want := "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-workflows/HEAD/C-AiO/DaSiWa%20Workflow%2085.json"
	if got != want {
		t.Fatalf("rawGitHubURL() = %q, want %q", got, want)
	}
}
