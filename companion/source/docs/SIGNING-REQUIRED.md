# Windows signing gate — 0.12.8

The generated Windows PE files remain **unsigned** until a real publisher certificate/private key is supplied. A self-signed certificate is not a substitute for public distribution trust.

Before public direct-download distribution, Authenticode-sign and timestamp:

- installed `KeystoneLens.exe`;
- installed `KeystoneLens-Uninstall.exe`;
- installed `KeystoneLens-WoW-Watcher.exe`;
- final `KeystoneLens-Setup.exe` after the signed payload has been embedded.

`installer/windows/sign-release.ps1` implements that signing order with Windows SDK `signtool.exe`, rebuilds Setup after signing the embedded launcher/uninstaller/WoW watcher, and verifies all four signatures. It accepts either a certificate thumbprint or PFX. For PFX use, supply the password through `KEYSTONELENS_PFX_PASSWORD` rather than committing it to source.

After signing, package without rebuilding the unsigned Windows binaries:

`KEYSTONELENS_SKIP_WINDOWS_BUILD=1 ./scripts/BUILD-RELEASE.sh`

Then regenerate/recheck release checksums. Any binary modification after Authenticode signing invalidates the signature.
