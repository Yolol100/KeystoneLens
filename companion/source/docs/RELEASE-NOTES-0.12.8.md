# KeystoneLens 0.12.8

0.12.8 is a correctness, Season 2 readiness and release-hardening update. The KL scoring formula remains exactly 50% Raider.IO + 50% Warcraft Logs; no hidden third scoring pillar or automated Group Finder action was added.

## Runtime correctness

- Tooltip cache schema v2 is bound to the exact Group Finder activity, target key level and applicant specialization; rollback to the old name-only cache fails closed.
- Confidence/evidence-age metadata remains visible and freshness uses the oldest positive contributing source timestamp.
- Delist/re-queue advances listing generation so delayed frames/results from an old queue cannot repopulate the new one.
- Raider.IO and Warcraft Logs pacing/backoff/cache limits remain bounded and fail-closed.
- The Bridge remains recruitment/display-only and repository policy rejects protected-action, combat/input-injection and process-memory expansion.
- Season 2 source selection remains aligned with the verified current Raider.IO/Warcraft Logs model used by 0.12.8.

## Portable Windows Companion

The supported Windows distribution is now `KeystoneLens-Portable-0.12.8-Windows-x64.zip`.

- Users extract the complete ZIP and start `START-COMPANION.cmd`; no `KeystoneLens-Setup.exe`, Windows installation, registry/Start-menu setup, administrator rights or separately installed Python are required.
- The obsolete installer/bootstrap/installed-launcher/uninstaller/WoW-watcher source tree is removed from the current source model.
- `runtime/windows/python-runtime.json` is the single source for Windows CPython version, python.org HTTPS URL and SHA-256.
- Runtime packages remain exact and hash-locked in `runtime/windows/requirements-runtime.lock` with `--require-hashes --no-deps --only-binary=:all:`.
- The portable launcher preserves the named `Local\KeystoneLens.Companion.Singleton` mutex, preventing duplicate Companion processes.
- Nonzero `SystemExit`/startup failures from the `pythonw.exe` path now produce visible diagnostics instead of disappearing silently.
- The portable launcher reads the expected Python version from bundled runtime metadata rather than duplicating a hard-coded patch version.
- Windows CI stages and verifies the runtime, creates the deterministic ZIP, re-extracts that exact ZIP and verifies it again.
- Portable CI rejects `KeystoneLens-Setup.exe`, `KeystoneLens.exe`, `KeystoneLens-Uninstall.exe` and `KeystoneLens-WoW-Watcher.exe` anywhere in the delivered archive.

## Repository and supply-chain hardening

- `companion/source/VERSION` remains the canonical Companion/Bridge/data-addon release identity.
- Generated binaries/ZIPs/checksums are release outputs rather than tracked source files.
- GitHub Actions use immutable full-SHA pins, explicit runner images and non-persisting checkout credentials.
- Dependabot covers Actions and production Python requirements; `pip-audit` also checks the exact portable runtime package set.
- Native Windows tests keep DPAPI/config coverage without rebuilding obsolete Go/Setup executables.
- Source/CurseForge packaging is deterministic and built twice during primary validation.
- A `v<VERSION>` tag builds the portable Windows ZIP on `windows-2025`, combines it with the exact validated core artifacts, creates SHA-256 checksums and GitHub provenance/CycloneDX attestations, then creates only a draft GitHub Release.
- No publisher PFX/signing secret is required by the current release path because KeystoneLens no longer publishes a custom Setup/installed launcher executable.
- `LICENSE-SCOPE.md` continues to document the Bridge/third-party licensing boundary without inventing a repository-wide Companion license.

## Release gates still external

Source/CI evidence does not prove:

- clean-Windows portable extract/start/close/restart/double-start, taskbar/DPI, Unicode/long/read-only/locked-path and Windows reputation/security-prompt behavior;
- live WoW Retail Group Finder/screenshot/tooltip/Companion Data acceptance;
- authenticated first-live Warcraft Logs `/api/v2/client` parsing with the real release credentials;
- CurseForge project metadata/channel settings;
- GitHub branch protection/rulesets, secret scanning and push protection;
- formal Blizzard authorization/policy acceptance for the external Companion.

Use Beta/preview distribution while any applicable live/public acceptance gate remains open.
