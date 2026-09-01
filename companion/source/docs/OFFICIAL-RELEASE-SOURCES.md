# Official release references for KeystoneLens 0.12.8

This file records the external platform and distribution contracts used by the current portable release pipeline. Runtime/live acceptance remains separate.

## Blizzard / WoW

- WoW UI Add-On Development Policy: https://eu.forums.blizzard.com/en/wow/t/wow-user-interface-add-on-development-policy/1642
- Current Blizzard content-update notes: https://worldofwarcraft.blizzard.com/en-us/content-update-notes

The packaged Retail TOC keeps `120007, 120100` as transition compatibility. Final publication still verifies the actual installed client/build.

## Runtime enrichment APIs

- Warcraft Logs API v2/OAuth: https://www.warcraftlogs.com/api/docs
- Warcraft Logs Midnight Season 2 live zone: https://www.warcraftlogs.com/zone/statistics/55/
- Warcraft Logs Midnight Season 2 PTR zone: https://www.warcraftlogs.com/zone/statistics/56/
- Raider.IO Developer API: https://raider.io/api

Reverified 2026-09-01: Warcraft Logs production Mythic+ Season 2 is zone `55`; zone `56` is explicitly the PTR surface. Season 2 encounter IDs are therefore resolved from zone `55`, and the default WCL cache path is migrated to `wcl-cache-prod55.json` so evidence collected against the old PTR mapping is not reused after this correction. Raider.IO remains on the documented public character-profile API, locally paced below the unauthenticated 200 requests/minute limit, with 429 backoff and visible `raider.io` attribution.

## CurseForge

- WoW file processor requirements: https://support.curseforge.com/support/solutions/articles/9000210425-curseforge-file-processor-rejections-and-how-to-solve-them
- File release types: https://support.curseforge.com/support/solutions/articles/9000197242
- Project/file requirements: https://support.curseforge.com/support/solutions/articles/9000197241-creating-and-submitting-a-project

The deterministic Bridge archive has one `KeystoneLensBridge/` root, matching TOC, no executable payload and retained license notices.

## GitHub / supply chain

- Secure use of GitHub Actions: https://docs.github.com/en/actions/reference/security/secure-use
- Artifact attestations: https://docs.github.com/en/actions/concepts/security/artifact-attestations
- Supply-chain build hardening: https://docs.github.com/en/code-security/tutorials/implement-supply-chain-best-practices/securing-builds

Actions are full-SHA pinned. Tag assets are produced from exact `v<VERSION>` source, checksummed, attested and staged as a draft GitHub Release rather than committed to `main`.

## Windows / Python runtime

- Windows application best practices: https://learn.microsoft.com/en-us/windows/apps/get-started/best-practices
- Python 3.13 Windows guidance: https://docs.python.org/3.13/using/windows.html
- Python 3.13.15 release: https://www.python.org/downloads/release/python-31315/

KeystoneLens no longer ships a custom Setup/launcher executable. The portable builder verifies the official CPython installer by pinned SHA-256, stages a private Tk-capable runtime, installs only hash-locked packages, removes build-only pip command shims and packages the resulting directory tree deterministically. Users run only `START-COMPANION.cmd`; no Windows installation is performed.

## Python package provenance

- Requests 2.34.2: https://pypi.org/project/requests/2.34.2/
- Pillow 12.3.0: https://pypi.org/project/pillow/12.3.0/
- zxing-cpp 3.1.1: https://pypi.org/project/zxing-cpp/3.1.1/
- charset-normalizer 3.4.9: https://pypi.org/project/charset-normalizer/3.4.9/
- idna 3.18: https://pypi.org/project/idna/3.18/
- urllib3 2.7.0: https://pypi.org/project/urllib3/2.7.0/
- certifi 2026.7.22: https://pypi.org/project/certifi/2026.7.22/
