# KeystoneLens 0.12.8 post-audit report

## Verdict

**SOURCE / BUILD / PORTABLE RELEASE PIPELINE: PASS WITH EXTERNAL LIVE + REPOSITORY-ADMIN + POLICY REVIEW GATES**

This report describes the current 0.12.8 source architecture. It does not claim live WoW, clean-Windows, repository-admin or Blizzard-policy acceptance that source/CI cannot prove.

## Runtime correctness retained

- KL Score remains exactly 50% Raider.IO plus 50% Warcraft Logs.
- Tooltip cache schema v2 stays bound to exact activity, target key and applicant spec; rollback to a name-only cache fails closed.
- Queue-generation and snapshot transport reject stale prior-listing results and retain fragments until complete delivery.
- Recruitment capture pauses at the documented full-party/active-dungeon boundaries.
- Raider.IO/WCL API identity, pacing, retry, OAuth/quota and bounded cache rules remain source-contract gates.
- The Bridge and desktop Companion remain observation/display-only; input injection, process-memory access and protected-action expansion remain rejected by repository audits.

## Portable Windows architecture

The previous installed-executable distribution was incomplete after the first portable change because the portable builder still read runtime constants/locks/helpers from `companion/source/installer/windows/`, while release/workflow/tests still treated Setup as authoritative. That coupling has been removed.

Current authoritative paths are:

- `companion/source/portable/` — start/build logic;
- `companion/source/runtime/windows-x64.json` — official CPython version/URL/SHA-256;
- `companion/source/runtime/requirements-runtime.lock` — exact hash-locked runtime packages;
- `companion/source/scripts/make_deterministic_zip.py` — deterministic generic ZIP helper.

The obsolete `companion/source/installer/` and root `executable/` source stacks are not allowed by the repository audit. The current package must reject `KeystoneLens-Setup.exe`, custom `KeystoneLens.exe`, `KeystoneLens-Uninstall.exe` and `KeystoneLens-WoW-Watcher.exe`.

The private CPython runtime is intentionally retained because Tkinter/Pillow/zxing-cpp/requests require a real interpreter runtime. `START-COMPANION.cmd` uses bundled `runtime/python.exe` for fail-visible verification and `runtime/pythonw.exe` for the UI. Build-only pip command shims/package are removed before packaging.

Single-instance behavior was preserved in `portable_launcher.py` with the existing named mutex `KeystoneLens.Companion.Singleton`; removing the old Go launcher therefore does not reintroduce duplicate Companion instances.

## Release integrity

- Portable CI builds the ZIP twice independently and requires equal SHA-256 hashes.
- The exact ZIP is re-extracted and verified with its own bundled Python runtime.
- The core release build still runs twice and requires deterministic output for Bridge/source artifacts.
- GitHub Actions remain full-SHA pinned with persisted checkout credentials disabled.
- Tag `v<VERSION>` parity remains mandatory.
- Draft tag releases now contain the validated Bridge, source and portable Windows ZIPs, checksums and GitHub attestations; no custom Setup/signing pipeline remains.
- Runtime/SBOM audits bind the CPython version/hash and direct package inventory to the current runtime contract.

## Validation still external

CI does not prove:

- first-run GUI behavior on a real clean user Windows desktop, SmartScreen/AV presentation, Unicode/long-path behavior or user-specific policy restrictions;
- live WoW Retail Group Finder context churn, secret values, screenshot/CVar recovery, representative resolutions/UI scales and repeated-capture soak;
- authenticated first-live Warcraft Logs behavior with real release credentials;
- CurseForge project metadata/distribution settings;
- branch protection, Dependency Graph, secret scanning and other repository-admin settings;
- formal Blizzard policy/EULA acceptance for the external Companion.

These remain explicit publication gates rather than being inferred from green CI.
