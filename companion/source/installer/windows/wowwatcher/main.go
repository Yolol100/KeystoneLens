package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

const (
	errorAlreadyExists             = 183
	th32csSnapProcess              = 0x00000002
	processQueryLimitedInformation = 0x1000
	pollInterval                   = 2 * time.Second
)

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

func acquireSingleInstance() (syscall.Handle, bool) {
	kernel32 := syscall.NewLazyDLL("kernel32.dll")
	createMutex := kernel32.NewProc("CreateMutexW")
	name, _ := syscall.UTF16PtrFromString(`Local\KeystoneLens.WoWWatcher.Singleton`)
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

func processImagePath(pid uint32) string {
	kernel32 := syscall.NewLazyDLL("kernel32.dll")
	openProcess := kernel32.NewProc("OpenProcess")
	queryImage := kernel32.NewProc("QueryFullProcessImageNameW")

	procRaw, _, _ := openProcess.Call(processQueryLimitedInformation, 0, uintptr(pid))
	if procRaw == 0 {
		return ""
	}
	defer syscall.CloseHandle(syscall.Handle(procRaw))

	buf := make([]uint16, 32768)
	size := uint32(len(buf))
	queried, _, _ := queryImage.Call(
		procRaw,
		0,
		uintptr(unsafe.Pointer(&buf[0])),
		uintptr(unsafe.Pointer(&size)),
	)
	if queried == 0 || size == 0 {
		return ""
	}
	return syscall.UTF16ToString(buf[:size])
}

func snapshotProcessIDs(matchName string) []uint32 {
	kernel32 := syscall.NewLazyDLL("kernel32.dll")
	createSnapshot := kernel32.NewProc("CreateToolhelp32Snapshot")
	processFirst := kernel32.NewProc("Process32FirstW")
	processNext := kernel32.NewProc("Process32NextW")

	snapshotRaw, _, _ := createSnapshot.Call(th32csSnapProcess, 0)
	if snapshotRaw == uintptr(syscall.InvalidHandle) {
		return nil
	}
	defer syscall.CloseHandle(syscall.Handle(snapshotRaw))

	var result []uint32
	entry := processEntry32{Size: uint32(unsafe.Sizeof(processEntry32{}))}
	ok, _, _ := processFirst.Call(snapshotRaw, uintptr(unsafe.Pointer(&entry)))
	for ok != 0 {
		name := syscall.UTF16ToString(entry.ExeFile[:])
		if strings.EqualFold(name, matchName) {
			result = append(result, entry.ProcessID)
		}
		entry.Size = uint32(unsafe.Sizeof(processEntry32{}))
		ok, _, _ = processNext.Call(snapshotRaw, uintptr(unsafe.Pointer(&entry)))
	}
	return result
}

func isRetailWoWPath(path string) bool {
	if !strings.EqualFold(filepath.Base(path), "Wow.exe") {
		return false
	}
	clean := filepath.Clean(path)
	for _, part := range strings.Split(clean, string(os.PathSeparator)) {
		if strings.EqualFold(part, "_retail_") {
			return true
		}
	}
	return false
}

func retailWoWPIDs() map[uint32]struct{} {
	result := make(map[uint32]struct{})
	for _, pid := range snapshotProcessIDs("Wow.exe") {
		if isRetailWoWPath(processImagePath(pid)) {
			result[pid] = struct{}{}
		}
	}
	return result
}

func processRunningAtPath(target string) bool {
	targetAbs, err := filepath.Abs(target)
	if err != nil {
		return false
	}
	targetClean := filepath.Clean(targetAbs)
	for _, pid := range snapshotProcessIDs(filepath.Base(targetClean)) {
		actual := processImagePath(pid)
		if actual == "" {
			continue
		}
		actualAbs, err := filepath.Abs(actual)
		if err == nil && strings.EqualFold(filepath.Clean(actualAbs), targetClean) {
			return true
		}
	}
	return false
}

func startCompanion() {
	exe, err := os.Executable()
	if err != nil {
		return
	}
	target := filepath.Join(filepath.Dir(exe), "KeystoneLens.exe")
	if _, err := os.Stat(target); err != nil {
		return
	}
	// Do not invoke the launcher again when the exact installed Companion is
	// already running. The launcher's singleton remains a second safety net, but
	// the watcher should never cause an unnecessary "already running" dialog.
	if processRunningAtPath(target) {
		return
	}
	cmd := exec.Command(target)
	cmd.Dir = filepath.Dir(target)
	if err := cmd.Start(); err == nil && cmd.Process != nil {
		_ = cmd.Process.Release()
	}
}

func main() {
	mutex, acquired := acquireSingleInstance()
	if !acquired {
		return
	}
	defer syscall.CloseHandle(mutex)

	seen := make(map[uint32]struct{})
	for {
		current := retailWoWPIDs()
		for pid := range current {
			if _, existed := seen[pid]; !existed {
				startCompanion()
				break
			}
		}
		seen = current
		time.Sleep(pollInterval)
	}
}
