# KeystoneLens

> **Portfoliostatus:** Flagship · actieve ontwikkeling · WoW-addon en Windows Companion

## In één oogopslag

KeystoneLens combineert een WoW Retail-addon met een portable Windows Companion voor veilige, lokale recruitmentanalyse. De repository legt nadruk op reproduceerbare Windows-builds, gecontroleerde dependencies en releasebewijs.

| Onderdeel | Bewijs |
| --- | --- |
| Doelgroep | WoW-guilds en recruiters die kandidaatdata lokaal willen analyseren |
| Stack | Python, Tkinter, Lua, Windows portable runtime, GitHub Actions |
| Kwaliteit | Regressies, Windows-platformchecks, dependency review en CodeQL |
| Release | Deterministische portable ZIP, checksums en attestations |
| Privacy | Screenshottransport en lokale verwerking; geen verborgen automatische game-acties |

## Snel starten

1. Download een gevalideerde portable ZIP uit een GitHub Release.
2. Pak de volledige ZIP uit naar één map.
3. Start `START-COMPANION.cmd`.
4. Download daarnaast de afzonderlijke `KeystoneLensBridge-<versie>-CurseForge.zip` release-asset, pak die uit in de WoW Retail addonmap en volg de in-product instructies.

## Architectuur

```text
WoW addon → lokale screenshotcode → Windows Companion
                                  ↘ Raider.IO / Warcraft Logs-verrijking
                                   → lokale analyse en Companion-data
```

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

## Projectstatus, roadmap en support

KeystoneLens wordt actief ontwikkeld. Volgende mijlpalen horen als issues of release-notes bij een concrete versie; er worden vanuit deze README geen releasedata beloofd. Meld reproduceerbare bugs via [GitHub Issues](https://github.com/Yolol100/KeystoneLens/issues) zonder account-, log- of privégegevens.

## Licentie

Deze repository gebruikt een gemengd licentiemodel. De Bridge-addon onder `addon/KeystoneLensBridge/` valt onder de MIT-licentie; andere onderdelen hebben geen algemene open-sourcelicentie. Zie [LICENSE-SCOPE.md](LICENSE-SCOPE.md) en de licentiebestanden per component voor de bindende scope.
