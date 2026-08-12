$ErrorActionPreference = 'Stop'
$Build = Join-Path $PSScriptRoot 'build'
$Files = @(
    (Join-Path $Build 'payload\KeystoneLens.exe'),
    (Join-Path $Build 'payload\KeystoneLens-Uninstall.exe'),
    (Join-Path $Build 'KeystoneLens-Setup.exe')
)
foreach ($file in $Files) {
    if (-not (Test-Path $file)) { throw "Missing: $file" }
    $sig = Get-AuthenticodeSignature -FilePath $file
    if ($sig.Status -ne 'Valid') { throw "Invalid or missing Authenticode signature: $file ($($sig.Status))" }
    Write-Host "VALID $file — $($sig.SignerCertificate.Subject)"
}
