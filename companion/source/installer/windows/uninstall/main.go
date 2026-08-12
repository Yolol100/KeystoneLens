package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"unsafe"
)

const (
	errorAlreadyExists             = 183
	th32csSnapProcess              = 0x00000002
	processTerminate               = 0x0001
	processQueryLimitedInformation = 0x1000
	synchronize                    = 0x00100000
	createNoWindow                 = 0x08000000
	waitTimeoutMilliseconds        = 5000
	coinitApartmentThreaded        = 0x2
	rpcEChangedMode                = 0x80010106
)

type guid struct {
	Data1 uint32
	Data2 uint16
	Data3 uint16
	Data4 [8]byte
}

type processEntry32 struct {
	Size              uint32
	Usage             uint32
	ProcessID         uint32
	DefaultHeapID     uintptr
	ModuleID          uint32
	Threads           uint32
	ParentProcessID   uint32
	PriorityClassBase int32
	Flags             uint32
	ExeFile           [260]uint16
}

var (
	folderIDLocalAppData = guid{
		Data1: 0xF1B32785, Data2: 0x6FBA, Data3: 0x4FCF,
		Data4: [8]byte{0x9D, 0x55, 0x7B, 0x8E, 0x7F, 0x15, 0x70, 0x91},
	}
	folderIDPrograms = guid{
		Data1: 0xA77F5D77, Data2: 0x2E2B, Data3: 0x44C3,
		Data4: [8]byte{0xA6, 0xA2, 0xAB, 0xA6, 0x01, 0x05, 0x4A, 0x51},
	}
	folderIDStartup = guid{
		Data1: 0xB97D20BB, Data2: 0xF46A, Data3: 0x4C97,
		Data4: [8]byte{0xBA, 0x10, 0x5E, 0x36, 0x08, 0x43, 0x08, 0x54},
	}
	folderIDDesktop = guid{
		Data1: 0xB4BFCC3A, Data2: 0xDB2C, Data3: 0x424C,
		Data4: [8]byte{0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41},
	}
)

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

