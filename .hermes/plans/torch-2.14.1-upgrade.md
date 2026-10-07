# Torch 2.14.1 cu130 Upgrade Implementation Plan

**Goal:** Upgrade the installer's modern NVIDIA stack without touching live ComfyUI environments.
**Architecture:** Keep explicit cu130 Torch/vision/audio pins, align Sage and Triton selectors, and validate the selected stack after installation. Invalidate old compiled attention packages only when the installed Torch/CUDA ABI changes.
**Tech stack:** Go, uv, embedded standalone Linux/Windows binaries.

1. TDD: update modern NVIDIA expectations to torch 2.14.1 / torchvision 0.29.1 / torchaudio 2.11.0; retain GTX10, AMD, CPU and Intel paths.
2. TDD: align Sage cu130 planner and Linux/Windows Triton 3.8 selectors without changing older explicit Torch mappings.
3. TDD: reject wrong exact CUDA stack versions, recheck after repair, and invalidate preexisting compiled attention extensions when Torch/CUDA changes.
4. Update README with stable TorchAudio ABI rationale and attention/runtime caveats. Keep config version 2.2.1: compatibility upgrade, no added downloads/nodes/features.
5. Run full Go suite and isolated real uv Python 3.12 Linux/Windows resolution with current upstream ComfyUI requirements.
6. Build both root release binaries with cmd/build-release; smoke Linux embedded /api/config in scratch and stop only that test process.

## Verification status

- [x] TDD red/green observed for stack pins, Sage planner, Triton mappings, exact CUDA versions, repair verification, legacy priority handling, attention invalidation and source cache bypass.
- [x] Full Go suite passes (143 tests across 22 packages); integration tests requiring explicit opt-in remain skipped.
- [x] Eight real uv Python 3.12 Linux/Windows Torch/Triton resolver cases pass, with/without Sage-selected Triton and with/without current fetched ComfyUI requirements. Resolved Torch 2.14.1+cu130, vision 0.29.1+cu130, audio 2.11.0+cu130, Triton 3.8.0 / triton-windows 3.8.0.post29.
- [x] GTX 10 cu121 stack resolves on Linux and Windows Python 3.12; AMD pins and Intel/CPU selectors unchanged by source edits and covered by suite/migration matrix.
- [x] Windows Sage cu130 ABI3 fallback wheel resolves separately with real uv --no-deps. Linux cu130 Sage correctly rejects CUDA 12 HF wheels and retains compiler-gated source fallback.
- [x] Final release build and Linux API smoke pass after all source edits; embedded config stays version 2.2.1, Python 3.12, toolkit 13.2, with updated embedded README. Both tracked smoke processes were stopped.

Resolver evidence: `$TMPDIR/torch214-verification/`. Fresh raw requirements contained comfy-kitchen 0.2.37 and comfy-aimdo 0.5.5 (web extraction returned an older cached snapshot); direct fetched content was used for all combined dry-runs.

**Limits:** No live environment changes, service restarts, commit or push. Resolver/cross-build success does not verify GPU kernels or Windows runtime. Optional source builds remain compiler- and wheel-dependent.
