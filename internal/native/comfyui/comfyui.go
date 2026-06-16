package comfyui

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/runutil"
)

const RepoURL = "https://github.com/comfyanonymous/ComfyUI.git"

func Sync(ctx context.Context, comfyPath, targetVersion, fallbackBranch string, logf runutil.LogFunc) error {
	if targetVersion == "" || strings.EqualFold(targetVersion, "latest") {
		targetVersion = "master"
	}
	if fallbackBranch == "" {
		fallbackBranch = "master"
	}
	if _, err := os.Stat(filepath.Join(comfyPath, ".git")); os.IsNotExist(err) {
		log(logf, "Cloning ComfyUI...")
		return git(ctx, logf, "", "clone", RepoURL, comfyPath)
	}
	log(logf, "Fetching ComfyUI updates...")
	if err := git(ctx, logf, comfyPath, "fetch", "--all", "--tags", "--prune"); err != nil {
		return err
	}
	if dirty(ctx, comfyPath) {
		log(logf, "ComfyUI tree has local changes; auto-stashing...")
		if err := git(ctx, logf, comfyPath, "stash", "push", "-u", "-m", "DaSiWa auto-stash before checkout"); err != nil {
			return err
		}
	}
	if targetVersion == "master" || targetVersion == fallbackBranch {
		return checkoutBranch(ctx, logf, comfyPath, targetVersion)
	}
	if err := git(ctx, logf, comfyPath, "checkout", targetVersion); err == nil {
		return nil
	}
	log(logf, fmt.Sprintf("Checkout %s failed; falling back to %s.", targetVersion, fallbackBranch))
	return checkoutBranch(ctx, logf, comfyPath, fallbackBranch)
}

func checkoutBranch(ctx context.Context, logf runutil.LogFunc, dir, branch string) error {
	if err := git(ctx, logf, dir, "checkout", branch); err != nil {
		return err
	}
	return git(ctx, logf, dir, "pull", "--ff-only", "origin", branch)
}

func dirty(ctx context.Context, dir string) bool {
	out, err := runutil.Output(ctx, dir, gitEnv(), "git", "status", "--porcelain")
	return err == nil && strings.TrimSpace(out) != ""
}

func git(ctx context.Context, logf runutil.LogFunc, dir string, args ...string) error {
	return runutil.Command(ctx, logf, dir, gitEnv(), "git", args...)
}

func gitEnv() []string {
	return runutil.SetEnv(os.Environ(), "GIT_TERMINAL_PROMPT", "0")
}

func log(logf runutil.LogFunc, line string) {
	if logf != nil {
		logf(line)
	}
}
