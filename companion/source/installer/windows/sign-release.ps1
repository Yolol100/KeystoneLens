param(
    [string]$CertThumbprint = '',
    [string]$PfxPath = '',
    [string]$TimestampUrl = 'https://timestamp.digicert.com'
)
$ErrorActionPreference = 'Stop'
$Version = '0.12.7'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Build = Join-Path $PSScriptRoot 'build'
$Payload = Join-Path $Build 'payload'
$Setup = Join-Path $Build 'KeystoneLens-Setup.exe'
$Launcher = Join-Path $Payload 'KeystoneLens.exe'
$Uninstaller = Join-Path $Payload 'KeystoneLens-Uninstall.exe'
$WoWWatcher = Join-Path $Payload 'KeystoneLens-WoW-Watcher.exe'

if (-not (Get-Command signtool.exe -ErrorAction SilentlyContinue)) { throw 'signtool.exe is required from the Windows SDK.' }
if (-not (Get-Command go.exe -ErrorAction SilentlyContinue)) { throw 'Go is required to rebuild the signed bootstrap.' }
if (-not (Get-Command python.exe -ErrorAction SilentlyContinue)) { throw 'Python is required for deterministic packaging/resource embedding.' }
if (-not (Test-Path $Launcher) -or -not (Test-Path $Uninstaller) -or -not (Test-Path $WoWWatcher)) { throw 'Run installer/windows/build.sh before signing.' }
if (-not $CertThumbprint -and -not $PfxPath) { throw 'Provide -CertThumbprint or -PfxPath.' }

function Invoke-Sign([string]$Path) {
    $args = @('sign','/fd','SHA256','/tr',$TimestampUrl,'/td','SHA256')
    if ($CertThumbprint) {
        $args += @('/sha1', $CertThumbprint)
    } else {
        $args += @('/f', (Resolve-Path $PfxPath).Path)
        if ($env:KEYSTONELENS_PFX_PASSWORD) { $args += @('/p', $env:KEYSTONELENS_PFX_PASSWORD) }
    }
    $args += $Path
    & signtool.exe @args
    if ($LASTEXITCODE -ne 0) { throw "Signing failed: $Path" }
}

# The binaries inside the embedded payload must be signed before Setup itself.
Invoke-Sign $Launcher
Invoke-Sign $Uninstaller
Invoke-Sign $WoWWatcher
& python.exe (Join-Path $PSScriptRoot 'make_payload_zip.py') --root $Payload --out (Join-Path $Build 'payload.zip')
if ($LASTEXITCODE -ne 0) { throw 'Could not rebuild signed payload.zip.' }
Copy-Item (Join-Path $Build 'payload.zip') (Join-Path $PSScriptRoot 'bootstrap\payload.zip') -Force

$env:GOOS = 'windows'; $env:GOARCH = 'amd64'; $env:CGO_ENABLED = '0'; $env:GO111MODULE = 'off'
& go.exe build -trimpath '-ldflags=-H=windowsgui -s -w -buildid=' -o $Setup (Join-Path $PSScriptRoot 'bootstrap\main.go')
if ($LASTEXITCODE -ne 0) { throw 'Could not rebuild Setup with signed payload.' }
& python.exe (Join-Path $PSScriptRoot 'embed_pe_resources.py') --exe $Setup --ico (Join-Path $Root 'app\KeystoneLens.ico') --version $Version --description 'KeystoneLens Companion Setup' --original-filename 'KeystoneLens-Setup.exe'
if ($LASTEXITCODE -ne 0) { throw 'Could not embed Setup resources.' }
Invoke-Sign $Setup

foreach ($file in @($Launcher,$Uninstaller,$WoWWatcher,$Setup)) {
    & signtool.exe verify /pa /all $file
    if ($LASTEXITCODE -ne 0) { throw "Signature verification failed: $file" }
}
Write-Host 'All KeystoneLens Windows binaries are signed and verified.'
Write-Host 'Package them without rebuilding the unsigned Windows binaries: KEYSTONELENS_SKIP_WINDOWS_BUILD=1 ./scripts/BUILD-RELEASE.sh'
