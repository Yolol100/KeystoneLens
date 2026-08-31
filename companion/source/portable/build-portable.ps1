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

$RuntimeContractPath = Join-Path $SourceRoot 'runtime\windows-x64.json'
$RuntimeContract = Get-Content -LiteralPath $RuntimeContractPath -Raw | ConvertFrom-Json
$PythonVersion = [string]$RuntimeContract.python_version
$PythonUrl = [string]$RuntimeContract.python_url
$PythonSha = ([string]$RuntimeContract.python_sha256).ToLowerInvariant()
if ([string]$RuntimeContract.platform -ne 'windows-x64') { throw 'Runtime contract must target windows-x64.' }
if ($PythonVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'Runtime contract has an invalid Python version.' }
if ($PythonUrl -notmatch '^https://') { throw 'Runtime contract Python URL must use HTTPS.' }
if ($PythonSha -notmatch '^[0-9a-f]{64}$') { throw 'Runtime contract has an invalid Python SHA-256.' }

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
        throw "Private Python runtime install-to-folder failed with exit code $($RuntimeInstall.ExitCode)."
    }

    $Python = Join-Path $Runtime 'python.exe'
    $PythonW = Join-Path $Runtime 'pythonw.exe'
    if (-not (Test-Path -LiteralPath $Python) -or -not (Test-Path -LiteralPath $PythonW)) {
        throw 'Portable Python runtime is incomplete after staging.'
    }
    $VersionCheck = "import sys,tkinter,pip; expected=tuple(map(int,'$PythonVersion'.split('.'))); raise SystemExit(0 if sys.version_info[:3] == expected else 4)"
    & $Python -I -c $VersionCheck
    if ($LASTEXITCODE -ne 0) { throw 'Portable Python Tk/pip/version verification failed.' }

    Copy-Item -LiteralPath (Join-Path $SourceRoot 'app\KeystoneLens.ico') -Destination (Join-Path $App 'KeystoneLens.ico') -Force
    Copy-Item -LiteralPath (Join-Path $SourceRoot 'app\keystonelens_companion') -Destination (Join-Path $App 'keystonelens_companion') -Recurse -Force

    $LockFile = Join-Path $SourceRoot 'runtime\requirements-runtime.lock'
    $PipArgs = @(
        '-m','pip','install',
        '--isolated','--no-input','--disable-pip-version-check','--no-warn-script-location',
        '--no-cache-dir','--no-compile','--timeout','30','--retries','3',
        '--index-url','https://pypi.org/simple','--only-binary=:all:',
        '--require-hashes','--no-deps','--target',$Packages,'-r',$LockFile
    )
    & $Python @PipArgs
    if ($LASTEXITCODE -ne 0) { throw 'Portable dependency installation failed.' }

    # pip is needed only while assembling the portable package. Remove its
    # command shims and package after dependencies are staged so the delivered
    # runtime contains no unnecessary package-management executables.
    Remove-Item -LiteralPath (Join-Path $Runtime 'Scripts') -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $Runtime 'Lib\site-packages\pip') -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -LiteralPath (Join-Path $Runtime 'Lib\site-packages') -Directory -Filter 'pip-*.dist-info' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'START-COMPANION.cmd') -Destination (Join-Path $Stage 'START-COMPANION.cmd') -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'portable_launcher.py') -Destination (Join-Path $Stage 'portable_launcher.py') -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'LEESMIJ.txt') -Destination (Join-Path $Stage 'LEESMIJ.txt') -Force
    Copy-Item -LiteralPath (Join-Path $SourceRoot 'VERSION') -Destination (Join-Path $Stage 'VERSION') -Force
    Copy-Item -LiteralPath $RuntimeContractPath -Destination (Join-Path $Stage 'RUNTIME.json') -Force

    Get-ChildItem -LiteralPath $Stage -Directory -Recurse -Filter '__pycache__' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -LiteralPath $Stage -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @('.pyc', '.pyo') } |
        Remove-Item -Force -ErrorAction SilentlyContinue

    & $Python -I (Join-Path $Stage 'portable_launcher.py') --verify
    if ($LASTEXITCODE -ne 0) { throw 'Portable staged runtime verification failed.' }

    Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
    & $Python (Join-Path $SourceRoot 'scripts\make_deterministic_zip.py') --root $Stage --out $ZipPath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $ZipPath)) {
        throw 'Portable ZIP creation failed.'
    }

    New-Item -ItemType Directory -Force -Path $Extracted | Out-Null
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $Extracted -Force
    $ExtractedPython = Join-Path $Extracted 'runtime\python.exe'
    & $ExtractedPython -I (Join-Path $Extracted 'portable_launcher.py') --verify
    if ($LASTEXITCODE -ne 0) { throw 'Extracted portable ZIP verification failed.' }

    $Forbidden = @('KeystoneLens-Setup.exe','KeystoneLens.exe','KeystoneLens-Uninstall.exe','KeystoneLens-WoW-Watcher.exe')
    $Unexpected = Get-ChildItem -LiteralPath $Extracted -File -Recurse | Where-Object { $_.Name -in $Forbidden }
    if ($Unexpected) {
        throw ('Portable package contains obsolete KeystoneLens executable(s): ' + (($Unexpected | ForEach-Object Name) -join ', '))
    }

    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ZipPath).Hash.ToLowerInvariant()
    Write-Host "PORTABLE_ZIP=$ZipPath"
    Write-Host "PORTABLE_SHA256=$Hash"
} finally {
    Remove-Item -LiteralPath $BuildRoot -Recurse -Force -ErrorAction SilentlyContinue
}
