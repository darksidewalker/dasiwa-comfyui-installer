package gpuinfo

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"time"
)

// GPU represents detected graphics hardware.
type GPU struct {
	Vendor     string // "NVIDIA", "AMD", "INTEL", "UNKNOWN"
	Name       string // Full GPU name as reported by OS
	IsDiscrete bool   // True if dedicated GPU (not integrated)
	PCIID      string // e.g., "10de:2684" or ""
	Source     string // Which detection method found it
}

// DetectWindows tries multiple sources to find GPUs on Windows.
// Returns up to N GPUs found, preferring discrete over integrated.
func DetectWindows() []GPU {
	var allGPUs []GPU

	// Primary: CIM/WMI (most reliable on modern Windows)
	if cims := detectViaCIM(); len(cims) > 0 {
		allGPUs = append(allGPUs, cims...)
	}

	// Fallback 1: WMIC (older but widely compatible)
	if len(allGPUs) == 0 {
		if wmic := detectViaWMIC(); len(wmic) > 0 {
			allGPUs = append(allGPUs, wmic...)
		}
	}

	// Fallback 2: Registry (deep system info)
	if len(allGPUs) == 0 {
		if reg := detectViaRegistry(); len(reg) > 0 {
			allGPUs = append(allGPUs, reg...)
		}
	}

	// Fallback 3: PnP Devices (PowerShell)
	if len(allGPUs) == 0 {
		if pnp := detectViaPnP(); len(pnp) > 0 {
			allGPUs = append(allGPUs, pnp...)
		}
	}

	// Last resort: DxDiag parsing
	if len(allGPUs) == 0 {
		if dx := detectViaDxDiag(); len(dx) > 0 {
			allGPUs = append(allGPUs, dx...)
		}
	}

	return deduplicateByPCIID(allGPUs)
}

// DetectUnix tries nvidia-smi and lspci to find GPUs on Linux/macOS.
func DetectUnix() []GPU {
	var allGPUs []GPU

	// Primary: nvidia-smi (NVIDIA-specific)
	if smi := detectViaNVidiaSMI(); len(smi) > 0 {
		allGPUs = append(allGPUs, smi...)
	}

	// Secondary: lspci (general PCI enumeration)
	if pci := detectViaLSPCI(); len(pci) > 0 {
		allGPUs = append(allGPUs, pci...)
	}

	return deduplicateByPCIID(allGPUs)
}

// detectViaCIM uses PowerShell Get-CimInstance Win32_VideoController
func detectViaCIM() []GPU {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, "powershell", "-NoProfile", "-Command",
		"Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name")
	out, err := cmd.Output()
	if err != nil {
		return nil
	}

	lines := splitNonEmptyLines(string(out))
	if len(lines) == 0 {
		return nil
	}

	var gpus []GPU
	for _, name := range lines {
		gpus = append(gpus, GPU{
			Vendor:     classifyVendor(name),
			Name:       strings.TrimSpace(name),
			IsDiscrete: isDiscreteHeuristic(name),
			Source:     "cim",
		})
	}
	return gpus
}

// detectViaWMIC uses wmic command (deprecated but still works)
func detectViaWMIC() []GPU {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, "wmic", "path", "win32_videocontroller", "get", "name", "/format:list")
	out, err := cmd.Output()
	if err != nil {
		return nil
	}

	// Parse "Name: ..." lines from wmic output
	re := regexp.MustCompile(`(?m)^Name:\s*(.+)$`)
	matches := re.FindAllStringSubmatch(string(out), -1)

	var gpus []GPU
	for _, match := range matches {
		name := strings.TrimSpace(match[1])
		if name != "" {
			gpus = append(gpus, GPU{
				Vendor:     classifyVendor(name),
				Name:       name,
				IsDiscrete: isDiscreteHeuristic(name),
				Source:     "wmic",
			})
		}
	}
	return gpus
}

