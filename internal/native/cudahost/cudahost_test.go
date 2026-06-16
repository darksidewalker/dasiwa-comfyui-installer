package cudahost

import (
	"strings"
	"testing"
)

func TestMaxGCCForCUDA133(t *testing.T) {
	got, ok := MaxGCCForCUDA(CUDAVersion{Major: 13, Minor: 3})
	if !ok {
		t.Fatal("MaxGCCForCUDA(CUDA 13.3) was not resolved")
	}
	if got != 15 {
		t.Fatalf("MaxGCCForCUDA(CUDA 13.3) = %d, want 15 before PyTorch cap", got)
	}
}

func TestMaxGCCForFuturePatchUsesNearestKnownCUDA(t *testing.T) {
	got, ok := MaxGCCForCUDA(CUDAVersion{Major: 13, Minor: 4})
	if !ok {
		t.Fatal("MaxGCCForCUDA(CUDA 13.4) was not resolved")
	}
	if got != 15 {
		t.Fatalf("MaxGCCForCUDA(CUDA 13.4) = %d, want nearest known CUDA 13 cap", got)
	}
}

func TestRequestedCompilerPrefersNVCCCCBIN(t *testing.T) {
	cc, cxx := requestedCompiler([]string{"CC=/opt/gcc-14/bin/gcc-14", "CXX=/opt/gcc-14/bin/g++-14", "NVCC_CCBIN=/custom/bin/g++-14"})
	if cc != "/opt/gcc-14/bin/gcc-14" {
		t.Fatalf("requestedCompiler() CC = %q", cc)
	}
	if cxx != "/custom/bin/g++-14" {
		t.Fatalf("requestedCompiler() CXX = %q, want NVCC_CCBIN", cxx)
	}
}

func TestInferCCFromGXX(t *testing.T) {
	if got := inferCC("/usr/bin/g++-14"); got != "/usr/bin/gcc-14" {
		t.Fatalf("inferCC(g++-14) = %q", got)
	}
	if got := inferCC("/usr/bin/clang++"); got != "/usr/bin/clang" {
		t.Fatalf("inferCC(clang++) = %q", got)
	}
}

func TestHintMentionsCompilerOverride(t *testing.T) {
	hint := Hint(Resolution{Status: "incompatible", DefaultMajor: 16, MaxMajor: 14, CUDA: CUDAVersion{Major: 13, Minor: 3}})
	if !strings.Contains(hint, "CC/CXX/NVCC_CCBIN") {
		t.Fatalf("Hint() = %q, want override variables", hint)
	}
}
