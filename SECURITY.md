# Security policy

## Supported version

Security fixes are applied to the current `main` source and the newest published KeystoneLens release only.

## Reporting a vulnerability

Do not publish credentials, private keys, exploit details, or user data in a public issue. Prefer GitHub private vulnerability reporting from the repository Security tab when that option is available. If private reporting is unavailable, contact the repository maintainer through the GitHub account before sharing sensitive reproduction details.

Include the affected component (Bridge, Companion, installer, updater/watcher, or release pipeline), affected version, reproduction conditions, impact, and the minimum evidence needed to validate the issue.

## Release trust

A successful source/CI audit is not equivalent to a signed Windows release. Public Windows production artifacts require the documented Authenticode signing and verification gate in addition to the normal source, package, dependency and runtime checks.
