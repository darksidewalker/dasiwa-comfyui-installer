const form = document.querySelector("#planForm");
const statusEl = document.querySelector("#status");
const reviewEl = document.querySelector("#review");
const logEl = document.querySelector("#log");
const startBtn = document.querySelector("#startBtn");
const wipeConfirm = document.querySelector("#wipeConfirm");
const downloadsList = document.querySelector("#downloadsList");
const phasePreview = document.querySelector("#phasePreview");
const planBadge = document.querySelector("#planBadge");
const docDialog = document.querySelector("#docDialog");
const docTitle = document.querySelector("#docTitle");
const docBody = document.querySelector("#docBody");
const pathDialog = document.querySelector("#pathDialog");
const pathCurrent = document.querySelector("#pathCurrent");
const pathRoots = document.querySelector("#pathRoots");
const pathEntries = document.querySelector("#pathEntries");
const pathUp = document.querySelector("#pathUp");
const extraSettingsBtn = document.querySelector("#extraSettingsBtn");
const settingsDialog = document.querySelector("#settingsDialog");
const settingsEditor = document.querySelector("#settingsEditor");
const settingsError = document.querySelector("#settingsError");
let configData = null;
let currentState = null;
let stateTimer = null;
let picker = { target: "", mode: "directory", selected: "", parent: "" };
let extraSettingsConfig = null;

function desktopAPI() {
  if (!window.go) return null;
  if (window.go.main?.DesktopApp) return window.go.main.DesktopApp;
  for (const packageName of Object.keys(window.go)) {
    const pkg = window.go[packageName];
    for (const structName of Object.keys(pkg || {})) {
      const candidate = pkg[structName];
      if (
        candidate?.Config &&
        candidate?.PathState &&
        (candidate?.PickFolder || candidate?.PickComfyFolder) &&
        candidate?.Start
      ) {
        return candidate;
      }
    }
  }
  return null;
}

function isDesktopShell() {
  return (
    location.protocol === "wails:" ||
    Boolean(window.WailsInvoke || window.runtime || window.go)
  );
}

function wailsReady() {
  return Boolean(window.WailsInvoke || window.runtime || window.go);
}

async function waitForDesktopAPI() {
  const existing = desktopAPI();
  if (existing || !isDesktopShell()) return existing;
  const deadline = Date.now() + 2500;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 50));
    const api = desktopAPI();
    if (api) return api;
  }
  return null;
}

function availableBindings() {
  if (!window.go) return "none";
  const names = [];
  for (const packageName of Object.keys(window.go)) {
    for (const structName of Object.keys(window.go[packageName] || {})) {
      names.push(`${packageName}.${structName}`);
    }
  }
  return names.length ? names.join(", ") : "window.go is empty";
}

