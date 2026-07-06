package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"

	installer "github.com/darksidewalker/dasiwa-comfyui-installer"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/appconfig"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/bootstrap"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/comfypath"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/folderpick"
	gpuinfo "github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/gpuinfo"
	nativeinstall "github.com/darksidewalker/dasiwa-comfyui-installer/internal/native/install"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/pathbrowser"
	"github.com/darksidewalker/dasiwa-comfyui-installer/internal/uistatic"
)

var version = "dev"

const (
	heartbeatInterval = 2 * time.Second
	heartbeatStale    = 7 * time.Second
	browserCloseGrace = 5 * time.Second
)

type appState struct {
	ComfyExists  bool   `json:"comfy_exists"`
	VenvExists   bool   `json:"venv_exists"`
	FFmpegSystem bool   `json:"ffmpeg_system"`
	FFmpegLocal  bool   `json:"ffmpeg_local"`
	ComfyPath    string `json:"comfy_path"`
}

type hardwareReport struct {
	Vendor string `json:"vendor"`
	Name   string `json:"name"`
}

type appConfig struct {
	Python struct {
		DisplayName string `json:"display_name"`
	} `json:"python"`
	Cuda struct {
		Global string `json:"global"`
	} `json:"cuda"`
	ComfyUI struct {
		Version string `json:"version"`
	} `json:"comfyui"`
	URLs struct {
		CustomNodes string `json:"custom_nodes"`
	} `json:"urls"`
	CustomNodes       []string         `json:"custom_nodes"`
	OptionalDownloads []map[string]any `json:"optional_downloads"`
}

type apiConfigResponse struct {
	Config           map[string]any `json:"config"`
	State            appState       `json:"state"`
	Hardware         hardwareReport `json:"hardware"`
	DefaultComfyPath string         `json:"default_comfy_path"`
}

type broker struct {
	mu      sync.Mutex
	clients map[chan string]struct{}
	history []string
}

func newBroker() *broker {
	return &broker{clients: make(map[chan string]struct{})}
}

func (b *broker) add() chan string {
	ch := make(chan string, 128)
	b.mu.Lock()
	for _, line := range b.history {
		ch <- line
	}
	b.clients[ch] = struct{}{}
	b.mu.Unlock()
	return ch
}

func (b *broker) remove(ch chan string) {
	b.mu.Lock()
	delete(b.clients, ch)
	close(ch)
	b.mu.Unlock()
}

func (b *broker) send(line string) {
	b.mu.Lock()
	b.history = append(b.history, line)
	if len(b.history) > 1000 {
		b.history = b.history[len(b.history)-1000:]
	}
	for ch := range b.clients {
		select {
		case ch <- line:
		default:
		}
	}
	b.mu.Unlock()
}

type server struct {
	root             string
	logs             *broker
	installMu        sync.Mutex
	running          bool
	defaultComfyPath string
	httpServer       *http.Server
	shutdownOnce     sync.Once
	heartbeatMu      sync.Mutex
	lastHeartbeat    time.Time
	heartbeatSeen    bool
	closeAfterRun    bool
	closeSignalMu    sync.Mutex
	closeSignalSeq   int
}

