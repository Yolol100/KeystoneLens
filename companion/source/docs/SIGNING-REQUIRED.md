# Windows signing gate — 0.12.8

Public Windows distribution stays fail-closed until a real publisher signing identity is available. A self-signed certificate is useful only for controlled local testing and is not a substitute for public trust.

## Required signing order

Before public direct-download distribution, SHA-256 Authenticode-sign and RFC 3161/SHA-256 timestamp:

1. installed `KeystoneLens.exe`;
2. installed `KeystoneLens-Uninstall.exe`;
3. installed `KeystoneLens-WoW-Watcher.exe`;
4. rebuild the embedded payload and Setup;
5. final `KeystoneLens-Setup.exe`.

`installer/windows/sign-release.ps1` implements this order, reads the canonical version from `companion/source/VERSION`, rebuilds Setup after signing the embedded payload binaries, and verifies every signature with both SignTool and PowerShell Authenticode status.

## GitHub tag-release secrets

The tag-release workflow expects these repository/environment secrets:

- `KEYSTONELENS_PFX_BASE64` — base64-encoded publisher PFX supplied to the ephemeral Windows runner;
- `KEYSTONELENS_PFX_PASSWORD` — password for that PFX.

Do not commit a PFX, password, private key or decoded certificate to the repository. The workflow decodes the PFX only into the runner temporary directory, uses it for the release job and relies on the ephemeral runner cleanup afterwards. If either secret is unavailable, the public tag release fails rather than publishing an unsigned installer.

For manual signing, `sign-release.ps1` can also use a certificate already installed in the Windows certificate store by passing `-CertThumbprint`.

After manual signing, package without rebuilding unsigned Windows binaries:

`KEYSTONELENS_SKIP_WINDOWS_BUILD=1 ./scripts/BUILD-RELEASE.sh`

Any binary modification after Authenticode signing invalidates the signature.

Microsoft currently recommends SHA-256 Authenticode with RFC 3161 timestamping. If KeystoneLens later moves away from a PFX-based CI identity, evaluate Microsoft Artifact Signing/managed signing as a separate migration rather than weakening this gate.
