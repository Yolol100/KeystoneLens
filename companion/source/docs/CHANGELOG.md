# Changelog

## 0.12.8 — Tooltip-context correctness, Season 2 and portable release hardening

- Bound cached KL tooltip scores to the exact Group Finder activity, target key level and applicant specialization.
- Kept `companion/source/VERSION` as the canonical Companion/Bridge/data-addon release identity.
- Kept the displayed KL Score exactly 50% Raider.IO + 50% Warcraft Logs.
- Removed generated binaries from `main` and removed the obsolete KeystoneLens installer/bootstrap/installed-launcher/uninstaller/WoW-watcher source path.
- Added first-class `KeystoneLens-Portable-<VERSION>-Windows-x64.zip`: extract and start `START-COMPANION.cmd`, with no KeystoneLens Setup or Windows installation.
- Centralized Windows CPython version/URL/SHA under `runtime/windows/python-runtime.json`; exact packages remain hash-locked under `runtime/windows/requirements-runtime.lock`.
- Preserved the single-instance mutex in portable startup and made nonzero `pythonw.exe` startup exits visible through diagnostics.
- Build and re-extract the exact portable ZIP on Windows CI; reject legacy KeystoneLens executable names from the archive.
- Retain native Windows DPAPI/config tests without obsolete Go/Setup build checks.
- Tag releases publish source, CurseForge and portable Windows ZIP artifacts with SHA-256 checksums and GitHub provenance/CycloneDX attestations; no publisher PFX is required by the current artifact path.
- GitHub Releases remain drafts until live WoW, clean-Windows portable and distribution gates pass.

Full pre-0.12.8 history is retained in `HISTORY.md`. Version-specific release notes remain in `RELEASE-NOTES-<VERSION>.md`.
