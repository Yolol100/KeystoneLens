# Security policy

## Supported version

Security fixes are applied to current `main` and the newest published KeystoneLens release only.

## Reporting a vulnerability

Do not publish credentials, private keys, exploit details, or user data in a public issue. Prefer GitHub private vulnerability reporting when available. Otherwise contact the repository maintainer before sharing sensitive reproduction details.

Include the affected component (Bridge, Companion, portable launcher/runtime, or release pipeline), version, reproduction conditions, impact, and the minimum evidence needed to validate the issue.

## Release trust

The Windows Companion is distributed as an extract-only portable ZIP. KeystoneLens does not require a custom Setup/launcher executable. The build downloads the official CPython Windows x64 installer only as build input, verifies its pinned SHA-256, stages a private runtime, installs only the hash-locked package set and removes build-only pip command shims before packaging.

CI builds the portable archive twice independently, requires byte-identical SHA-256 output, re-extracts the archive and verifies the exact staged runtime again. Tag assets receive checksums and GitHub attestations. These source/build controls do not replace live WoW or clean-Windows acceptance.