async function apiConfig() {
  const api = await waitForDesktopAPI();
  if (api) return api.Config();
  const res = await fetch("/api/config");
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function apiPathState(path) {
  const api = await waitForDesktopAPI();
  if (api) return api.PathState(path);
  const res = await fetch(`/api/path-state?path=${encodeURIComponent(path)}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function apiPathList(path, mode) {
  const api = await waitForDesktopAPI();
  if (api?.PathList) return api.PathList(path || "", mode || "directory");
  const params = new URLSearchParams({
    path: path || "",
    mode: mode || "directory",
  });
  const res = await fetch(`/api/path/list?${params.toString()}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function apiStart(plan) {
  const api = await waitForDesktopAPI();
  if (api) {
    await api.Start(plan);
    return;
  }
  const res = await fetch("/api/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(plan),
  });
  if (!res.ok) throw new Error(await res.text());
}

async function apiQuit() {
  const api = await waitForDesktopAPI();
  if (api?.Quit) {
    await api.Quit();
    return;
  }
  const res = await fetch("/api/quit", { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
}

function sendHeartbeat() {
  if (isDesktopShell()) return;
  fetch("/api/heartbeat", {
    method: "POST",
    keepalive: true,
  }).catch(() => {});
}

function startHeartbeat() {
  sendHeartbeat();
  setInterval(sendHeartbeat, 2000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") sendHeartbeat();
  });
}

async function apiText(path) {
  const api = await waitForDesktopAPI();
  if (api && path === "/api/readme") return api.Readme();
  if (api && path === "/api/license") return api.License();
  const res = await fetch(path);
  if (!res.ok) throw new Error(await res.text());
  return res.text();
}

function selectedMode() {
  return document.querySelector('input[name="install_mode"]:checked').value;
}

function selectedDownloadChoices() {
  return [...document.querySelectorAll(".download-choice:checked")].map(
    (input) => ({
      index: Number.parseInt(input.value, 10),
      name: input.dataset.name || "",
    }),
  );
}

function deepClone(value) {
  return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
}

function isPlainObject(value) {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value)
  );
}

function mergeConfig(base, override) {
  const merged = deepClone(base || {});
  if (!isPlainObject(override)) return merged;
  for (const [key, value] of Object.entries(override)) {
    if (value === undefined) continue;
    if (isPlainObject(value) && isPlainObject(merged[key])) {
      merged[key] = mergeConfig(merged[key], value);
    } else {
      merged[key] = deepClone(value);
    }
  }
  return merged;
}

function formConfigOverrides() {
  const pythonDisplay = document.querySelector("#python_display").value.trim();
  const targetVersion = document.querySelector("#target_version").value.trim();
  const cudaTarget = document.querySelector("#cuda_target").value.trim();
  const customNodesURL = document
    .querySelector("#custom_nodes_url")
    .value.trim();
  const overrides = {};
  if (pythonDisplay) overrides.python = { display_name: pythonDisplay };
  if (targetVersion) overrides.comfyui = { version: targetVersion };
  if (cudaTarget) overrides.cuda = { global: cudaTarget };
  if (customNodesURL) overrides.urls = { custom_nodes: customNodesURL };
  return overrides;
}

function buildConfigOverrides() {
  return mergeConfig(extraSettingsConfig || {}, formConfigOverrides());
}

function buildPlan() {
  const comfyPath = document.querySelector("#comfy_path").value.trim();
  const targetVersion = document.querySelector("#target_version").value.trim();
  const cudaTarget = document.querySelector("#cuda_target").value.trim();
  const mode = selectedMode();
  const downloadChoices = selectedDownloadChoices();
  const downloadIndices = downloadChoices
    .map((choice) => choice.index)
    .filter(Number.isInteger);
  const downloadNames = downloadChoices
    .map((choice) => choice.name)
    .filter(Boolean);
  return {
    install_mode: mode,
    confirm_wipe:
      mode !== "wipe" || document.querySelector("#confirm_wipe").checked,
    hw: {
      vendor: document.querySelector("#vendor").value,
      name:
        document.querySelector("#gpuName").value.trim() ||
        `Manual: ${document.querySelector("#vendor").value}`,
    },
    want_sage: document.querySelector("#want_sage").checked,
    want_radial: document.querySelector("#want_radial").checked,
    want_ffmpeg: document.querySelector("#want_ffmpeg").checked,
    comfy_path: comfyPath || undefined,
    target_version: targetVersion || undefined,
    cuda_target: cudaTarget || undefined,
    config_overrides: buildConfigOverrides(),
    downloads: downloadIndices.length ? "selected" : "none",
    download_indices: downloadIndices,
    download_names: downloadNames,
  };
}

function refreshReview() {
  const plan = buildPlan();
  wipeConfirm.classList.toggle("hidden", plan.install_mode !== "wipe");
  startBtn.disabled = plan.install_mode === "wipe" && !plan.confirm_wipe;
  reviewEl.textContent = JSON.stringify(plan, null, 2);
  planBadge.textContent = `${plan.install_mode} · ${plan.download_indices.length} downloads`;
  renderPhases(plan);
}

function renderPhases(plan) {
  const needsVenv =
    ["fresh", "refresh", "wipe"].includes(plan.install_mode) ||
    !currentState?.venv_exists;
  const phases = [
    ["sync ComfyUI", true],
    ["create/rebuild venv", needsVenv],
    ["downloads", plan.download_indices.length > 0],
    ["torch", true],
    ["ComfyUI requirements", true],
    ["ffmpeg", plan.want_ffmpeg],
    ["custom nodes", true],
    ["priority packages", true],
    ["sage", plan.want_sage],
    ["radial", plan.want_radial],
  ];
  phasePreview.textContent = "";
  phases.forEach(([name, enabled]) => {
    const chip = document.createElement("span");
    chip.className = enabled ? "phase on" : "phase";
    chip.textContent = enabled ? `✓ ${name}` : `– ${name}`;
    phasePreview.append(chip);
  });
}

function renderDownloads(items) {
  downloadsList.textContent = "";
  if (!items.length) {
    downloadsList.innerHTML =
      '<p class="hint">No optional downloads configured.</p>';
    return;
  }
  items.forEach((item, index) => {
    const label = document.createElement("label");
    label.className = "download-item";

    const input = document.createElement("input");
    input.type = "checkbox";
    input.className = "download-choice";
    input.value = String(index);
    input.dataset.name = item.name || "";

    const text = document.createElement("span");
    text.className = "download-text";

    const name = document.createElement("b");
    name.className = "download-name";
    name.textContent = item.name || "Unnamed download";
    text.append(name);

    const metaText = item.description || item.type || item.kind || "";
    if (metaText) {
      const meta = document.createElement("small");
      meta.className = "download-meta";
      meta.textContent = item.type ? `Destination: ${metaText}` : metaText;
      text.append(meta);
    }

    label.append(input, text);
    downloadsList.append(label);
  });
}

function applyDetectedHardware(report) {
  if (!report) return;
  const vendor = report.vendor || "NVIDIA";
  document.querySelector("#vendor").value = vendor;
  document.querySelector("#gpuName").value = report.name || `Manual: ${vendor}`;
  document.querySelector("#gpuHint").textContent = report.name
    ? "Detected GPU loaded. Edit if wrong; use Manual: NVIDIA GTX 10 for Pascal cards."
    : "Auto-detect failed; choose manually.";
}

async function refreshPathState() {
  const path = document.querySelector("#comfy_path").value.trim();
  const state = await apiPathState(path);
  currentState = state;
  updateStateCards(state, configData?.hardware);
  document.querySelector('input[value="fresh"]').checked = !state.comfy_exists;
  document.querySelector('input[value="update"]').checked = state.comfy_exists;
  statusEl.textContent = state.comfy_exists
    ? "Existing install detected at selected folder"
    : `Ready for fresh install at ${state.comfy_path || path}`;
  refreshReview();
}

function queuePathStateRefresh() {
  clearTimeout(stateTimer);
  stateTimer = setTimeout(() => {
    refreshPathState().catch(() => {});
  }, 250);
}

function updateStateCards(state, hardware) {
  document.querySelector("#stateComfy").textContent = state.comfy_exists
    ? "installed"
    : "will create";
  document.querySelector("#stateVenv").textContent = state.venv_exists
    ? "present"
    : "missing";
  document.querySelector("#stateFFmpeg").textContent = state.ffmpeg_system
    ? "system PATH"
    : state.ffmpeg_local
      ? "portable"
      : "missing";
  document.querySelector("#stateGPU").textContent = hardware?.name || "manual";
}

async function loadConfig() {
  configData = await apiConfig();
  const cfg = configData.config;
  const state = configData.state;
  currentState = state;
  const comfyPathInput = document.querySelector("#comfy_path");
  comfyPathInput.value = configData.default_comfy_path || "ComfyUI";
  applyDetectedHardware(configData.hardware);
  updateStateCards(state, configData.hardware);
  renderDownloads(cfg.optional_downloads || []);
  document.querySelector("#python_display").placeholder =
    cfg.python?.display_name || "3.12";
  document.querySelector("#comfy_path").placeholder = "ComfyUI";
  document.querySelector("#target_version").placeholder =
    cfg.comfyui?.version || "latest";
  document.querySelector("#cuda_target").placeholder =
    cfg.cuda?.global || "auto";
  document.querySelector("#custom_nodes_url").placeholder =
    cfg.urls?.custom_nodes || "optional remote node list URL";
  document.querySelector('input[value="fresh"]').checked = !state.comfy_exists;
  document.querySelector('input[value="update"]').checked = state.comfy_exists;
  if (state.ffmpeg_system || state.ffmpeg_local) {
    document.querySelector("#want_ffmpeg").checked = false;
  }
  statusEl.textContent = state.comfy_exists
    ? "Existing install detected at selected folder"
    : `Ready for fresh install at ${state.comfy_path || comfyPathInput.value}`;
  refreshReview();
}

function editorConfigSeed() {
  return mergeConfig(
    mergeConfig(configData?.config || {}, extraSettingsConfig || {}),
    formConfigOverrides(),
  );
}

function updateExtraSettingsState() {
  extraSettingsBtn.textContent = extraSettingsConfig
    ? "Extra Settings *"
    : "Extra Settings";
}

function applyConfigPreview(config) {
  if (Array.isArray(config.optional_downloads)) {
    renderDownloads(config.optional_downloads);
  } else if (Array.isArray(configData?.config?.optional_downloads)) {
    renderDownloads(configData.config.optional_downloads);
  }
  document.querySelector("#python_display").placeholder =
    config.python?.display_name || "3.12";
  document.querySelector("#target_version").placeholder =
    config.comfyui?.version || "latest";
  document.querySelector("#cuda_target").placeholder =
    config.cuda?.global || "auto";
  document.querySelector("#custom_nodes_url").placeholder =
    config.urls?.custom_nodes || "optional remote node list URL";
}

function openExtraSettings() {
  settingsError.textContent = "";
  settingsEditor.value = JSON.stringify(editorConfigSeed(), null, 2);
  settingsDialog.showModal();
}

function applyExtraSettings() {
  let parsed;
  try {
    parsed = JSON.parse(settingsEditor.value);
  } catch (err) {
    settingsError.textContent = `Invalid JSON: ${err.message}`;
    return;
  }
  if (!isPlainObject(parsed)) {
    settingsError.textContent = "Top-level JSON must be an object.";
    return;
  }
  extraSettingsConfig = parsed;
  settingsError.textContent = "";
  applyConfigPreview(parsed);
  updateExtraSettingsState();
  refreshReview();
  settingsDialog.close();
}

function resetExtraSettings() {
  extraSettingsConfig = null;
  settingsError.textContent = "";
  settingsEditor.value = JSON.stringify(configData?.config || {}, null, 2);
  applyConfigPreview(configData?.config || {});
  updateExtraSettingsState();
  refreshReview();
}

async function openDoc(title, path) {
  docTitle.textContent = title;
  docBody.textContent = await apiText(path);
  docDialog.showModal();
}

async function openPathPicker(target, mode = "directory") {
  const input = document.querySelector(`#${target}`);
  picker = { target, mode, selected: input?.value || "", parent: "" };
  pathDialog.showModal();
  await loadPath(picker.selected, picker.mode);
}

async function loadPath(path, mode = picker.mode) {
  const data = await apiPathList(path || "", mode);
  pathCurrent.value = data.path || "";
  picker.selected = data.path || "";
  picker.parent = data.parent || "";
  renderRoots(data.roots || []);
  renderPathEntries(data.entries || []);
}

function renderRoots(roots) {
  pathRoots.textContent = "";
  for (const root of roots) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = root.name;
    button.addEventListener("click", () => loadPath(root.path));
    pathRoots.append(button);
  }
}

