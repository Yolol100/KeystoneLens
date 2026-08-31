param(
    [string]$OutputDir = ''
)

$ErrorActionPreference = 'Stop'
$SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Version = (Get-Content -LiteralPath (Join-Path $SourceRoot 'VERSION') -Raw).Trim()
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Invalid KeystoneLens VERSION: $Version" }

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $SourceRoot 'release'
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$OutputDir = (Resolve-Path $OutputDir).Path

$RuntimeSpecPath = Join-Path $SourceRoot 'runtime\windows\python-runtime.json'
try {
    $RuntimeSpec = Get-Content -LiteralPath $RuntimeSpecPath -Raw | ConvertFrom-Json
} catch {
    throw "Could not read the canonical portable runtime manifest: $RuntimeSpecPath"
}
$PythonVersion = [string]$RuntimeSpec.version
$PythonUrl = [string]$RuntimeSpec.url
$PythonSha = ([string]$RuntimeSpec.sha256).ToLowerInvariant()
if ($PythonVersion -notmatch '^\d+\.\d+\.\d+$') { throw "Invalid runtime version: $PythonVersion" }
if ([string]$RuntimeSpec.platform -ne 'windows-x64') { throw "Unsupported portable runtime platform: $($RuntimeSpec.platform)" }
if ($PythonUrl -notmatch '^https://www\.python\.org/') { throw "Portable runtime URL must use python.org HTTPS: $PythonUrl" }
if ($PythonSha -notmatch '^[0-9a-f]{64}$') { throw 'Portable runtime SHA-256 is invalid.' }

$TempBase = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
$BuildRoot = Join-Path $TempBase ('KeystoneLensPortable-' + [guid]::NewGuid().ToString('N'))
$Stage = Join-Path $BuildRoot 'KeystoneLens-Portable'
$Runtime = Join-Path $Stage 'runtime'
$App = Join-Path $Stage 'app'
$Packages = Join-Path $Stage 'packages'
$PythonInstaller = Join-Path $BuildRoot 'python-runtime.exe'
$Extracted = Join-Path $BuildRoot 'verify-extracted'
$ZipPath = Join-Path $OutputDir ("KeystoneLens-Portable-$Version-Windows-x64.zip")

try {
    New-Item -ItemType Directory -Force -Path $BuildRoot,$Stage,$Runtime,$App,$Packages | Out-Null

    Write-Host "Downloading canonical Python runtime: $PythonUrl"
    Invoke-WebRequest -Uri $PythonUrl -OutFile $PythonInstaller -UseBasicParsing
    $ActualPythonSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $PythonInstaller).Hash.ToLowerInvariant()
    if ($ActualPythonSha -ne $PythonSha) {
        throw "Python runtime SHA-256 mismatch. Expected $PythonSha, got $ActualPythonSha"
    }

    $RuntimeArgs = @(
        '/quiet',
        'InstallAllUsers=0',
        ('TargetDir=' + $Runtime),
        'Include_launcher=0',
        'Include_test=0',
        'Include_doc=0',
        'Shortcuts=0',
        'PrependPath=0',
        'AppendPath=0',
        'AssociateFiles=0',
        'CompileAll=0',
        'Include_debug=0',
        'Include_symbols=0',
        'Include_tools=0',
        'Include_pip=1',
        'Include_tcltk=1'
    )
    $RuntimeInstall = Start-Process -FilePath $PythonInstaller -ArgumentList $RuntimeArgs -Wait -PassThru
    if ($RuntimeInstall.ExitCode -notin @(0, 3010)) {
        throw "Private Python runtime staging failed with exit code $($RuntimeInstall.ExitCode)."
    }

    $Python = Join-Path $Runtime 'python.exe'
    $PythonW = Join-Path $Runtime 'pythonw.exe'
    if (-not (Test-Path -LiteralPath $Python) -or -not (Test-Path -LiteralPath $PythonW)) {
        throw 'Portable Python runtime is incomplete after staging.'
    }
    & $Python -I -c "import sys,tkinter,pip; raise SystemExit(0 if '.'.join(map(str,sys.version_info[:3])) == '$PythonVersion' else 4)"
    if ($LASTEXITCODE -ne 0) { throw 'Portable Python Tk/pip/version verification failed.' }

    Copy-Item -LiteralPath (Join-Path $SourceRoot 'app\KeystoneLens.ico') -Destination (Join-Path $App 'KeystoneLens.ico') -Force
    Copy-Item -LiteralPath (Join-Path $SourceRoot 'app\keystonelens_companion') -Destination (Join-Path $App 'keystonelens_companion') -Recurse -Force

    $LockFile = Join-Path $SourceRoot 'runtime\windows\requirements-runtime.lock'
    $PipArgs = @(
        '-m','pip','install',
        '--isolated','--no-input','--disable-pip-version-check','--no-warn-script-location',
        '--no-cache-dir','--no-compile','--timeout','30','--retries','3',
        '--index-url','https://pypi.org/simple','--only-binary=:all:',
        '--require-hashes','--no-deps','--target',$Packages,'-r',$LockFile
    )
    & $Python @PipArgs
    if ($LASTEXITCODE -ne 0) { throw 'Portable dependency installation failed.' }

    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'START-COMPANION.cmd') -Destination (Join-Path $Stage 'START-COMPANION.cmd') -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'portable_launcher.py') -Destination (Join-Path $Stage 'portable_launcher.py') -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'LEESMIJ.txt') -Destination (Join-Path $Stage 'LEESMIJ.txt') -Force
    Copy-Item -LiteralPath (Join-Path $SourceRoot 'VERSION') -Destination (Join-Path $Stage 'VERSION') -Force
    Set-Content -LiteralPath (Join-Path $Runtime 'python-version.txt') -Value $PythonVersion -Encoding ascii -NoNewline

    Get-ChildItem -LiteralPath $Stage -Directory -Recurse -Filter '__pycache__' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -LiteralPath $Stage -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @('.pyc', '.pyo') } |
        Remove-Item -Force -ErrorAction SilentlyContinue

    & $Python -B -I (Join-Path $Stage 'portable_launcher.py') --verify
    if ($LASTEXITCODE -ne 0) { throw 'Portable staged runtime verification failed.' }

    Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
    & $Python -B (Join-Path $PSScriptRoot 'make_portable_zip.py') --root $Stage --out $ZipPath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $ZipPath)) {
        throw 'Portable ZIP creation failed.'
    }

    New-Item -ItemType Directory -Force -Path $Extracted | Out-Null
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $Extracted -Force
    $ExtractedPython = Join-Path $Extracted 'runtime\python.exe'
    & $ExtractedPython -B -I (Join-Path $Extracted 'portable_launcher.py') --verify
    if ($LASTEXITCODE -ne 0) { throw 'Extracted portable ZIP verification failed.' }

    foreach ($forbidden in @('KeystoneLens-Setup.exe','KeystoneLens.exe','KeystoneLens-Uninstall.exe','KeystoneLens-WoW-Watcher.exe')) {
        if (Test-Path -LiteralPath (Join-Path $Extracted $forbidden)) {
            throw "Portable package must not contain $forbidden."
        }
    }

    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ZipPath).Hash.ToLowerInvariant()
    Write-Host "PORTABLE_ZIP=$ZipPath"
    Write-Host "PORTABLE_SHA256=$Hash"
} finally {
    Remove-Item -LiteralPath $BuildRoot -Recurse -Force -ErrorAction SilentlyContinue
}
