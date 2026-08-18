# Contributing to KeystoneLens

KeystoneLens contains a WoW addon, a desktop Companion and native Windows bootstrap/launcher components. Changes should preserve release determinism, fail-closed data handling and the separation between source and generated artifacts.

## Source and release rules

- `companion/source/VERSION` is the canonical product version. Keep Companion, Bridge, generated data-addon and Windows release metadata aligned with it.
- Do not commit generated ZIPs, EXEs, build/release directories, checksums, caches, logs, screenshots, credentials, PFX files or private keys.
- Keep the standalone Bridge under `addon/KeystoneLensBridge/` authoritative. Release validation synchronizes the embedded Companion copy from that source.
- Keep tooltip/cache context fail-closed. New cache fields must not weaken activity, key-level or spec binding.
- Runtime dependency changes must update the intended requirements/lock evidence together and remain reproducible under CI.
- Never replace the real Authenticode release gate with a self-signed or unsigned public build.

## Validation before a pull request

Run the repository and Companion checks that apply to your change:

```bash
python3 companion/source/scripts/audit_repository.py
cd companion/source
python -m pytest -q
python -m compileall -q app/keystonelens_companion
bash scripts/BUILD-RELEASE.sh
```

Windows installer, launcher, uninstall or watcher changes must also pass the native Windows workflow. Dependency changes must pass both the scheduled dependency audit and the PR dependency audit. Python and Go source changes are scanned by CodeQL.

## Pull request expectations

- Explain the correctness, security, compatibility or product problem being solved.
- State impact on the WoW Bridge, Companion, Windows installer, saved/generated data and release packaging.
- Keep `VERSION` unchanged unless the pull request intentionally creates a new release identity and matching release evidence.
- Include regression coverage for parser, transport, cache, installer, lifecycle or scoring correctness changes when practical.
- Do not claim live WoW, Warcraft Logs, SmartScreen or clean-Windows acceptance unless it was actually performed.

Security vulnerabilities should follow `SECURITY.md` rather than being posted as public issues.

## Public releases

A version tag must match `VERSION`. The release workflow validates source and deterministic artifacts, signs the validated Windows payload with the configured publisher identity, verifies Authenticode and creates only a draft GitHub Release. Publishing remains gated on the documented live WoW and clean-Windows acceptance checks.
