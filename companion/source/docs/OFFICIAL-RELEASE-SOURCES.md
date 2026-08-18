# Official release references for KeystoneLens 0.12.8

This file records the external platform and distribution contracts used by the release pipeline. Runtime/live acceptance remains a separate gate.

## Blizzard / WoW

- WoW UI Add-On Development Policy: https://eu.forums.blizzard.com/en/wow/t/wow-user-interface-add-on-development-policy/1642
  - Addons must be free, visible/unobfuscated, must not advertise or solicit donations in-game, and must avoid negative game/realm/player impact.
- Current Blizzard content-update notes: https://worldofwarcraft.blizzard.com/en-us/content-update-notes
- The packaged Retail TOC keeps `120007, 120100` as transition compatibility. Final publication still verifies the actual installed client and the intended Retail build.

## CurseForge

- WoW file processor requirements: https://support.curseforge.com/support/solutions/articles/9000210425-curseforge-file-processor-rejections-and-how-to-solve-them
- File release types / additional fields: https://support.curseforge.com/support/solutions/articles/9000197242
- Project submission/file requirements: https://support.curseforge.com/support/solutions/articles/9000197241-creating-and-submitting-a-project
- Multi-TOC guidance: https://support.curseforge.com/support/solutions/articles/9000209856-multi-toc-for-world-of-warcraft-addons
- PackageMeta format: https://support.curseforge.com/support/solutions/articles/9000197952-preparing-the-packagemeta-file

KeystoneLens uses a custom deterministic packager rather than relying on automatic CurseForge packaging. The generated Bridge archive is nevertheless checked against the same distribution contract: one `KeystoneLensBridge/` root, matching `KeystoneLensBridge.toc`, no executable payload and retained license notices.

## GitHub / supply chain

- Secure use of GitHub Actions: https://docs.github.com/en/actions/reference/security/secure-use
- Artifact attestations: https://docs.github.com/en/actions/concepts/security/artifact-attestations
- Supply-chain build hardening: https://docs.github.com/en/code-security/tutorials/implement-supply-chain-best-practices/securing-builds

Actions used by the repository are pinned to immutable full commit SHAs. Public release assets are produced from an exact `v<VERSION>` tag, checksummed, attested and published as GitHub Release assets rather than committed back to `main`.

## Windows / Microsoft

- Windows application best practices: https://learn.microsoft.com/en-us/windows/apps/get-started/best-practices
- Code signing options: https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options
- Authenticode RFC 3161/SHA-256 timestamping: https://learn.microsoft.com/en-us/windows/win32/seccrypto/time-stamping-authenticode-signatures
- Setup UX guidance: https://learn.microsoft.com/en-us/windows/win32/uxguide/exper-setup

Public Windows release requires a real publisher identity. The current release scripts use SHA-256 Authenticode, RFC 3161/SHA-256 timestamping and post-sign verification. Signing secrets must stay outside source control.

## Python runtime

- Python 3.13 Windows guidance: https://docs.python.org/3.13/using/windows.html
- Python 3.13.15 release: https://www.python.org/downloads/release/python-31315/

KeystoneLens uses a dedicated per-user CPython runtime because the Companion UI requires Tcl/Tk and Setup requires pip; the embeddable distribution is deliberately not claimed or used.

## Python package provenance

- Requests 2.34.2: https://pypi.org/project/requests/2.34.2/
- Pillow 12.3.0: https://pypi.org/project/pillow/12.3.0/
- zxing-cpp 3.1.1: https://pypi.org/project/zxing-cpp/3.1.1/
- charset-normalizer 3.4.9: https://pypi.org/project/charset-normalizer/3.4.9/
- idna 3.18: https://pypi.org/project/idna/3.18/
- urllib3 2.7.0: https://pypi.org/project/urllib3/2.7.0/
- certifi 2026.7.22: https://pypi.org/project/certifi/2026.7.22/

The exact Windows runtime lock remains the production dependency source; the weekly dependency-audit workflow scans both the declared application requirements and exact runtime package set.