func main() {
	rootFlag := flag.String("root", ".", "installer repository root")
	addrFlag := flag.String("addr", "127.0.0.1:0", "listen address")
	showVersion := flag.Bool("version", false, "print version and exit")
	comfyPathFlag := flag.String("comfy-path", "", "default ComfyUI install folder shown in the GUI; absolute or relative to --root")
	flag.Parse()
	if *showVersion {
		fmt.Println(version)
		return
	}

	root, err := filepath.Abs(*rootFlag)
	if err != nil {
		log.Fatal(err)
	}

	app := &server{root: root, logs: newBroker(), defaultComfyPath: strings.TrimSpace(*comfyPathFlag)}
	mux := http.NewServeMux()
	mux.Handle("/", http.FileServer(http.FS(uistatic.Files)))
	mux.HandleFunc("/api/config", app.handleConfig)
	mux.HandleFunc("/api/path-state", app.handlePathState)
	mux.HandleFunc("/api/path/list", app.handlePathList)
	mux.HandleFunc("/api/pick-folder", app.handlePickFolder)
	mux.HandleFunc("/api/start", app.handleStart)
	mux.HandleFunc("/api/logs", app.handleLogs)
	mux.HandleFunc("/api/heartbeat", app.handleHeartbeat)
	mux.HandleFunc("/api/browser-close", app.handleBrowserClose)
	mux.HandleFunc("/api/quit", app.handleQuit)
	mux.HandleFunc("/api/readme", app.handleEmbeddedText("README.md"))
	mux.HandleFunc("/api/license", app.handleEmbeddedText("LICENSE"))

	listener, err := net.Listen("tcp", *addrFlag)
	if err != nil {
		log.Fatal(err)
	}
	url := "http://" + listener.Addr().String() + "/static/index.html"
	fmt.Printf("DaSiWa Installer App %s: %s\n", version, url)
	httpServer := &http.Server{Handler: mux}
	app.httpServer = httpServer
	go app.watchBrowserHeartbeat()
	if os.Getenv("DASIWA_NO_BROWSER") != "1" {
		go openBrowser(url)
	}

	if err := httpServer.Serve(listener); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}

func (s *server) handleConfig(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	data, err := appconfig.LoadMergedJSONWithFallback(s.root, installer.Files)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	var cfg appConfig
	if err := json.Unmarshal(data, &cfg); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	var fullConfig map[string]any
	if err := json.Unmarshal(data, &fullConfig); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defaultPath := s.defaultComfyPathForUI()
	writeJSON(w, apiConfigResponse{Config: fullConfig, State: s.stateForComfy(defaultPath), Hardware: detectHardware(), DefaultComfyPath: defaultPath})
}

func (s *server) handlePathState(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	writeJSON(w, s.stateForComfy(r.URL.Query().Get("path")))
}

func (s *server) stateForComfy(selected string) appState {
	comfyRoot := resolveComfyPath(s.root, selected)
	return appState{
		ComfyExists:  fileExists(filepath.Join(comfyRoot, "main.py")),
		VenvExists:   fileExists(filepath.Join(comfyRoot, "venv")),
		FFmpegSystem: executableInPath("ffmpeg"),
		FFmpegLocal:  fileExists(filepath.Join(comfyRoot, "ffmpeg", "bin", executableName("ffmpeg"))),
		ComfyPath:    comfyRoot,
	}
}

func (s *server) handlePathList(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	writeJSON(w, pathbrowser.List(r.URL.Query().Get("path"), r.URL.Query().Get("mode")))
}

func (s *server) handlePickFolder(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var req struct {
		Initial string `json:"initial"`
	}
	_ = json.NewDecoder(r.Body).Decode(&req)
	initial := req.Initial
	if strings.TrimSpace(initial) == "" {
		initial = s.defaultComfyPathForUI()
	}
	path, err := folderpick.Pick("Select ComfyUI folder", resolveComfyPath(s.root, initial))
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	writeJSON(w, map[string]string{"path": path})
}

