package main

import (
	_ "embed"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"unsafe"
)

const errorAlreadyExists = 183

//go:embed payload.zip
var payload []byte

//go:embed installer.ps1
var installer []byte

func messageBox(title, text string) {
	user32 := syscall.NewLazyDLL("user32.dll")
	proc := user32.NewProc("MessageBoxW")
	t, _ := syscall.UTF16PtrFromString(text)
	c, _ := syscall.UTF16PtrFromString(title)
	proc.Call(0, uintptr(unsafe.Pointer(t)), uintptr(unsafe.Pointer(c)), 0x10)
}

func silentRequested() bool {
	for _, arg := range os.Args[1:] {
		switch strings.ToLower(arg) {
		case "--silent", "/s", "/silent":
			return true
		}
	}
	return false
}

func fail(temp string, text string, silent bool) {
	_ = os.RemoveAll(temp)
	if !silent {
		messageBox("KeystoneLens Setup", text)
	}
	os.Exit(1)
}

func acquireMaintenanceMutex() (syscall.Handle, bool) {
	kernel32 := syscall.NewLazyDLL("kernel32.dll")
	createMutex := kernel32.NewProc("CreateMutexW")
	name, _ := syscall.UTF16PtrFromString(`Local\KeystoneLens.Maintenance.Singleton`)
	handle, _, callErr := createMutex.Call(0, 0, uintptr(unsafe.Pointer(name)))
	if handle == 0 {
		return 0, false
	}
	if errno, ok := callErr.(syscall.Errno); ok && errno == errorAlreadyExists {
		syscall.CloseHandle(syscall.Handle(handle))
		return 0, false
	}
	return syscall.Handle(handle), true
}

func systemDirectory() string {
	kernel32 := syscall.NewLazyDLL("kernel32.dll")
	getSystemDirectory := kernel32.NewProc("GetSystemDirectoryW")
	buf := make([]uint16, 32768)
	n, _, _ := getSystemDirectory.Call(
		uintptr(unsafe.Pointer(&buf[0])),
		uintptr(len(buf)),
	)
	if n == 0 || n >= uintptr(len(buf)) {
		return ""
	}
	return syscall.UTF16ToString(buf[:n])
}

func systemPowerShell() string {
	root := systemDirectory()
	if root == "" {
		return ""
	}
	return filepath.Join(root, "WindowsPowerShell", "v1.0", "powershell.exe")
}

func main() {
	silent := silentRequested()
	maintenance, acquired := acquireMaintenanceMutex()
	if !acquired {
		if !silent {
			messageBox("KeystoneLens Setup", "Another KeystoneLens install, repair, or uninstall is already running.")
		}
		os.Exit(2)
	}
	defer syscall.CloseHandle(maintenance)

	temp, err := os.MkdirTemp("", "KeystoneLensSetup-")
	if err != nil {
		if !silent {
			messageBox("KeystoneLens Setup", "Setup could not create its temporary working folder.")
		}
		os.Exit(1)
	}
	defer os.RemoveAll(temp)

	payloadPath := filepath.Join(temp, "payload.zip")
	scriptPath := filepath.Join(temp, "installer.ps1")
	resultPath := filepath.Join(temp, "result.txt")
	// Windows PowerShell 5.1 treats BOM-less scripts as the active ANSI code page.
	// Prefix UTF-8 BOM so branded Unicode UI text is decoded deterministically.
	scriptBytes := append([]byte{0xEF, 0xBB, 0xBF}, installer...)
	if os.WriteFile(payloadPath, payload, 0600) != nil || os.WriteFile(scriptPath, scriptBytes, 0600) != nil {
		fail(temp, "Setup could not prepare its installation files.", silent)
	}

	setupSource, _ := os.Executable()
	args := []string{"-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", scriptPath, "-Payload", payloadPath, "-SetupSource", setupSource, "-ResultFile", resultPath}
	for _, arg := range os.Args[1:] {
		switch arg {
		case "--silent", "/S", "/silent":
			args = append(args, "-Silent")
		case "--repair", "/repair":
			args = append(args, "-Repair")
		}
	}

	powershell := systemPowerShell()
	if powershell == "" {
		fail(temp, "Setup could not resolve the trusted Windows system directory.", silent)
	}
	cmd := exec.Command(powershell, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000}
	err = cmd.Run()
	result, _ := os.ReadFile(resultPath)
	status := strings.TrimSpace(string(result))
	if err != nil {
		// Normal installer failures and user cancellation are already presented
		// inside the branded WPF flow. Only show the emergency bootstrap dialog
		// when PowerShell failed before it could write a normal result marker.
		if status == "failed" {
			os.Exit(1)
		}
		if status == "canceled" {
			os.Exit(2)
		}
		fail(temp, "KeystoneLens Setup could not start or finish its installer UI. Your previous installed version was preserved when possible. Please retry the installer.", silent)
	}
}
