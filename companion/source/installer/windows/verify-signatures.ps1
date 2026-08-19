$ErrorActionPreference = 'Stop'
$Build = Join-Path $PSScriptRoot 'build'
if (-not (Get-Command signtool.exe -ErrorAction SilentlyContinue)) { throw 'signtool.exe is required from the Windows SDK.' }
$Files = @(
    (Join-Path $Build 'payload\KeystoneLens.exe'),
    (Join-Path $Build 'payload\KeystoneLens-Uninstall.exe'),
    (Join-Path $Build 'payload\KeystoneLens-WoW-Watcher.exe'),
    (Join-Path $Build 'KeystoneLens-Setup.exe')
)
foreach ($file in $Files) {
    if (-not (Test-Path $file)) { throw "Missing: $file" }
    & signtool.exe verify /pa /tw /all /v $file
    if ($LASTEXITCODE -ne 0) { throw "Signature/timestamp verification failed: $file" }
    $sig = Get-AuthenticodeSignature -FilePath $file
    if ($sig.Status -ne 'Valid') { throw "Invalid or missing Authenticode signature: $file ($($sig.Status))" }
    if ($null -eq $sig.SignerCertificate) { throw "Signer certificate unavailable: $file" }
    Write-Host "VALID + TIMESTAMPED $file — $($sig.SignerCertificate.Subject)"
}