func (s *server) handleStart(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var plan map[string]any
	if err := json.NewDecoder(r.Body).Decode(&plan); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	s.installMu.Lock()
	if s.running {
		s.installMu.Unlock()
		http.Error(w, "install already running", http.StatusConflict)
		return
	}
	s.running = true
	s.installMu.Unlock()

	planPath := filepath.Join(s.root, ".dasiwa-app-plan.json")
	encoded, err := json.MarshalIndent(plan, "", "  ")
	if err != nil {
		s.setNotRunning()
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if _, ok := plan["comfy_path"]; !ok && s.defaultComfyPathForUI() != "" {
		plan["comfy_path"] = s.defaultComfyPathForUI()
	}
	encoded, err = json.MarshalIndent(plan, "", "  ")
	if err != nil {
		s.setNotRunning()
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if err := os.WriteFile(planPath, encoded, 0o600); err != nil {
		s.setNotRunning()
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	go s.runInstaller(planPath)
	writeJSON(w, map[string]string{"status": "started"})
}

func (s *server) handleEmbeddedText(path string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		data, err := installer.Files.ReadFile(path)
		if err != nil {
			http.Error(w, err.Error(), http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		_, _ = w.Write(data)
	}
}

func (s *server) handleLogs(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "streaming unsupported", http.StatusInternalServerError)
		return
	}
	ch := s.logs.add()
	defer s.logs.remove(ch)

	for {
		select {
		case <-r.Context().Done():
			return
		case line := <-ch:
			fmt.Fprintf(w, "data: %s\n\n", line)
			flusher.Flush()
		}
	}
}

func (s *server) handleHeartbeat(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	s.heartbeatMu.Lock()
	s.lastHeartbeat = time.Now()
	s.heartbeatSeen = true
	s.heartbeatMu.Unlock()
	writeJSON(w, map[string]string{"status": "ok"})
}

func (s *server) handleBrowserClose(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	signaledAt := time.Now()
	s.closeSignalMu.Lock()
	s.closeSignalSeq++
	seq := s.closeSignalSeq
	s.closeSignalMu.Unlock()
	writeJSON(w, map[string]string{"status": "closing"})
	go s.closeAfterGrace(seq, signaledAt, browserCloseGrace)
}

func (s *server) handleQuit(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	writeJSON(w, map[string]string{"status": "shutting_down"})
	go s.requestShutdown("Quit requested from browser.", true)
}

func (s *server) runInstaller(planPath string) {
	defer s.setNotRunning()
	s.logs.send("Starting installer...")
	runner, err := bootstrap.PreparePython(s.root, s.pythonVersion(planPath), s.logs.send)
	if err != nil {
		s.logs.send("ERROR: " + err.Error())
		return
	}

	ctx := context.Background()
	s.runNativeInstaller(ctx, planPath, runner)
}

func (s *server) runNativeInstaller(ctx context.Context, planPath string, runner *bootstrap.PythonRunner) {
	data, err := os.ReadFile(planPath)
	if err != nil {
		s.logs.send("ERROR: " + err.Error())
		return
	}
	var choices nativeinstall.Choices
	if err := json.Unmarshal(data, &choices); err != nil {
		s.logs.send("ERROR: " + err.Error())
		return
	}
	s.logs.send("Using native Go install engine...")
	if err := nativeinstall.Run(ctx, s.root, choices, runner, s.logs.send); err != nil {
		s.logs.send("Native installer exited with error: " + err.Error())
		return
	}
	s.logs.send("Installer finished successfully.")
	_ = os.Remove(planPath)
}

func (s *server) setNotRunning() {
	s.installMu.Lock()
	s.running = false
	shouldShutdown := s.closeAfterRun
	s.installMu.Unlock()
	if shouldShutdown {
		go s.requestShutdown("Browser closed; installer run finished.", false)
	}
}

func (s *server) watchBrowserHeartbeat() {
	ticker := time.NewTicker(heartbeatInterval)
	defer ticker.Stop()
	for range ticker.C {
		s.heartbeatMu.Lock()
		seen := s.heartbeatSeen
		stale := seen && time.Since(s.lastHeartbeat) > heartbeatStale
		s.heartbeatMu.Unlock()
		if !stale {
			continue
		}
		s.shutdownForLostBrowser("Browser tab closed; shutting down installer.")
		return
	}
}

func (s *server) closeAfterGrace(seq int, signaledAt time.Time, grace time.Duration) {
	time.Sleep(grace)
	s.closeSignalMu.Lock()
	currentSeq := s.closeSignalSeq
	s.closeSignalMu.Unlock()
	if seq != currentSeq {
		return
	}
	s.heartbeatMu.Lock()
	reconnected := s.heartbeatSeen && s.lastHeartbeat.After(signaledAt)
	s.heartbeatMu.Unlock()
	if reconnected {
		return
	}
	s.shutdownForLostBrowser("Browser tab closed; shutting down installer.")
}

func (s *server) shutdownForLostBrowser(reason string) {
	s.installMu.Lock()
	running := s.running
	if running {
		s.closeAfterRun = true
	}
	s.installMu.Unlock()
	if running {
		s.logs.send("Browser tab closed; installer will quit after the current run finishes.")
		return
	}
	go s.requestShutdown(reason, false)
}

func (s *server) requestShutdown(reason string, immediate bool) {
	s.shutdownOnce.Do(func() {
		s.logs.send(reason)
		if immediate {
			time.Sleep(150 * time.Millisecond)
		}
		if s.httpServer == nil {
			return
		}
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		_ = s.httpServer.Shutdown(ctx)
	})
}

func writeJSON(w http.ResponseWriter, value any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(value)
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

func (s *server) defaultComfyPathForUI() string {
	if strings.TrimSpace(s.defaultComfyPath) != "" {
		return s.defaultComfyPath
	}
	return "ComfyUI"
}

func resolveComfyPath(root, selected string) string {
	return comfypath.Resolve(root, selected)
}

func executableInPath(name string) bool {
	_, err := exec.LookPath(executableName(name))
	return err == nil
}

func executableName(name string) string {
	if runtime.GOOS == "windows" {
		return name + ".exe"
	}
	return name
}

func detectHardware() hardwareReport {
	var gpus []gpuinfo.GPU
	if runtime.GOOS == "windows" {
		gpus = gpuinfo.DetectWindows()
	} else {
		gpus = gpuinfo.DetectUnix()
	}
	best := hardwareReport{Vendor: "NVIDIA", Name: "Manual: NVIDIA Modern"}
	bestWeight := -1
	for _, gpu := range gpus {
		vendor := gpuinfo.ClassifyVendor(gpu.Name)
		weight := classifyGPUWeight(vendor)
		if weight > bestWeight {
			best = hardwareReport{Vendor: vendor, Name: gpu.Name}
			bestWeight = weight
		}
	}
	return best
}

func classifyGPUWeight(vendor string) int {
	switch vendor {
	case "NVIDIA":
		return 3
	case "AMD", "INTEL":
		return 2
	default:
		return 0
	}
}

func (s *server) pythonVersion(planPath string) string {
	if version := pythonVersionFromPlan(planPath); version != "" {
		return version
	}
	data, err := appconfig.LoadMergedJSONWithFallback(s.root, installer.Files)
	if err != nil {
		return "3.12"
	}
	var cfg appConfig
	if err := json.Unmarshal(data, &cfg); err != nil || cfg.Python.DisplayName == "" {
		return "3.12"
	}
	return cfg.Python.DisplayName
}

func pythonVersionFromPlan(planPath string) string {
	data, err := os.ReadFile(planPath)
	if err != nil {
		return ""
	}
	var plan struct {
		ConfigOverrides struct {
			Python struct {
				DisplayName string `json:"display_name"`
			} `json:"python"`
		} `json:"config_overrides"`
	}
	if err := json.Unmarshal(data, &plan); err != nil {
		return ""
	}
	return plan.ConfigOverrides.Python.DisplayName
}

func openBrowser(url string) {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "windows":
		cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", url)
	case "darwin":
		cmd = exec.Command("open", url)
	default:
		cmd = exec.Command("xdg-open", url)
	}
	_ = cmd.Start()
	// Give the browser a moment before returning on platforms that detach slowly.
	time.Sleep(300 * time.Millisecond)
}
