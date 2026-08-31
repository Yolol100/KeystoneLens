# Changelog

## 0.12.8 — Tooltip correctness, Season 2 readiness and portable Windows release

- Bound cached KL tooltip scores to the exact Group Finder activity, target key level and applicant specialization.
- Kept schema-v2 tooltip data fail-closed across rollback and context changes.
- Kept the fixed 50/50 Raider.IO + Warcraft Logs scoring model.
- Confirmed the current Season 2 registry/source boundaries and kept request/cache behavior bounded.
- Made `companion/source/VERSION` the canonical release identity across Companion, Bridge, generated data and release filenames.
- Replaced the Windows Setup/custom launcher/uninstaller/WoW-watcher distribution stack with one extract-only portable Windows ZIP.
- Added a neutral `runtime/windows-x64.json` source contract for the pinned official CPython runtime and moved the exact Python package lock to `runtime/`.
- Preserved single-instance behavior in the portable Python launcher while removing the custom KeystoneLens executable.
- Removed build-only pip command shims from the delivered private runtime.
- Build the portable ZIP twice independently and require byte-identical SHA-256 output before upload.
- Re-extract and verify the exact portable archive with its bundled runtime; reject legacy KeystoneLens custom executables in the archive.
- Keep generated release assets out of `main`; tagged builds create draft release assets with checksums and attestations.

Full pre-0.12.8 history is retained in `HISTORY.md`. Version-specific release notes remain in `RELEASE-NOTES-<VERSION>.md`.
