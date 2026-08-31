# KeystoneLens Companion

De actuele Companionbron staat onder `companion/source/`.

Windowsdistributie is portable: pak `KeystoneLens-Portable-<versie>-Windows-x64.zip` volledig uit en dubbelklik `START-COMPANION.cmd`. Er is geen KeystoneLens Setup-executable, geen Windows-installatie en geen apart geïnstalleerde Python nodig.

De portable package gebruikt:

- `source/app/` voor de Companion;
- `source/portable/` voor start/buildlogica;
- `source/runtime/` voor de officiële CPython-bronhash en exact hash-locked Python packages.

De private Python-runtime in de ZIP blijft noodzakelijk voor Tkinter en de QR/network dependencies. De oude custom launcher/uninstaller/WoW-watcher/Setup-stack is geen onderdeel meer van de huidige architectuur.

Zie `source/README-NL.md`, `source/docs/SNELSTART.md` en `source/docs/UITGAVE-CHECKLIST.md` voor gebruik en releasegates.