function renderPathEntries(entries) {
  pathEntries.textContent = "";
  pathUp.onclick = () => loadPath(picker.parent || pathCurrent.value);
  for (const entry of entries) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `path-entry ${entry.isDir ? "directory" : "file"}`;
    row.innerHTML = `<span>${entry.isDir ? "/" : ""}${escapeHTML(entry.name)}</span><small>${escapeHTML(entry.path)}</small>`;
    row.addEventListener("click", () => {
      picker.selected = entry.path;
      pathCurrent.value = entry.path;
      if (entry.isDir) loadPath(entry.path);
    });
    row.addEventListener("dblclick", () => {
      if (!entry.isDir || picker.mode === "directory") chooseCurrentPath();
    });
    pathEntries.append(row);
  }
}

function chooseCurrentPath() {
  const input = document.querySelector(`#${picker.target}`);
  if (!input) return;
  input.value = pathCurrent.value || picker.selected;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
  closePathPicker();
}

function closePathPicker() {
  if (pathDialog.open) pathDialog.close();
}

function escapeHTML(value) {
  return String(value).replace(
    /[&<>'"]/g,
    (char) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "'": "&#39;",
        '"': "&quot;",
      })[char],
  );
}

function handleLogLine(line) {
  const span = document.createElement("span");
  let className = "";
  const lower = line.toLowerCase();
  if (lower.startsWith("error:") || lower.includes("failed") || lower.includes("exit status") || lower.includes("error compiling")) {
    className = "log-error";
  } else if (lower.includes("warning:") || lower.includes("warning ") || lower.startsWith("warning")) {
    className = "log-warning";
  } else if (lower.includes("successfully") || lower.includes("complete") || lower.includes("skip") || lower.includes("already installed")) {
    className = "log-success";
  }
  if (className) {
    span.className = className;
  }
  span.textContent = `${line}\n`;
  logEl.appendChild(span);
  logEl.scrollTop = logEl.scrollHeight;

  if (line.includes("Installer finished successfully.")) {
    statusEl.textContent = "Install finished";
    startBtn.disabled = false;
  } else if (line.startsWith("ERROR:") || line.includes("exited with error")) {
    statusEl.textContent = "Install failed";
    startBtn.disabled = false;
  }
}

