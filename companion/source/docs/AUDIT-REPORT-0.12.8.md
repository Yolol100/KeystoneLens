# KeystoneLens 0.12.8 post-audit report

## Verdict

**SOURCE / PORTABLE BUILD / RELEASE PIPELINE: PASS WITH EXTERNAL LIVE + CLEAN-WINDOWS + REPOSITORY-ADMIN + POLICY REVIEW GATES**

This report describes the current 0.12.8 source. It does not claim live WoW, clean-Windows portable acceptance, repository-admin settings or Blizzard-policy acceptance that source inspection/CI cannot prove.

## Runtime correctness retained

- KL Score remains exactly 50% Raider.IO plus 50% Warcraft Logs.
- Tooltip cache schema v2 remains bound to activity/key/spec context and rollback fails closed.
- Invalid/incomplete/secret listing context and non-finite score evidence remain fail-closed.
- Raider.IO/WCL request pacing, retry/backoff and bounded cache contracts remain machine-tested.
- The Bridge remains recruitment/display-only and repository policy rejects protected-action/combat/input/process-memory expansion.

## Portable distribution audit

The first portable ZIP was valid for install-free use, but the follow-up repository audit found obsolete installer architecture and three launcher regressions identified by automated PR review:

1. the portable launcher did not preserve the old named single-instance mutex;
2. nonzero `SystemExit` from the `pythonw.exe` path could disappear without a visible diagnostic;
3. CPython 3.13.15 was duplicated as a hard-coded launcher value rather than coming from one canonical runtime source.

The current source corrects all three and removes the obsolete distribution layer:

- `companion/source/installer/` and top-level `executable/` are removed from the current source tree;
- `runtime/windows/python-runtime.json` is the sole Windows CPython version/URL/SHA source;
- `runtime/windows/requirements-runtime.lock` is the exact hash-locked production package graph;
- `portable/portable_launcher.py` owns `Local\KeystoneLens.Companion.Singleton` for the lifetime of the Companion;
- nonzero startup exits produce visible error feedback and a diagnostic log;
- the portable build stages, verifies, packages, re-extracts and re-verifies the exact delivered ZIP;
- CI rejects the old Setup/launcher/uninstaller/WoW-watcher executable names in the portable archive;
- native Windows tests retain DPAPI/config coverage without rebuilding obsolete Go/Setup executables.

## Repository and release integrity

- `companion/source/VERSION` is the canonical release identity and current value is `0.12.8`.
- Repository audits now fail if legacy installer/executable source paths are reintroduced.
- Primary validation covers repository hygiene, external security, version parity, Lua syntax, the Python regression suite and deterministic source/CurseForge packaging.
- The extracted source ZIP is tested again and must contain portable/runtime source while excluding legacy installer source.
- GitHub Actions require immutable full-SHA pins, explicit runners and non-persisting checkout credentials.
- A `v<VERSION>` tag builds the portable Windows ZIP on `windows-2025`, combines it with the validated core artifacts, produces SHA-256 checksums and GitHub provenance/CycloneDX attestations, and creates only a draft GitHub Release.
- The current public artifact path no longer requires a custom KeystoneLens PE executable or publisher PFX secret.

## Validation evidence still external

The source and CI gates cannot prove and do not mark as passed:

- clean-Windows portable extraction/start/close/restart/double-start, taskbar/DPI, Windows reputation/security prompts and Unicode/long/read-only/locked-path behavior;
- live WoW Retail Group Finder context churn, screenshot/CVar recovery, Companion Data co-load, tooltip rendering and repeated-capture soak;
- authenticated first-live Warcraft Logs `/api/v2/client` parsing with real release credentials;
- CurseForge project metadata/distribution-channel settings;
- branch protection/rulesets, secret scanning, push protection and other repository-admin settings;
- formal Blizzard authorization for the external Companion.

## Re-audit result

The portable-only cleanup removes code that no longer participates in the supported user/release path while retaining the required pieces: Companion application code, Bridge/data-addon source, native Windows/DPAPI tests, canonical runtime provenance, hash-locked dependencies, deterministic packaging, security audits and live-acceptance documentation. No scoring weights or automated Group Finder actions were changed.
