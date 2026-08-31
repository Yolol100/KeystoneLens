# KeystoneLens

KeystoneLens bestaat uit twee runtime-onderdelen:

1. `addon/KeystoneLensBridge/` — de WoW Retail addon die recruitmentdata veilig naar lokale screenshots transporteert en Companion-tooltipdata toont.
2. `companion/source/app/` — de Windows Companion die screenshots decodeert en Raider.IO/Warcraft Logs-verrijking berekent.

De Windows Companion wordt vanaf 0.12.8 als **portable ZIP** geleverd. Er is geen KeystoneLens Setup-programma, geen eigen KeystoneLens `.exe`, geen registerinstallatie, geen administratorinstallatie en geen apart geïnstalleerde Python nodig. Pak `KeystoneLens-Portable-<versie>-Windows-x64.zip` volledig uit en start `START-COMPANION.cmd`.

De portable ZIP bevat bewust een private upstream CPython-runtime (`runtime/python.exe` en `runtime/pythonw.exe`) omdat de Tkinter Companion Python nodig heeft. Dat zijn runtimebestanden, geen KeystoneLens-installer of custom launcher. De build-only pip-command shims worden vóór packaging verwijderd.

## Repository-indeling

- `addon/KeystoneLensBridge/` — canonieke Bridge-bron.
- `companion/source/app/` — Companion runtime.
- `companion/source/portable/` — portable launcher en Windows builder.
- `companion/source/runtime/` — hash-locked runtime dependencies en het officiële Python runtimecontract.
- `companion/source/data-addon/` — Companion Data-bron.
- `companion/source/scripts/` — repository-audit en deterministische packaging.
- `companion/source/docs/` — actuele release-, security- en testdocumentatie.

`companion/source/VERSION` is de canonieke productversie. Generated ZIPs, EXEs, checksums, caches en lokale runtime-output worden niet op `main` opgeslagen.

## Releasecontract

CI valideert de bron, volledige regressies, native Windowsgedrag, dependency locks en deterministische packaging. De portable Windows ZIP wordt op een Windows-runner tweemaal onafhankelijk opgebouwd; beide SHA-256 hashes moeten gelijk zijn. Daarna wordt dezelfde ZIP opnieuw uitgepakt en met de gebundelde runtime geverifieerd.

Een tag `v<VERSION>` kan alleen een draft GitHub Release maken met de gevalideerde Bridge-, source- en portable-ZIP plus checksums/attestations. Live WoW-, schone Windows-, CurseForge- en policyacceptatie blijven aparte publicatiegates.