function attachLogs() {
  if (window.runtime?.EventsOn) {
    window.runtime.EventsOn("installer-log", handleLogLine);
    return;
  }
  const events = new EventSource("/api/logs");
  events.onmessage = (event) => handleLogLine(event.data);
  events.onerror = () => {
    statusEl.textContent = "Log stream disconnected";
  };
}

document.addEventListener("input", refreshReview);
document.addEventListener("change", refreshReview);
document
  .querySelector("#comfy_path")
  .addEventListener("input", queuePathStateRefresh);

document.querySelector("#pickComfyPath").addEventListener("click", async () => {
  try {
    await openPathPicker("comfy_path", "directory");
  } catch (err) {
    alert((err.message || String(err)).trim());
  }
});

document.querySelector("#pathGo").addEventListener("click", () => {
  loadPath(pathCurrent.value).catch((err) => alert(err.message || String(err)));
});
document
  .querySelector("#pathChoose")
  .addEventListener("click", chooseCurrentPath);
document
  .querySelector("#pathCancel")
  .addEventListener("click", closePathPicker);
document.querySelector("#pathClose").addEventListener("click", closePathPicker);
pathCurrent.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    loadPath(pathCurrent.value).catch((err) =>
      alert(err.message || String(err)),
    );
  }
});

document.querySelector("#selectAllDownloads").addEventListener("click", () => {
  document.querySelectorAll(".download-choice").forEach((input) => {
    input.checked = true;
  });
  refreshReview();
});