// detectViaRegistry queries HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}
func detectViaRegistry() []GPU {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Query registry via PowerShell
	psCmd := `$regPath = "HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
if (Test-Path $regPath) {
    Get-ChildItem $regPath -ErrorAction SilentlyContinue | ForEach-Object {
        $desc = $_.GetValue("DriverDesc")
        if ($desc) { Write-Output $desc }
    }
}`

	cmd := exec.CommandContext(ctx, "powershell", "-NoProfile", "-Command", psCmd)
	out, err := cmd.Output()
	if err != nil {
		return nil
	}

	lines := splitNonEmptyLines(string(out))
	if len(lines) == 0 {
		return nil
	}

	var gpus []GPU
	for _, name := range lines {
		gpus = append(gpus, GPU{
			Vendor:     classifyVendor(name),
			Name:       strings.TrimSpace(name),
			IsDiscrete: isDiscreteHeuristic(name),
			Source:     "registry",
		})
	}
	return gpus
}

// detectViaPnP uses Get-PnpDevice to enumerate display adapters
func detectViaPnP() []GPU {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	psCmd := `Get-PnpDevice -Class Display -Status OK | Select-Object -ExpandProperty FriendlyName`
	cmd := exec.CommandContext(ctx, "powershell", "-NoProfile", "-Command", psCmd)
	out, err := cmd.Output()
	if err != nil {
		return nil
	}

	lines := splitNonEmptyLines(string(out))
	if len(lines) == 0 {
		return nil
	}

	var gpus []GPU
	for _, name := range lines {
		gpus = append(gpus, GPU{
			Vendor:     classifyVendor(name),
			Name:       strings.TrimSpace(name),
			IsDiscrete: isDiscreteHeuristic(name),
			Source:     "pnpp",
		})
	}
	return gpus
}

// detectViaDxDiag parses dxdiag output for GPU information
func detectViaDxDiag() []GPU {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Run dxdiag and capture output
	cmd := exec.CommandContext(ctx, "dxdiag", "/t", "dxdiag.txt")
	err := cmd.Run()
	if err != nil {
		return nil
	}

	// Read the generated file
	content, readErr := os.ReadFile("dxdiag.txt")
	if readErr != nil {
		return nil
	}

	defer func() {
		os.Remove("dxdiag.txt") // Clean up
	}()

	// Parse GPU names from dxdiag output
	text := string(content)

	// Look for lines like "Name: Radeon RX 7900 XTX"
	nameRe := regexp.MustCompile(`(?im)^Name:\s*(.+)$`)
	names := nameRe.FindAllStringSubmatch(text, -1)

	var gpus []GPU
	for _, match := range names {
		name := strings.TrimSpace(match[1])
		if name != "" && !strings.Contains(strings.ToUpper(name), "DISPLAY") {
			gpus = append(gpus, GPU{
				Vendor:     classifyVendor(name),
				Name:       name,
				IsDiscrete: isDiscreteHeuristic(name),
				Source:     "dxdiag",
			})
		}
	}
	return gpus
}

// detectViaNVidiaSMI uses nvidia-smi --query-gpu=name
func detectViaNVidiaSMI() []GPU {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	smiPath, err := exec.LookPath("nvidia-smi")
	if err != nil {
		return nil
	}

	cmd := exec.CommandContext(ctx, smiPath, "--query-gpu=name", "--format=csv,noheader")
	out, err := cmd.Output()
	if err != nil {
		return nil
	}

	lines := splitNonEmptyLines(string(out))
	if len(lines) == 0 {
		return nil
	}

	var gpus []GPU
	for _, name := range lines {
		gpus = append(gpus, GPU{
			Vendor:     "NVIDIA",
			Name:       strings.TrimSpace(name),
			IsDiscrete: true, // nvidia-smi only shows discrete cards
			Source:     "nvidia-smi",
		})
	}
	return gpus
}

// detectViaLSPCI enumerates PCI devices for VGA controllers
func detectViaLSPCI() []GPU {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	lspciPath, err := exec.LookPath("lspci")
	if err != nil {
		return nil
	}

	cmd := exec.CommandContext(ctx, lspciPath)
	out, err := cmd.Output()
	if err != nil {
		return nil
	}

	lines := splitNonEmptyLines(string(out))
	var gpus []GPU

	for _, line := range lines {
		up := strings.ToUpper(line)
		if strings.Contains(up, "VGA") || strings.Contains(up, "3D") || strings.Contains(up, "DISPLAY") {
			parts := strings.SplitN(line, ": ", 2)
			if len(parts) == 2 {
				name := strings.TrimSpace(parts[1])
				gpus = append(gpus, GPU{
					Vendor:     classifyVendor(name),
					Name:       name,
					PCIID:      extractPCIID(parts[0]),
					IsDiscrete: true, // PCI enumeration shows actual hardware
					Source:     "lspci",
				})
			}
		}
	}
	return gpus
}