func initializeCOM() (func(), bool) {
	ole32 := syscall.NewLazyDLL("ole32.dll")
	coInitializeEx := ole32.NewProc("CoInitializeEx")
	coUninitialize := ole32.NewProc("CoUninitialize")
	hr, _, _ := coInitializeEx.Call(0, coinitApartmentThreaded)
	code := uint32(hr)
	if int32(code) >= 0 {
		return func() { coUninitialize.Call() }, true
	}
	// RPC_E_CHANGED_MODE means this thread was already initialized with a
	// different apartment model. COM is still initialized and usable, but this
	// call must not be balanced with CoUninitialize.
	if code == rpcEChangedMode {
		return func() {}, true
	}
	return func() {}, false
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

func systemExecutable(parts ...string) string {
	root := systemDirectory()
	if root == "" {
		return ""
	}
	all := append([]string{root}, parts...)
	return filepath.Join(all...)
}

func box(title, text string, flags uintptr) uintptr {
	user32 := syscall.NewLazyDLL("user32.dll")
	proc := user32.NewProc("MessageBoxW")
	t, _ := syscall.UTF16PtrFromString(text)
	c, _ := syscall.UTF16PtrFromString(title)
	ret, _, _ := proc.Call(0, uintptr(unsafe.Pointer(t)), uintptr(unsafe.Pointer(c)), flags)
	return ret
}

func hidden(name string, args ...string) error {
	if name == "" {
		return syscall.Errno(3)
	}
	cmd := exec.Command(name, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWindow}
	return cmd.Run()
}

func knownFolderPath(id *guid) string {
	shell32 := syscall.NewLazyDLL("shell32.dll")
	ole32 := syscall.NewLazyDLL("ole32.dll")
	getKnownFolderPath := shell32.NewProc("SHGetKnownFolderPath")
	coTaskMemFree := ole32.NewProc("CoTaskMemFree")

	var raw *uint16
	hr, _, _ := getKnownFolderPath.Call(
		uintptr(unsafe.Pointer(id)),
		0,
		0,
		uintptr(unsafe.Pointer(&raw)),
	)
	// Microsoft requires any returned allocation to be released with
	// CoTaskMemFree even when the HRESULT indicates failure.
	if raw != nil {
		defer coTaskMemFree.Call(uintptr(unsafe.Pointer(raw)))
	}
	if int32(uint32(hr)) < 0 || raw == nil {
		return ""
	}
	return syscall.UTF16ToString((*[32768]uint16)(unsafe.Pointer(raw))[:])
}

func terminateExactExecutable(target string) {
	if target == "" {
		return
	}
	target, err := filepath.Abs(target)
	if err != nil {
		return
	}

	kernel32 := syscall.NewLazyDLL("kernel32.dll")
	createSnapshot := kernel32.NewProc("CreateToolhelp32Snapshot")
	processFirst := kernel32.NewProc("Process32FirstW")
	processNext := kernel32.NewProc("Process32NextW")
	openProcess := kernel32.NewProc("OpenProcess")
	queryImage := kernel32.NewProc("QueryFullProcessImageNameW")
	terminate := kernel32.NewProc("TerminateProcess")
	wait := kernel32.NewProc("WaitForSingleObject")

	snapshotRaw, _, _ := createSnapshot.Call(th32csSnapProcess, 0)
	if snapshotRaw == uintptr(syscall.InvalidHandle) {
		return
	}
	snapshot := syscall.Handle(snapshotRaw)
	defer syscall.CloseHandle(snapshot)

	entry := processEntry32{Size: uint32(unsafe.Sizeof(processEntry32{}))}
	ok, _, _ := processFirst.Call(snapshotRaw, uintptr(unsafe.Pointer(&entry)))
	for ok != 0 {
		procRaw, _, _ := openProcess.Call(
			processTerminate|processQueryLimitedInformation|synchronize,
			0,
			uintptr(entry.ProcessID),
		)
		if procRaw != 0 {
			proc := syscall.Handle(procRaw)
			buf := make([]uint16, 32768)
			size := uint32(len(buf))
			queried, _, _ := queryImage.Call(
				procRaw,
				0,
				uintptr(unsafe.Pointer(&buf[0])),
				uintptr(unsafe.Pointer(&size)),
			)
			if queried != 0 {
				actual := syscall.UTF16ToString(buf[:size])
				actualAbs, absErr := filepath.Abs(actual)
				if absErr == nil && strings.EqualFold(filepath.Clean(actualAbs), filepath.Clean(target)) {
					terminate.Call(procRaw, 0)
					wait.Call(procRaw, waitTimeoutMilliseconds)
				}
			}
			syscall.CloseHandle(proc)
		}
		entry.Size = uint32(unsafe.Sizeof(processEntry32{}))
		ok, _, _ = processNext.Call(snapshotRaw, uintptr(unsafe.Pointer(&entry)))
	}
}

func scheduleDirectoryCleanup(root, runtimeRoot, installerCache string) error {
	// Pass paths only through environment variables so path characters can never
	// become PowerShell syntax. The helper starts after this uninstaller exits.
	script := `$ErrorActionPreference='SilentlyContinue'; Start-Sleep -Milliseconds 1400; @($env:KL_REMOVE_APP,$env:KL_REMOVE_RUNTIME,$env:KL_REMOVE_INSTALLER) | Where-Object { $_ } | ForEach-Object { Remove-Item -LiteralPath $_ -Recurse -Force -ErrorAction SilentlyContinue }`
	powershell := systemExecutable("WindowsPowerShell", "v1.0", "powershell.exe")
	if powershell == "" {
		return syscall.Errno(3)
	}
	cmd := exec.Command(
		powershell,
		"-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script,
	)
	cmd.Env = append(os.Environ(),
		"KL_REMOVE_APP="+root,
		"KL_REMOVE_RUNTIME="+runtimeRoot,
		"KL_REMOVE_INSTALLER="+installerCache,
	)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWindow}
	return cmd.Start()
}

