package bootstrap

import (
	"archive/zip"
	"bytes"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

type uvTransport func(*http.Request) (*http.Response, error)

func (f uvTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestEnsureUVChecksLatestAndPreservesSystemUV(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("executable shell fixtures are Unix-only")
	}
	for _, tc := range []struct {
		name, local, system, downloaded string
		apiFailure, wantFailure         bool
		wantDownloads                   int
		wantSystem                      bool
	}{
		{name: "current local", local: "0.12.15", system: "0.8.22"},
		{name: "current PATH", system: "0.12.15", wantSystem: true},
		{name: "stale local with current PATH", local: "0.8.22", system: "0.12.15", wantSystem: true},
		{name: "old PATH", system: "0.8.22", downloaded: "0.12.15", wantDownloads: 1},
		{name: "old local", local: "0.8.22", system: "0.8.22", downloaded: "0.12.15", wantDownloads: 1},
		{name: "missing", downloaded: "0.12.15", wantDownloads: 1},
		{name: "bad download preserves local", local: "0.8.22", downloaded: "0.8.22", wantFailure: true, wantDownloads: 1},
		{name: "API failure refuses unverified uv", local: "0.8.22", apiFailure: true, wantFailure: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			root := t.TempDir()
			bin, system := filepath.Join(root, "local"), filepath.Join(root, "system")
			for _, dir := range []string{bin, system} {
				if err := os.MkdirAll(dir, 0755); err != nil {
					t.Fatal(err)
				}
			}
			localPath, systemPath := filepath.Join(bin, "uv"), filepath.Join(system, "uv")
			fixture := func(version string) []byte { return []byte("#!/bin/sh\nprintf 'uv " + version + "\\n'\n") }
			for path, version := range map[string]string{localPath: tc.local, systemPath: tc.system} {
				if version != "" {
					if err := os.WriteFile(path, fixture(version), 0755); err != nil {
						t.Fatal(err)
					}
				}
			}
			t.Setenv("PATH", system)
			var archive bytes.Buffer
			zw := zip.NewWriter(&archive)
			entry, err := zw.Create("uv")
			if err != nil {
				t.Fatal(err)
			}
			if _, err := entry.Write(fixture(tc.downloaded)); err != nil {
				t.Fatal(err)
			}
			if err := zw.Close(); err != nil {
				t.Fatal(err)
			}
			previous := uvHTTPClient
			t.Cleanup(func() { uvHTTPClient = previous })
			downloads, checks := 0, 0
			uvHTTPClient = &http.Client{Transport: uvTransport(func(r *http.Request) (*http.Response, error) {
				body, status := "", http.StatusOK
				if r.URL.String() == uvLatestAPI {
					checks++
					body = fmt.Sprintf(`{"tag_name":"0.12.15","assets":[{"name":"uv-%s.zip","browser_download_url":"https://example.test/uv.zip"}]}`, uvTargetToken())
					if tc.apiFailure {
						status = http.StatusServiceUnavailable
					}
				} else if r.URL.String() == "https://example.test/uv.zip" {
					downloads++
					body = archive.String()
				} else {
					t.Fatalf("unexpected request: %s", r.URL)
				}
				return &http.Response{StatusCode: status, Status: http.StatusText(status), Body: io.NopCloser(strings.NewReader(body)), Header: make(http.Header)}, nil
			})}
			got, err := ensureUV(bin, func(string) {})
			if (err != nil) != tc.wantFailure {
				t.Fatalf("path=%q error=%v", got, err)
			}
			if checks != 1 || downloads != tc.wantDownloads {
				t.Fatalf("checks=%d downloads=%d", checks, downloads)
			}
			if !tc.wantFailure {
				want := localPath
				if tc.wantSystem {
					want = systemPath
				}
				if got != want || !uvMatchesVersion(got, "0.12.15") {
					t.Fatalf("got %q want %q", got, want)
				}
				if tc.wantSystem && fileExists(localPath) {
					t.Fatal("stale local uv shadows selected PATH uv")
				}
			} else if tc.local != "" && !uvMatchesVersion(localPath, tc.local) {
				t.Fatal("failed update changed existing local uv")
			}
			if tc.system != "" && !uvMatchesVersion(systemPath, tc.system) {
				t.Fatal("system uv was modified")
			}
		})
	}
}

func TestEnsureUVLiveIntegration(t *testing.T) {
	if os.Getenv("DASIWA_UV_INTEGRATION") != "1" {
		t.Skip("set DASIWA_UV_INTEGRATION=1 for real GitHub release/download test")
	}
	bin := t.TempDir()
	// Prevent a system uv from satisfying the check: exercise the download path.
	t.Setenv("PATH", bin)
	path, err := ensureUV(bin, func(s string) { t.Log(s) })
	if err != nil {
		t.Fatal(err)
	}
	if path != filepath.Join(bin, executableName("uv")) {
		t.Fatalf("unexpected path %q", path)
	}
	again, err := ensureUV(bin, func(s string) { t.Log(s) })
	if err != nil || again != path {
		t.Fatalf("repeat: %q %v", again, err)
	}
}
