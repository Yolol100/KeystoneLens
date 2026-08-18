## Summary

<!-- What problem does this change solve? -->

## Product / compatibility impact

<!-- Cover Bridge, Companion, Windows installer, generated data, release packaging and version identity where relevant. -->

## Validation

- [ ] `python3 companion/source/scripts/audit_repository.py`
- [ ] relevant Companion regressions pass
- [ ] deterministic release build passes when release/package code is affected
- [ ] native Windows validation passes when installer/launcher/uninstall/watcher code is affected
- [ ] no generated ZIP/EXE/build output, secrets, PFX/private keys or local runtime data are committed
- [ ] `companion/source/VERSION` changed only when this PR intentionally creates a new release identity with matching evidence

## Security / dependency impact

- [ ] No new dependency is introduced, or dependency review/audit evidence is included.
- [ ] Cache/parser/transport/input changes remain fail-closed for malformed or context-mismatched evidence.

## Live acceptance

- [ ] No live WoW/Windows/WCL behavior is affected, or the affected scenarios are described below.
- [ ] I have not claimed live WoW, Warcraft Logs, SmartScreen, signing or clean-Windows acceptance that was not actually performed.

<!-- Include exact live client/build/service evidence only when it was actually tested. -->