func main() {
	// COM initialization is thread-affine. Keep this goroutine on the same OS
	// thread while using SHGetKnownFolderPath, as required by the Known Folder API.
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()

	silent := false
	keepData := true
	keepDataExplicit := false
	for _, arg := range os.Args[1:] {
		switch strings.ToLower(arg) {
		case "--silent", "/s", "/silent":
			silent = true
		case "--purge-data", "/purge-data":
			keepData = false
			keepDataExplicit = true
		case "--keep-data", "/keep-data":
			keepData = true
			keepDataExplicit = true
		}
	}

	maintenance, acquired := acquireMaintenanceMutex()
	if !acquired {
		if !silent {
			box("KeystoneLens", "Another KeystoneLens install, repair, or uninstall is already running.", 0x10)
		}
		os.Exit(2)
	}
	defer syscall.CloseHandle(maintenance)

	cleanupCOM, comOK := initializeCOM()
	if !comOK {
		if !silent {
			box("KeystoneLens", "Windows COM initialization failed. Nothing was removed.", 0x10)
		}
		os.Exit(3)
	}
	defer cleanupCOM()

	if !silent {
		if box("Uninstall KeystoneLens", "Remove KeystoneLens Companion from this PC?", 0x24) != 6 {
			return
		}
		if !keepDataExplicit {
			// Yes keeps preferences/credentials for a later reinstall; No performs
			// a complete user-data cleanup. The default is deliberately non-destructive.
			keepData = box(
				"KeystoneLens settings",
				"Keep your saved KeystoneLens settings for a future reinstall?\n\nYes = keep settings\nNo = remove settings too",
				0x24,
			) == 6
		}
	}

	exe, exeErr := os.Executable()
	if exeErr != nil {
		if !silent {
			box("KeystoneLens", "Uninstall could not verify its installation path.", 0x10)
		}
		os.Exit(3)
	}
	root := filepath.Dir(exe)
	local := knownFolderPath(&folderIDLocalAppData)
	programs := knownFolderPath(&folderIDPrograms)
	startup := knownFolderPath(&folderIDStartup)
	desktop := knownFolderPath(&folderIDDesktop)
	if local == "" || programs == "" || startup == "" || !filepath.IsAbs(local) || !filepath.IsAbs(programs) || !filepath.IsAbs(startup) {
		if !silent {
			box("KeystoneLens", "Windows known-folder paths are unavailable or unsafe. Nothing was removed.", 0x10)
		}
		os.Exit(3)
	}
	expectedRoot := filepath.Join(local, "Programs", "KeystoneLens")
	rootAbs, rootErr := filepath.Abs(root)
	expectedAbs, expectedErr := filepath.Abs(expectedRoot)
	if rootErr != nil || expectedErr != nil || !strings.EqualFold(filepath.Clean(rootAbs), filepath.Clean(expectedAbs)) {
		if !silent {
			box("KeystoneLens", "This uninstaller is not running from the KeystoneLens installation folder. Nothing was removed.", 0x10)
		}
		os.Exit(3)
	}
	runtimeRoot := filepath.Join(local, "Programs", "KeystoneLensRuntime")
	pythonDir := filepath.Join(runtimeRoot, "Python313")
	pythonW := filepath.Join(pythonDir, "pythonw.exe")
	runtimeInstaller := filepath.Join(runtimeRoot, "python-3.13.15-amd64.exe")
	installerCache := filepath.Join(local, "Programs", "KeystoneLensInstaller")
	userData := filepath.Join(local, "KeystoneLens")

	// Stop only processes that belong to this installation. The launcher owns its
	// Python child through a Job Object; the WoW watcher is a separate lightweight
	// helper that must also be stopped before the installation directory is removed.
	terminateExactExecutable(filepath.Join(root, "KeystoneLens.exe"))
	terminateExactExecutable(filepath.Join(root, "KeystoneLens-WoW-Watcher.exe"))
	terminateExactExecutable(pythonW)

	_ = os.Remove(filepath.Join(startup, "KeystoneLens.lnk"))
	_ = os.Remove(filepath.Join(startup, "KeystoneLens-WoW-Watcher.lnk"))
	_ = os.Remove(filepath.Join(programs, "KeystoneLens.lnk"))
	if desktop != "" && filepath.IsAbs(desktop) {
		_ = os.Remove(filepath.Join(desktop, "KeystoneLens.lnk"))
	}
	_ = hidden(systemExecutable("reg.exe"), "delete", `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\KeystoneLens`, "/f")

	// The Python runtime is KeystoneLens-dedicated. Ask the official cached Python
	// installer to unregister it before deleting any leftovers.
	if _, err := os.Stat(runtimeInstaller); err == nil {
		_ = hidden(runtimeInstaller, "/quiet", "/uninstall", "InstallAllUsers=0", "TargetDir="+pythonDir)
	}

	if !keepData {
		_ = os.RemoveAll(userData)
	}

	_ = scheduleDirectoryCleanup(root, runtimeRoot, installerCache)
	if !silent {
		message := "KeystoneLens Companion has been removed."
		if keepData {
			message += " Your saved settings were kept."
		} else {
			message += " Saved settings were removed too."
		}
		box("KeystoneLens", message, 0x40)
	}
}
