# KeystoneLens Bridge transport notice

KeystoneLens Bridge contains a modified transport core derived from **ApplicantScout Addon** by Antrakt.
The upstream transport is MIT licensed. The bundled `Libs/qrencode.lua` library is BSD-3-Clause licensed.

KeystoneLens-specific changes include:

- product identity, SavedVariables and the minimal `/kl` support commands;
- transport-focused defaults with legacy ApplicantScout settings and automatic chat/playstyle actions disabled;
- removal of production-dead fixture exports;
- local Raider.IO profile extraction for the companion snapshot;
- an empty generated tooltip-cache data file;
- cached KeystoneLens/Warcraft Logs lines appended to Group Finder tooltips;
- preservation of the APS1 QR/screenshot wire contract for companion compatibility.

The upstream MIT license and third-party QR license notice are retained in this release.
