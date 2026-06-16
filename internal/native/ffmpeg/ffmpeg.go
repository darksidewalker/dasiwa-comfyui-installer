package ffmpeg

import (
	"archive/zip"
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/runutil"
)

func SystemInstalled() bool {
	_, err := exec.LookPath(exeName("ffmpeg"))
	return err == nil
}

func LocalInstalled(comfyPath string) bool {
	_, err := os.Stat(filepath.Join(comfyPath, "ffmpeg", "bin", exeName("ffmpeg")))
	return err == nil
}

func Install(ctx context.Context, comfyPath, windowsURL string, logf runutil.LogFunc) error {
	if SystemInstalled() {
		log(logf, "FFmpeg already found in PATH.")
		return nil
	}
	if LocalInstalled(comfyPath) {
		log(logf, "Portable FFmpeg already present.")
		return nil
	}
	if runtime.GOOS == "windows" {
		if windowsURL == "" {
			return errors.New("ffmpeg_windows URL missing")
		}
		return installWindows(comfyPath, windowsURL, logf)
	}
	if runtime.GOOS == "linux" {
		return installLinux(ctx, logf)
	}
	return errors.New("automatic FFmpeg install unsupported on this OS")
}

func installWindows(comfyPath, rawURL string, logf runutil.LogFunc) error {
	log(logf, "Downloading portable FFmpeg...")
	zipPath := filepath.Join(comfyPath, "ffmpeg.zip")
	if err := download(rawURL, zipPath); err != nil {
		return err
	}
	defer os.Remove(zipPath)
	tmpDir := filepath.Join(comfyPath, "ffmpeg_temp")
	finalDir := filepath.Join(comfyPath, "ffmpeg")
	_ = os.RemoveAll(tmpDir)
	if err := unzip(zipPath, tmpDir); err != nil {
		return err
	}
	defer os.RemoveAll(tmpDir)
	entries, err := os.ReadDir(tmpDir)
	if err != nil {
		return err
	}
	for _, entry := range entries {
		if entry.IsDir() && strings.HasPrefix(strings.ToLower(entry.Name()), "ffmpeg-") {
			_ = os.RemoveAll(finalDir)
			if err := os.Rename(filepath.Join(tmpDir, entry.Name()), finalDir); err != nil {
				return err
			}
			log(logf, "Portable FFmpeg configured.")
			return nil
		}
	}
	return errors.New("ffmpeg zip did not contain expected ffmpeg-* folder")
}

func installLinux(ctx context.Context, logf runutil.LogFunc) error {
	candidates := []struct {
		manager string
		args    []string
	}{
		{"apt-get", []string{"sudo", "apt-get", "install", "-y", "ffmpeg"}},
		{"pacman", []string{"sudo", "pacman", "-S", "--noconfirm", "ffmpeg"}},
		{"dnf", []string{"sudo", "dnf", "install", "-y", "ffmpeg"}},
		{"zypper", []string{"sudo", "zypper", "install", "-y", "ffmpeg"}},
		{"brew", []string{"brew", "install", "ffmpeg"}},
	}
	for _, candidate := range candidates {
		if _, err := exec.LookPath(candidate.manager); err != nil {
			continue
		}
		log(logf, "Installing FFmpeg via "+candidate.manager+"...")
		cmd := candidate.args[0]
		args := candidate.args[1:]
		if err := runutil.Command(ctx, logf, "", os.Environ(), cmd, args...); err == nil {
			return nil
		}
	}
	return errors.New("could not automatically install FFmpeg")
}

func download(rawURL, dest string) error {
	resp, err := http.Get(rawURL)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("download failed: %s", resp.Status)
	}
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		return err
	}
	tmp := dest + ".part"
	out, err := os.OpenFile(tmp, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, resp.Body); err != nil {
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

func unzip(src, dest string) error {
	reader, err := zip.OpenReader(src)
	if err != nil {
		return err
	}
	defer reader.Close()
	for _, file := range reader.File {
		path := filepath.Join(dest, filepath.FromSlash(file.Name))
		if !safeDest(dest, path) {
			return fmt.Errorf("unsafe zip path: %s", file.Name)
		}
		if file.FileInfo().IsDir() {
			if err := os.MkdirAll(path, file.Mode()); err != nil {
				return err
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			return err
		}
		in, err := file.Open()
		if err != nil {
			return err
		}
		out, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, file.Mode())
		if err != nil {
			_ = in.Close()
			return err
		}
		_, copyErr := io.Copy(out, in)
		closeErr := out.Close()
		_ = in.Close()
		if copyErr != nil {
			return copyErr
		}
		if closeErr != nil {
			return closeErr
		}
	}
	return nil
}

func safeDest(root, dest string) bool {
	absRoot, err := filepath.Abs(root)
	if err != nil {
		return false
	}
	absDest, err := filepath.Abs(dest)
	if err != nil {
		return false
	}
	rel, err := filepath.Rel(absRoot, absDest)
	return err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(os.PathSeparator))
}

func exeName(name string) string {
	if runtime.GOOS == "windows" {
		return name + ".exe"
	}
	return name
}

func log(logf runutil.LogFunc, line string) {
	if logf != nil {
		logf(line)
	}
}
