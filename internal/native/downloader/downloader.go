package downloader

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"net"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

// dlClient has connection-level timeouts but NO body read timeout, so
// multi-GB model downloads (T5 Encoder ~6.7 GB) cannot be interrupted.
var dlClient = &http.Client{
	Timeout: 0, // no overall timeout — body reads can take hours
	Transport: &http.Transport{
		DialContext: (&net.Dialer{
			Timeout:   30 * time.Second,
			KeepAlive: 30 * time.Second,
		}).DialContext,
		TLSHandshakeTimeout: 10 * time.Second,
	},
}

type LogFunc func(string)

type Item struct {
	Name     string     `json:"name"`
	Type     string     `json:"type"`
	URL      string     `json:"url"`
	RepoPath string     `json:"repo_path"`
	Folder   string     `json:"folder"`
	Version  string     `json:"version"`
	Kind     string     `json:"kind"`
	Files    []AssetRef `json:"files"`
}

type AssetRef struct {
	Src  string `json:"src"`
	Type string `json:"type"`
	File string `json:"file"`
}

type LatestFile struct {
	Name        string
	DownloadURL string
}

var hfBlobRE = regexp.MustCompile(`^(https?://(?:[^/]+\.)?huggingface\.co/[^/]+/[^/]+)/blob/`)

var binaryExts = map[string]struct{}{
	".safetensors": {}, ".ckpt": {}, ".pt": {}, ".pth": {}, ".bin": {}, ".gguf": {}, ".onnx": {},
	".pkl": {}, ".npz": {}, ".tar": {}, ".zip": {}, ".7z": {}, ".gz": {}, ".xz": {}, ".zst": {},
	".png": {}, ".jpg": {}, ".jpeg": {}, ".webp": {}, ".mp3": {}, ".mp4": {}, ".wav": {}, ".flac": {},
	".mov": {}, ".mkv": {}, ".webm": {},
}

func Download(rawURL, destFolder, displayName, explicitFile string, logf LogFunc) error {
	rawURL = normalizeURL(rawURL)
	filename := explicitFile
	if filename == "" {
		parsed, err := url.Parse(rawURL)
		if err != nil {
			return err
		}
		filename = filepath.Base(parsed.Path)
	}
	if filename == "" || filename == "." || filename == string(filepath.Separator) {
		return errors.New("could not determine download filename")
	}
	dest := filepath.Join(destFolder, filename)
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		return err
	}
	expectedSize, contentType := headInfo(rawURL)
	if looksBinary(rawURL, explicitFile) && strings.Contains(strings.ToLower(contentType), "text/html") {
		return fmt.Errorf("refusing %s: server returned HTML for binary URL", displayName)
	}
	if info, err := os.Stat(dest); err == nil {
		if expectedSize <= 0 || info.Size() == expectedSize {
			log(logf, filename+" already exists; skipping.")
			return nil
		}
		_ = os.Remove(dest)
	}
	tmp := dest + ".part"
	defer os.Remove(tmp)
	var lastErr error
	for attempt := 1; attempt <= 3; attempt++ {
		log(logf, fmt.Sprintf("Downloading %s (%d/3)...", displayName, attempt))
		lastErr = fetch(rawURL, tmp)
		if lastErr == nil && expectedSize > 0 {
			if info, err := os.Stat(tmp); err == nil && info.Size() != expectedSize {
				lastErr = fmt.Errorf("size mismatch (%d vs %d)", info.Size(), expectedSize)
			}
		}
		if lastErr == nil && looksBinary(rawURL, explicitFile) {
			lastErr = rejectHTMLPayload(tmp)
		}
		if lastErr == nil {
			if err := os.Rename(tmp, dest); err != nil {
				return err
			}
			log(logf, "DONE "+filename)
			return nil
		}
		_ = os.Remove(tmp)
		time.Sleep(2 * time.Second)
	}
	return fmt.Errorf("download failed for %s: %w", displayName, lastErr)
}

func FilterMissing(items []Item, comfyPath string) []Item {
	var missing []Item
	for _, item := range items {
		if item.Kind == "asset_bundle" {
			if !bundleExists(item, comfyPath) {
				missing = append(missing, item)
			}
			continue
		}
		name := explicitName(item)
		if name == "" || !fileExistsRecursive(filepath.Join(comfyPath, item.Type), name) {
			missing = append(missing, item)
		}
	}
	return missing
}

func InstallSelected(items []Item, comfyPath, root string, logf LogFunc) error {
	return InstallSelectedWithFS(items, comfyPath, root, nil, logf)
}

