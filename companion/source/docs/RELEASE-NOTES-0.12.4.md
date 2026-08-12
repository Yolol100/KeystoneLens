# KeystoneLens 0.12.4 — Season 2 final-prep fixes

- Blizzard's `King’s Rest` spelling (singular *King* + typographic apostrophe) now canonicalizes to the WCL/Raider.IO service name `Kings' Rest`.
- Common Unicode apostrophe variants are normalized for dungeon-name matching without changing unknown display names.
- Season 2 aliases are regression-tested through registry, WCL-zone and Raider.IO paths.
- The Windows build now runs `go vet` for launcher/uninstaller and, after generating the embedded payload, for Setup/bootstrap.
- Release documentation now reflects that the Curse of Ula'tek / 12.1 content update is live while Midnight Season 2 itself starts Aug 18 (NA) / Aug 19 (EU).
- WCL zone 56 remains a pre-reset validation source until live Season 2 reports exist.

Public release still requires Authenticode signing plus native Windows, live WoW and actual CurseForge moderation validation.
