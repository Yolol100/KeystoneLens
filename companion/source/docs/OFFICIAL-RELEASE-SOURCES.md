# Official release references checked for KeystoneLens 0.12.7

Checked on 2026-08-12 before packaging.

## CurseForge
- WoW addon file processor requirements: https://support.curseforge.com/support/solutions/articles/9000210425-curseforge-file-processor-rejections-and-how-to-solve-them
- Project/file moderation states: https://support.curseforge.com/support/solutions/articles/9000197905-project-statuses-101
- Project submission/file requirements: https://support.curseforge.com/support/solutions/articles/9000197241-creating-and-submitting-a-project
- Multi-TOC guidance: https://support.curseforge.com/support/solutions/articles/9000209856-multi-toc-for-world-of-warcraft-addons

## Blizzard / WoW
- World of Warcraft UI Add-On Development Policy: https://us.forums.blizzard.com/en/wow/t/ui-add-on-development-policy/24534/1
- Current content-update notes / live Curse of Ula'tek context: https://worldofwarcraft.blizzard.com/en-us/content-update-notes
- Blizzard Season 2 announcement / dungeon pool: https://worldofwarcraft.blizzard.com/en-us/news/24280285
- The 12.1 content update is live; Midnight Season 2 itself starts Aug 18 (NA) / Aug 19 (EU).
- The packaged Retail TOC keeps `120007, 120100` as transition compatibility. Final publish verification should still confirm the actual client with `GetBuildInfo()`.
- Supplemental API/TOC reference for 12.1.0 interface `120100`: https://warcraft.wiki.gg/wiki/Patch_12.1.0/API_changes (secondary reference; final runtime truth remains the installed client).

## Windows / Microsoft
- Windows application best practices: https://learn.microsoft.com/en-us/windows/apps/get-started/best-practices
- Known Folder guidance / SHGetKnownFolderPath: https://learn.microsoft.com/en-us/windows/win32/shell/known-folders
- GetSystemDirectoryW: https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-getsystemdirectoryw
- Code signing options: https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options
- Authenticode RFC 3161/SHA-256 timestamping: https://learn.microsoft.com/en-us/windows/win32/seccrypto/time-stamping-authenticode-signatures
- Setup UX guidance: https://learn.microsoft.com/en-us/windows/win32/uxguide/exper-setup

## Python runtime
- Python 3.13 Windows installer options, including custom `TargetDir`, feature toggles and the distinction between the full installer and embeddable distribution: https://docs.python.org/3.13/using/windows.html
- Python 3.13.15 release / Windows installer: https://www.python.org/downloads/release/python-31315/
- KeystoneLens uses the full installer in a dedicated per-user target because the UI requires Tcl/Tk and Setup requires pip; the embeddable distribution is deliberately not claimed or used.

## Python package provenance
- Requests 2.34.2: https://pypi.org/project/requests/2.34.2/
- Pillow 12.3.0: https://pypi.org/project/pillow/12.3.0/
- zxing-cpp 3.1.1: https://pypi.org/project/zxing-cpp/3.1.1/
- charset-normalizer 3.4.9: https://pypi.org/project/charset-normalizer/3.4.9/
- idna 3.18: https://pypi.org/project/idna/3.18/
- urllib3 2.7.0: https://pypi.org/project/urllib3/2.7.0/
- certifi 2026.7.22: https://pypi.org/project/certifi/2026.7.22/

## Season 2 compatibility verification — 2026-08-12
- Blizzard's Curse of Ula'tek announcement lists the Season 2 Mythic+ pool as Altar of Fangs, Murder Row, Den of Nalorakk, The Blinding Vale, Voidscar Arena, King’s Rest, Ruby Life Pools and Temple of Sethraliss; KeystoneLens canonicalizes Blizzard's `King’s Rest` label to the external-service spelling `Kings' Rest`.
- Blizzard schedules Midnight Season 2 for Aug 18 (NA) / Aug 19 (EU); this build is transition-ready before that weekly reset.
- WoW 12.1.0 uses TOC interface `120100`; WoW supports comma-delimited Interface values, so the release declares `120007, 120100` during the transition.
- Warcraft Logs zone 56 currently exposes the same eight Season 2 dungeons but is still labeled PTR before the live reset; the Companion resolves Season 2 encounter IDs dynamically and requires one post-reset validation before claiming live WCL coverage.
