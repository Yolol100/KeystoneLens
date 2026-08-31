# CurseForge upload — KeystoneLens Bridge 0.12.8

Upload the generated Bridge artifact from the tagged release:

`KeystoneLensBridge-0.12.8-CurseForge.zip`

Do **not** upload the Companion source bundle or portable Windows ZIP as the WoW addon file.

The release build verifies that the archive contains exactly one addon root, `KeystoneLensBridge/`, with a matching `KeystoneLensBridge/KeystoneLensBridge.toc`, and that no executable is present. Keep the root folder name unversioned; the file name may carry the version.

Recommended file settings:

- use **Beta** while live WoW/Season 2 acceptance is still open;
- change to **Release** only after the final live acceptance matrix passes;
- select only Retail game versions actually validated on the released client;
- retain the included MIT and third-party notices;
- configure dependencies/optional dependencies consistently with the project metadata and TOC;
- use the 0.12.8 release notes/project copy from `CURSEFORGE-BESCHRIJVING.md`.

CurseForge approval remains a platform/moderation decision and cannot be pre-certified by local CI.
