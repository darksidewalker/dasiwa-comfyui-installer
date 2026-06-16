package launcher

import (
	"os"
	"path/filepath"
	"runtime"
)

func Create(comfyPath string) error {
	ffmpegBin := filepath.Join(comfyPath, "ffmpeg", "bin")
	hasFFmpeg := dirExists(ffmpegBin)
	if runtime.GOOS == "windows" {
		pathLine := ""
		if hasFFmpeg {
			pathLine = "set PATH=%~dp0ffmpeg\\bin;%PATH%\n"
		}
		content := "@echo off\n" +
			"cd /d \"%~dp0\"\n" +
			pathLine +
			"start http://127.0.0.1:8188\n" +
			"venv\\Scripts\\python.exe main.py --enable-manager --preview-method auto\n" +
			"pause"
		return os.WriteFile(filepath.Join(comfyPath, "run_comfyui.bat"), []byte(content), 0o644)
	}
	pathLine := ""
	if hasFFmpeg {
		pathLine = "export PATH=\"$(dirname \"$0\")/ffmpeg/bin:$PATH\"\n"
	}
	content := "#!/bin/bash\n" +
		"cd \"$(dirname \"$0\")\"\n" +
		pathLine +
		"(sleep 5 && xdg-open http://127.0.0.1:8188) &\n" +
		"./venv/bin/python main.py --enable-manager --preview-method auto\n"
	return os.WriteFile(filepath.Join(comfyPath, "run_comfyui.sh"), []byte(content), 0o755)
}

func dirExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.IsDir()
}
