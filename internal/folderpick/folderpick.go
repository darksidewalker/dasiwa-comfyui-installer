package folderpick

import (
	"context"
	"errors"
	"os/exec"
	"runtime"
	"strings"
	"time"
)

func Pick(title, initialDir string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()
	switch runtime.GOOS {
	case "windows":
		return pickWindows(ctx, title, initialDir)
	case "darwin":
		return pickDarwin(ctx, title, initialDir)
	default:
		return pickLinux(ctx, title, initialDir)
	}
}

func pickWindows(ctx context.Context, title, initialDir string) (string, error) {
	if title == "" {
		title = "Select ComfyUI folder"
	}
	script := `Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description = ` + psQuote(title) + `; $d.ShowNewFolderButton = $true;`
	if initialDir != "" {
		script += `$d.SelectedPath = ` + psQuote(initialDir) + `;`
	}
	script += `if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); Write-Output $d.SelectedPath }`
	out, err := exec.CommandContext(ctx, "powershell", "-NoProfile", "-STA", "-Command", script).Output()
	if err != nil {
		return "", err
	}
	return clean(out)
}

func pickDarwin(ctx context.Context, title, initialDir string) (string, error) {
	if title == "" {
		title = "Select ComfyUI folder"
	}
	script := `POSIX path of (choose folder with prompt ` + osaQuote(title)
	if initialDir != "" {
		script += ` default location POSIX file ` + osaQuote(initialDir)
	}
	script += `)`
	out, err := exec.CommandContext(ctx, "osascript", "-e", script).Output()
	if err != nil {
		return "", err
	}
	return clean(out)
}

func pickLinux(ctx context.Context, title, initialDir string) (string, error) {
	if title == "" {
		title = "Select ComfyUI folder"
	}
	candidates := [][]string{
		{"zenity", "--file-selection", "--directory", "--title", title},
		{"kdialog", "--getexistingdirectory", initialDir, "--title", title},
		{"yad", "--file-selection", "--directory", "--title", title},
	}
	for _, args := range candidates {
		name := args[0]
		if _, err := exec.LookPath(name); err != nil {
			continue
		}
		cmdArgs := args[1:]
		if initialDir != "" && name == "zenity" {
			cmdArgs = append(cmdArgs, "--filename", ensureSlash(initialDir))
		}
		out, err := exec.CommandContext(ctx, name, cmdArgs...).Output()
		if err == nil {
			return clean(out)
		}
	}
	return "", errors.New("no supported folder picker found; install zenity, kdialog, or yad, or type the path manually")
}

func clean(out []byte) (string, error) {
	path := strings.TrimSpace(string(out))
	if path == "" {
		return "", errors.New("folder selection cancelled")
	}
	return path, nil
}

func ensureSlash(path string) string {
	if strings.HasSuffix(path, "/") {
		return path
	}
	return path + "/"
}

func psQuote(s string) string {
	return "'" + strings.ReplaceAll(s, "'", "''") + "'"
}

func osaQuote(s string) string {
	return "\"" + strings.ReplaceAll(s, "\"", "\\\"") + "\""
}