// ClassifyVendor determines GPU vendor from name (exported for use in main.go)
func ClassifyVendor(name string) string {
	up := strings.ToUpper(name)
	switch {
	case strings.Contains(up, "NVIDIA"):
		return "NVIDIA"
	case strings.Contains(up, "AMD") || strings.Contains(up, "RADEON"):
		return "AMD"
	case strings.Contains(up, "ARC"):
		return "INTEL"
	case strings.Contains(up, "INTEL"):
		return "INTEL"
	default:
		return "UNKNOWN"
	}
}

// classifyVendor determines GPU vendor from name (private alias for internal use)
func classifyVendor(name string) string {
	return ClassifyVendor(name)
}

// isDiscreteHeuristic guesses if GPU is dedicated based on name patterns
func isDiscreteHeuristic(name string) bool {
	up := strings.ToUpper(name)
	
	// Common iGPU indicators
	iGPUIndicators := []string{
		"INTEGRATED", "UH", "HD GRAPHICS", "IRIS", "MOBILE", 
		"APU", "Radeon Vega", "Radeon Graphics", "Intel UHD",
		"Intel HD", "Intel Iris", "AMD APU",
	}
	
	for _, indicator := range iGPUIndicators {
		if strings.Contains(up, indicator) {
			return false
		}
	}
	
	// Check for explicit discrete indicators
	discreteIndicators := []string{
		"RX", "RTX", "GTX", "TI", "XTX", "SUPER", "PROFESSIONAL",
		"GAMING", "STRIX", "TUF", "ROG", "STRIX",
	}
	
	for _, indicator := range discreteIndicators {
		if strings.Contains(up, indicator) {
			return true
		}
	}
	
	// Default to true if we have a specific model number pattern
	modelPattern := regexp.MustCompile(`(RX|RTX|GTX)\s*\d+[A-Z]?`)
	if modelPattern.MatchString(up) {
		return true
	}
	
	// Unknown case - assume discrete if vendor is NVIDIA/AMD
	return strings.Contains(up, "NVIDIA") || strings.Contains(up, "AMD") || strings.Contains(up, "RADEON")
}

// extractPCIID extracts PCI ID from lspci output format "XX:XX.X Class: Name"
func extractPCIID(line string) string {
	// Format: "01:00.0 VGA compatible controller: Advanced Micro Devices, Inc. [AMD/ATI]"
	idx := strings.Index(line, ": ")
	if idx == -1 {
		return ""
	}
	pciPart := strings.TrimSpace(line[:idx])
	
	// Extract hex IDs from PCI address like "01:00.0"
	re := regexp.MustCompile(`([0-9a-fA-F]{2}):([0-9a-fA-F]{2})`)
	match := re.FindStringSubmatch(pciPart)
	if len(match) >= 3 {
		return fmt.Sprintf("%s:%s", match[1], match[2])
	}
	return ""
}

// deduplicateByPCIID removes duplicate GPUs based on PCI ID or name similarity
func deduplicateByPCIID(gpus []GPU) []GPU {
	if len(gpus) <= 1 {
		return gpus
	}
	
	seen := make(map[string]bool)
	var unique []GPU
	
	for _, gpu := range gpus {
		key := gpu.PCIID
		if key == "" {
			key = strings.ToLower(gpu.Name)
		}
		
		if !seen[key] {
			seen[key] = true
			unique = append(unique, gpu)
		}
	}
	
	return unique
}

// splitNonEmptyLines splits text into non-empty trimmed lines
func splitNonEmptyLines(text string) []string {
	var lines []string
	for _, line := range strings.Split(text, "\n") {
		line = strings.TrimSpace(line)
		if line != "" {
			lines = append(lines, line)
		}
	}
	return lines
}