document.querySelector("#selectNoDownloads").addEventListener("click", () => {
  document.querySelectorAll(".download-choice").forEach((input) => {
    input.checked = false;
  });
  refreshReview();
});

document.querySelector("#clearLog").addEventListener("click", () => {
  logEl.textContent = "";
});

document.querySelector("#readmeBtn").addEventListener("click", async () => {
  try {
    await openDoc("README", "/api/readme");
  } catch (err) {
    alert(err.message);
  }
});

document.querySelector("#licenseBtn").addEventListener("click", async () => {
  try {
    await openDoc("License", "/api/license");
  } catch (err) {
    alert(err.message);
  }
});

document.querySelector("#quitBtn").addEventListener("click", async () => {
  try {
    statusEl.textContent = "Shutting down…";
    await apiQuit();
  } catch (err) {
    statusEl.textContent = "Shutdown failed";
    alert(err.message || String(err));
  }
});

extraSettingsBtn.addEventListener("click", openExtraSettings);
document
  .querySelector("#settingsClose")
  .addEventListener("click", () => settingsDialog.close());
document
  .querySelector("#settingsApply")
  .addEventListener("click", applyExtraSettings);
document
  .querySelector("#settingsReset")
  .addEventListener("click", resetExtraSettings);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const plan = buildPlan();
  if (plan.install_mode === "wipe" && !plan.confirm_wipe) {
    alert("Confirm the wipe before starting.");
    return;
  }
  startBtn.disabled = true;
  statusEl.textContent = "Starting…";
  logEl.textContent = "";
  try {
    await apiStart(plan);
  } catch (err) {
    statusEl.textContent = "Failed to start";
    startBtn.disabled = false;
    alert(err.message || String(err));
    return;
  }
  statusEl.textContent = "Installer running";
});

attachLogs();
startHeartbeat();
loadConfig().catch((err) => {
  statusEl.textContent = "Config load failed";
  logEl.textContent = err.message;
});
