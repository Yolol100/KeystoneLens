## Summary

<!-- What problem does this change solve? -->

## Product / compatibility impact

<!-- Cover Bridge, Companion, portable runtime/launcher, generated data, release packaging and version identity where relevant. -->

## Validation

- [ ] `python3 companion/source/scripts/audit_repository.py`
- [ ] relevant Companion regressions pass
- [ ] deterministic core release build passes when packaging/source is affected
- [ ] portable Windows double-build + extracted-runtime verification passes when portable/runtime code is affected
- [ ] native Windows validation passes when Windows runtime behavior is affected
- [ ] no generated ZIP/EXE/build output, secrets, PFX/private keys or local runtime data are committed
- [ ] `companion/source/VERSION` changed only when intentionally creating a new release identity

## Security / dependency impact

- [ ] No new dependency is introduced, or dependency review/audit evidence is included.
- [ ] Cache/parser/transport/input changes remain fail-closed.
- [ ] The retired Setup/custom-executable stack was not reintroduced.

## Live acceptance

- [ ] No live WoW/Windows/WCL behavior is affected, or the affected scenarios are described below.
- [ ] I have not claimed live WoW, Warcraft Logs or clean-Windows acceptance that was not actually performed.
