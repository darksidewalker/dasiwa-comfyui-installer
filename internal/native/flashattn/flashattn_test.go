package flashattn

import (
	"reflect"
	"testing"
)

func TestPyPIBinaryInstallArgsUsePackageNameAsOnlyBinarySelector(t *testing.T) {
	got := pypiBinaryInstallArgs("2.8.3.post1", "/venv/bin/python")
	want := []string{
		"pip", "install", "--only-binary", "flash-attn",
		"--python", "/venv/bin/python", "flash-attn==2.8.3.post1",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("pypiBinaryInstallArgs() = %q, want %q", got, want)
	}
}

func TestSourceCloneArgsFetchRequestedTagInShallowClone(t *testing.T) {
	got := sourceCloneArgs("https://github.com/Dao-AILab/flash-attention.git", "v2.8.3.post1", "/tmp/flash-attention")
	want := []string{
		"clone", "--depth", "1", "--branch", "v2.8.3.post1",
		"https://github.com/Dao-AILab/flash-attention.git", "/tmp/flash-attention",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("sourceCloneArgs() = %q, want %q", got, want)
	}
}

func TestSourceFetchTagArgsFetchesMissingTagForExistingClone(t *testing.T) {
	got := sourceFetchTagArgs("v2.8.3.post1")
	want := []string{"fetch", "--depth", "1", "origin", "tag", "v2.8.3.post1"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("sourceFetchTagArgs() = %q, want %q", got, want)
	}
}

func TestSourceInstallArgsPreserveSelectedTorchStack(t *testing.T) {
	got := sourceInstallArgs("/venv/bin/python")
	want := []string{"pip", "install", "--no-build-isolation", "--no-deps", "--python", "/venv/bin/python", "."}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("sourceInstallArgs() = %q, want %q", got, want)
	}
}
