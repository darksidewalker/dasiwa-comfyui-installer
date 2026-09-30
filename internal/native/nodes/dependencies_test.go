package nodes

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
)

func TestLlamaIndexMatchesTorchBackend(t *testing.T) {
	for _, tc := range []struct{ cuda, tag string }{{"13.0\n", "cu130"}, {"12.1", "cu121"}, {"12.4", "cu124"}, {"", "cpu"}} {
		got, err := llamaIndex(tc.cuda)
		if err != nil || got != "https://abetlen.github.io/llama-cpp-python/whl/"+tc.tag {
			t.Fatalf("%q: %s, %v", tc.cuda, got, err)
		}
	}
	if _, err := llamaIndex("not a CUDA version"); err == nil {
		t.Fatal("invalid probe must fail")
	}
}

func TestPrepareLlamaSkipsUnrelatedRequirements(t *testing.T) {
	path := filepath.Join(t.TempDir(), "requirements.txt")
	if err := os.WriteFile(path, []byte("torch\n# llama-cpp-python\nnumpy\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := prepareLlama(context.Background(), nil, "nonexistent-python", path, nil); err != nil {
		t.Fatal(err)
	}
}

func TestDependencyFailureExplainsReportedBuild(t *testing.T) {
	output := "Failed to build `llama-cpp-python==0.3.35`\n'nmake' '-?' failed with: no such file or directory\nCMake Error: CMAKE_C_COMPILER not set, after EnableLanguage\nCMake Error: CMAKE_CXX_COMPILER not set, after EnableLanguage"
	got := dependencyFailure(output)
	for _, want := range []string{"llama-cpp-python==0.3.35", "Missing build tool: nmake", "Missing C compiler", "Missing C++ compiler"} {
		if !strings.Contains(got, want) {
			t.Fatalf("%q missing from %s", want, got)
		}
	}
	if got := dependencyFailure("HTTP 503"); strings.Contains(got, "Missing C") {
		t.Fatal("must not invent compiler failures")
	}
}

func TestDependencyLogIsBoundedAndConcurrent(t *testing.T) {
	var d dependencyLog
	capture := d.capture(nil)
	var wg sync.WaitGroup
	for i := 0; i < 4; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < 100; j++ {
				capture(strings.Repeat("x", 1000))
			}
		}()
	}
	wg.Wait()
	if len(d.text) > 32768 {
		t.Fatal("unbounded output")
	}
}
