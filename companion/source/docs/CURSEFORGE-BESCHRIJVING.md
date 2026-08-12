# KeystoneLens Bridge 0.12.7 — CurseForge project copy

## Summary

Mythic+ Group Finder bridge for the KeystoneLens Windows Companion, with local applicant transport and optional cached WCL tooltip data.

## Description

KeystoneLens Bridge reads applicants from your own WoW Retail Mythic+ Group Finder listing and transports that snapshot to the separate KeystoneLens Companion. The addon itself makes no Warcraft Logs HTTP requests and never automatically invites, declines or kicks players.

### Features

- automatic applicant snapshots while actively recruiting;
- local Raider.IO evidence available to the Companion;
- QR/screenshot transport from WoW to the local Windows Companion;
- cached local WCL tooltip lines through `KeystoneLensCompanionData`;
- capture pauses when a normal party reaches five players, a party dungeon starts, or recruitment ends;
- visible, unobfuscated Lua source.

### Commands

- `/kl off` or `/kl stop` — stop the current recruitment capture round;
- `/kl on` — enable capture;
- `/kl status` — show current state;
- `/kl sync` — request a fresh snapshot;
- `/kl help` — show commands.

### Companion

The Windows Companion is distributed separately from the CurseForge addon archive. Follow the project installation instructions for the current Companion release.

### Privacy

Transport uses screenshots created by World of Warcraft while recruitment capture is active. KeystoneLens keeps Blizzard's normal screenshot feedback intact. The Companion processes KeystoneLens transport frames locally.

### Credits and license

KeystoneLens Bridge is a transport fork based on ApplicantScout by Antrakt and includes the BSD-3-Clause `luaqrcode` library. License notices are included in the addon archive.