func InstallSelectedWithFS(items []Item, comfyPath, root string, embedded fs.FS, logf LogFunc) error {
	for _, item := range items {
		if item.Kind == "asset_bundle" {
			for _, file := range item.Files {
				if err := copyAsset(filepath.Join(root, file.Src), filepath.Join(comfyPath, file.Type, file.File), embedded, file.Src); err != nil {
					return err
				}
			}
			continue
		}
		urlToGet := item.URL
		filename := ""
		if strings.EqualFold(item.Version, "latest") && item.RepoPath != "" && item.Folder != "" {
			latest, err := GetLatestGithubFile(item.RepoPath, item.Folder)
			if err != nil {
				return err
			}
			urlToGet = latest.DownloadURL
			filename = latest.Name
		}
		if err := Download(urlToGet, filepath.Join(comfyPath, item.Type), item.Name, filename, logf); err != nil {
			return err
		}
	}
	return nil
}

func GetLatestGithubFile(repoPath, folder string) (*LatestFile, error) {
	client := &http.Client{Timeout: 15 * time.Second}
	commitsURL := fmt.Sprintf("https://api.github.com/repos/%s/commits?path=%s&per_page=1", repoPath, url.PathEscape(folder))
	var commits []struct {
		SHA string `json:"sha"`
	}
	if err := getJSON(client, commitsURL, &commits); err != nil {
		return nil, err
	}
	if len(commits) == 0 {
		return nil, errors.New("no commits found for folder")
	}
	contentsURL := fmt.Sprintf("https://api.github.com/repos/%s/contents/%s", repoPath, folder)
	var contents []struct {
		Name        string `json:"name"`
		DownloadURL string `json:"download_url"`
	}
	if err := getJSON(client, contentsURL, &contents); err != nil {
		return nil, err
	}
	for _, file := range contents {
		if strings.HasSuffix(file.Name, ".json") {
			return &LatestFile{Name: file.Name, DownloadURL: file.DownloadURL}, nil
		}
	}
	return nil, errors.New("no json file found in latest folder")
}

func getJSON(client *http.Client, rawURL string, out any) error {
	req, err := http.NewRequest(http.MethodGet, rawURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", "DaSiWa-Installer-Go/1.0")
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("github API returned %s", resp.Status)
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

func fetch(rawURL, dest string) error {
	req, err := http.NewRequest(http.MethodGet, rawURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", "DaSiWa-Installer-Go/1.0")
	resp, err := dlClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("download returned %s", resp.Status)
	}
	out, err := os.OpenFile(dest, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644)
	if err != nil {
		return err
	}
	defer out.Close()
	_, err = io.Copy(out, resp.Body)
	return err
}

func headInfo(rawURL string) (int64, string) {
	req, err := http.NewRequest(http.MethodHead, rawURL, nil)
	if err != nil {
		return 0, ""
	}
	req.Header.Set("User-Agent", "DaSiWa-Installer-Go/1.0")
	resp, err := dlClient.Do(req)
	if err != nil {
		return 0, ""
	}
	defer resp.Body.Close()
	return resp.ContentLength, resp.Header.Get("Content-Type")
}

func rejectHTMLPayload(path string) error {
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()
	buf := make([]byte, 512)
	n, _ := file.Read(buf)
	sniff := strings.ToLower(strings.TrimSpace(string(buf[:n])))
	if strings.HasPrefix(sniff, "<!doctype html") || strings.HasPrefix(sniff, "<html") {
		return errors.New("server returned HTML instead of binary payload")
	}
	return nil
}

func normalizeURL(rawURL string) string {
	return hfBlobRE.ReplaceAllString(rawURL, "$1/resolve/")
}

func looksBinary(rawURL, explicitFile string) bool {
	name := explicitFile
	if name == "" {
		if parsed, err := url.Parse(rawURL); err == nil {
			name = parsed.Path
		}
	}
	_, ok := binaryExts[strings.ToLower(filepath.Ext(name))]
	return ok
}

func explicitName(item Item) string {
	if item.URL == "" {
		return ""
	}
	parsed, err := url.Parse(item.URL)
	if err != nil {
		return ""
	}
	return filepath.Base(parsed.Path)
}

func fileExistsRecursive(base, filename string) bool {
	found := false
	_ = filepath.WalkDir(base, func(path string, entry os.DirEntry, err error) error {
		if err == nil && !entry.IsDir() && entry.Name() == filename {
			found = true
			return filepath.SkipAll
		}
		return nil
	})
	return found
}

func bundleExists(item Item, comfyPath string) bool {
	for _, file := range item.Files {
		if _, err := os.Stat(filepath.Join(comfyPath, file.Type, file.File)); err != nil {
			return false
		}
	}
	return true
}

func copyAsset(src, dest string, embedded fs.FS, embeddedPath string) error {
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		return err
	}
	var in io.ReadCloser
	in, err := os.Open(src)
	if err != nil {
		if embedded == nil {
			return err
		}
		in, err = embedded.Open(embeddedPath)
		if err != nil {
			return err
		}
	}
	defer in.Close()
	tmp := dest + ".part"
	out, err := os.OpenFile(tmp, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		_ = out.Close()
		_ = os.Remove(tmp)
		return err
	}
	if err := out.Close(); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	return os.Rename(tmp, dest)
}

func log(logf LogFunc, line string) {
	if logf != nil {
		logf(line)
	}
}
