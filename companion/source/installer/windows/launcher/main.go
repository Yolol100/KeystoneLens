package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"unsafe"
)

const (
	errorAlreadyExists           = 183
	processTerminate             = 0x0001
	processSetQuota              = 0x0100
	jobObjectExtendedLimitInfo   = 9
	jobObjectLimitKillOnJobClose = 0x00002000
	createNoWindow               = 0x08000000
)

type ioCounters struct {
	ReadOperationCount  uint64
	WriteOperationCount uint64
	OtherOperationCount uint64
	ReadTransferCount   uint64
	WriteTransferCount  uint64
	OtherTransferCount  uint64
}

type basicLimitInformation struct {
	PerProcessUserTimeLimit int64
	PerJobUserTimeLimit     int64
	LimitFlags              uint32
	MinimumWorkingSetSize   uintptr
	MaximumWorkingSetSize   uintptr
	ActiveProcessLimit      uint32
	Affinity                uintptr
	PriorityClass           uint32
	SchedulingClass         uint32
}

type extendedLimitInformation struct {
	BasicLimitInformation basicLimitInformation
	IoInfo                ioCounters
	ProcessMemoryLimit    uintptr
	JobMemoryLimit        uintptr
	PeakProcessMemoryUsed uintptr
	PeakJobMemoryUsed     uintptr
}

func messageBox(title, text string) {
	user32 := syscall.NewLazyDLL("user32.dll")
	proc := user32.NewProc("MessageBoxW")
	t, _ := syscall.UTF16PtrFromString(text)
	c, _ := syscall.UTF16PtrFromString(title)
	proc.Call(0, uintptr(unsafe.Pointer(t)), uintptr(unsafe.Pointer(c)), 0x10)
}

func acquireSingleInstance() (syscall.Handle, bool) {
	kernel32 := syscall.NewLazyDLL("kernel32.dll")
	createMutex := kernel32.NewProc("CreateMutexW")
	name, _ := syscall.UTF16PtrFromString(`Local\KeystoneLens.Companion.Singleton`)
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

func sanitizedEnvironment(root string) []string {
	blocked := map[string]bool{
		"PYTHONPATH":     true,
		"PYTHONHOME":     true,
		"PYTHONSTARTUP":  true,
		"PYTHONUSERBASE": true,
	}
	out := make([]string, 0, len(os.Environ())+5)
	for _, entry := range os.Environ() {
		key, _, found := strings.Cut(entry, "=")
		if found && blocked[strings.ToUpper(key)] {
			continue
		}
		out = append(out, entry)
	}
	out = append(out,
		"KEYSTONELENS_ROOT="+root,
		"PYTHONNOUSERSITE=1",
		"PYTHONDONTWRITEBYTECODE=1",
		"PYTHONUTF8=1",
	)
	return out
}

func createKillOnCloseJob(pid int) (syscall.Handle, error) {
	kernel32 := syscall.NewLazyDLL("kernel32.dll")
	createJob := kernel32.NewProc("CreateJobObjectW")
	setInfo := kernel32.NewProc("SetInformationJobObject")
	openProcess := kernel32.NewProc("OpenProcess")
	assign := kernel32.NewProc("AssignProcessToJobObject")

	rawJob, _, createErr := createJob.Call(0, 0)
	if rawJob == 0 {
		return 0, createErr
	}
	job := syscall.Handle(rawJob)
	info := extendedLimitInformation{}
	info.BasicLimitInformation.LimitFlags = jobObjectLimitKillOnJobClose
	ok, _, setErr := setInfo.Call(
		rawJob,
		jobObjectExtendedLimitInfo,
		uintptr(unsafe.Pointer(&info)),
		unsafe.Sizeof(info),
	)
	if ok == 0 {
		syscall.CloseHandle(job)
		return 0, setErr
	}

	rawProcess, _, openErr := openProcess.Call(processTerminate|processSetQuota, 0, uintptr(uint32(pid)))
	if rawProcess == 0 {
		syscall.CloseHandle(job)
		return 0, openErr
	}
	process := syscall.Handle(rawProcess)
	defer syscall.CloseHandle(process)
	ok, _, assignErr := assign.Call(rawJob, rawProcess)
	if ok == 0 {
		syscall.CloseHandle(job)
		return 0, assignErr
	}
	return job, nil
}

func main() {
	mutex, acquired := acquireSingleInstance()
	if !acquired {
		messageBox("KeystoneLens", "KeystoneLens Companion is already running.")
		return
	}
	defer syscall.CloseHandle(mutex)

	exe, err := os.Executable()
	if err != nil {
		return
	}
	root := filepath.Dir(exe)
	raw, err := os.ReadFile(filepath.Join(root, "pythonw.path"))
	if err != nil {
		messageBox("KeystoneLens", "KeystoneLens runtime is missing. Reinstall or repair KeystoneLens.")
		return
	}
	pythonw := strings.TrimSpace(string(raw))
	if _, err := os.Stat(pythonw); err != nil {
		messageBox("KeystoneLens", "Python runtime is unavailable. Reinstall or repair KeystoneLens.")
		return
	}

	script := `import os,runpy,sys; r=os.environ["KEYSTONELENS_ROOT"]; sys.path[:0]=[os.path.join(r,"app"),os.path.join(r,"packages")]; runpy.run_module("keystonelens_companion", run_name="__main__")`
	cmd := exec.Command(pythonw, "-I", "-c", script)
	cmd.Dir = root
	cmd.Env = sanitizedEnvironment(root)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWindow}
	if err := cmd.Start(); err != nil {
		messageBox("KeystoneLens", "KeystoneLens could not start. Repair the installation and try again.")
		return
	}

	job, err := createKillOnCloseJob(cmd.Process.Pid)
	if err != nil {
		_ = cmd.Process.Kill()
		_, _ = cmd.Process.Wait()
		messageBox("KeystoneLens", "KeystoneLens could not establish a safe process lifecycle. Repair the installation and try again.")
		return
	}
	defer syscall.CloseHandle(job)

	if err := cmd.Wait(); err != nil {
		messageBox("KeystoneLens", "KeystoneLens stopped unexpectedly. Check %LOCALAPPDATA%\\KeystoneLens\\keystonelens.log.")
	}
}
