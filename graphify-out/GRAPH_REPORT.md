# Graph Report - dasiwa-comfyui-installer  (2026-06-17)

## Corpus Check
- 32 files · ~27,267 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 424 nodes · 924 edges · 23 communities
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 108 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ba767834`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]

## God Nodes (most connected - your core abstractions)
1. `Command()` - 26 edges
2. `server` - 22 edges
3. `Run()` - 19 edges
4. `PlanInstall()` - 16 edges
5. `DaSiWa ComfyUI Installer` - 16 edges
6. `contains()` - 15 edges
7. `ResolveWithEnv()` - 12 edges
8. `installWindows()` - 12 edges
9. `tryHFInstall()` - 12 edges
10. `Download()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `checkCUDAMigration()` --calls--> `PlanInstall()`  [INFERRED]
  cmd/build-release/main.go → internal/native/torch/torch.go
- `checkCUDAMigration()` --calls--> `contains()`  [INFERRED]
  cmd/build-release/main.go → internal/native/torch/torch_test.go
- `build()` --calls--> `Command()`  [INFERRED]
  cmd/build-release/main.go → internal/native/runutil/runutil.go
- `main()` --calls--> `GetEnv()`  [INFERRED]
  cmd/installer-app/main.go → internal/native/runutil/runutil.go
- `windowsGPUNameCandidates()` --calls--> `Command()`  [INFERRED]
  cmd/installer-app/main.go → internal/native/runutil/runutil.go

## Import Cycles
- None detected.

## Communities (23 total, 0 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.10
Nodes (28): Context, PythonRunner, HandlerFunc, apiConfigResponse, appConfig, appState, broker, hardwareReport (+20 more)

### Community 1 - "Community 1"
Cohesion: 0.12
Nodes (25): LoadMergedJSON(), LoadMergedJSONWithFallback(), MergeJSONBytes(), TestLoadMergedJSONUsesEmbeddedDefaultsOnly(), TestMergeJSONBytesAppliesSupportedOverrideSections(), write(), Choices, Config (+17 more)

### Community 2 - "Community 2"
Cohesion: 0.16
Nodes (35): Context, LogFunc, T, CUDAConfig, Hardware, installedProbe, InstallPlan, CurrentInstallSatisfies() (+27 more)

### Community 3 - "Community 3"
Cohesion: 0.20
Nodes (25): Context, LogFunc, Venv, T, checkHFCompatibility(), compareVersion(), cudaMajor(), envDefault() (+17 more)

### Community 4 - "Community 4"
Cohesion: 0.07
Nodes (24): chooseCurrentPath(), closePathPicker(), docBody, docDialog, docTitle, downloadsList, extraSettingsBtn, form (+16 more)

### Community 5 - "Community 5"
Cohesion: 0.19
Nodes (24): ApplyToEnv(), CheckCPP(), CheckNVCC(), exe(), Hint(), inferCC(), lessEq(), log() (+16 more)

### Community 6 - "Community 6"
Cohesion: 0.17
Nodes (23): AssetRef, Client, AssetRef, bundleExists(), copyAsset(), Download(), explicitName(), fetch() (+15 more)

### Community 7 - "Community 7"
Cohesion: 0.16
Nodes (22): archiveSuffix(), bootstrapEnv(), downloadUV(), ensureUV(), executableName(), extractUVTarGz(), extractUVZip(), fileExists() (+14 more)

### Community 8 - "Community 8"
Cohesion: 0.17
Nodes (20): dirExists(), fileExists(), isComfyRoot(), Resolve(), clean(), ensureSlash(), osaQuote(), Pick() (+12 more)

### Community 9 - "Community 9"
Cohesion: 0.11
Nodes (18): Adding models and workflows, Architecture: Zero Conflict, Configuration, Custom Nodes, DaSiWa ComfyUI Installer, Disclaimer, FFmpeg, Full `config.json` reference (+10 more)

### Community 10 - "Community 10"
Cohesion: 0.13
Nodes (29): Context, LogFunc, Context, Reader, T, FetchList(), log(), ParseLine() (+21 more)

### Community 11 - "Community 11"
Cohesion: 0.33
Nodes (12): download(), exeName(), Install(), installLinux(), installWindows(), LocalInstalled(), log(), safeDest() (+4 more)

### Community 12 - "Community 12"
Cohesion: 0.19
Nodes (14): apiConfig(), apiPathState(), applyConfigPreview(), applyDetectedHardware(), applyExtraSettings(), isPlainObject(), loadConfig(), refreshPathState() (+6 more)

### Community 13 - "Community 13"
Cohesion: 0.58
Nodes (8): checkoutBranch(), dirty(), git(), gitEnv(), log(), Sync(), Context, LogFunc

### Community 14 - "Community 14"
Cohesion: 0.29
Nodes (11): cudaMigrationCase, build(), checkCUDAMigration(), copyFile(), dashIfEmpty(), fatal(), main(), repoRoot() (+3 more)

### Community 15 - "Community 15"
Cohesion: 0.35
Nodes (15): Context, LogFunc, Venv, cmpVersion(), getJSON(), Install(), installRadialNode(), installSpargeLinux() (+7 more)

### Community 16 - "Community 16"
Cohesion: 0.22
Nodes (9): apiQuit(), apiStart(), apiText(), desktopAPI(), isDesktopShell(), openDoc(), sendHeartbeat(), startHeartbeat() (+1 more)

### Community 17 - "Community 17"
Cohesion: 0.25
Nodes (9): buildConfigOverrides(), buildPlan(), deepClone(), editorConfigSeed(), formConfigOverrides(), mergeConfig(), openExtraSettings(), selectedDownloadChoices() (+1 more)

### Community 18 - "Community 18"
Cohesion: 0.25
Nodes (7): Absolute Constraints, AGENTS.md - DaSiWa ComfyUI Installer, Core Invariants, graphify, Important Files, Modification Map, Verification

### Community 19 - "Community 19"
Cohesion: 0.53
Nodes (5): TestResolveComfyUIBasenameStaysDirect(), TestResolveDefaultsToComfyUIUnderRoot(), TestResolveExistingComfyUIRootStaysDirect(), TestResolveExistingParentAppendsComfyUI(), T

### Community 20 - "Community 20"
Cohesion: 0.33
Nodes (6): apiPathList(), escapeHTML(), loadPath(), openPathPicker(), renderPathEntries(), renderRoots()

## Knowledge Gaps
- **61 isolated node(s):** `Hardware`, `appConfig`, `Once`, `Time`, `HandlerFunc` (+56 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Command()` connect `Community 10` to `Community 0`, `Community 1`, `Community 2`, `Community 3`, `Community 7`, `Community 11`, `Community 13`, `Community 14`, `Community 15`?**
  _High betweenness centrality (0.218) - this node is a cross-community bridge._
- **Why does `Run()` connect `Community 1` to `Community 0`, `Community 10`, `Community 2`, `Community 6`?**
  _High betweenness centrality (0.148) - this node is a cross-community bridge._
- **Are the 21 inferred relationships involving `Command()` (e.g. with `outputLogged()` and `runLogged()`) actually correct?**
  _`Command()` has 21 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `Run()` (e.g. with `InstallSelectedWithFS()` and `Create()`) actually correct?**
  _`Run()` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `PlanInstall()` (e.g. with `checkCUDAMigration()` and `contains()`) actually correct?**
  _`PlanInstall()` has 7 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Hardware`, `appConfig`, `Once` to the rest of the system?**
  _61 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.09929078014184398 - nodes in this community are weakly interconnected._