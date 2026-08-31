# Uitgavechecklist 0.12.8

## Product/runtime

- [x] Exact één Companion-spelerslijst met instelbare KL-score-range (0–100).
- [x] Score, Class en Role filters combineren deterministisch.
- [x] Exacte 50/50-formule zonder meta/group/setup-score.
- [x] Raider.IO-component en WCL-average zijn current-dungeon-only.
- [x] Delist/re-queue wist de oude queue-generatie en negeert vertraagde oude frames/results.
- [x] Tooltipcache v2 is gebonden aan activity, target key level en applicant specialization.
- [x] Malformed/short APS1 transport en non-finite scorebewijs worden fail-closed geweigerd.
- [x] Companion source blijft observation-only; repository-audit blokkeert input-injectie/process-memory/remote-injection/global hooks.

## Source/repository

- [x] `companion/source/VERSION` is de canonical release identity voor Companion, Bridge en data-addon.
- [x] Repository-audit blokkeert tracked ZIP/EXE/build/release/cachebestanden en gangbare secrets/private keys.
- [x] Legacy `companion/source/installer/` en top-level `executable/` bronpaden zijn verwijderd en worden geweigerd als ze terugkomen.
- [x] Portable Windows source staat onder `companion/source/portable/`; runtime provenance/locks staan onder `companion/source/runtime/windows/`.
- [x] Generated release-assets worden niet in `main` opgeslagen.
- [x] GitHub Actions gebruikt immutable full-SHA pins, expliciete runners en `persist-credentials: false`.
- [x] Dependabot/Dependency Review/`pip-audit` blijven dependency-securitygates.
- [x] Python, Lua, repository-security en native Windows-tests zijn CI-gates.

## Portable Windows packaging

- [x] De gebruiker start alleen `START-COMPANION.cmd`; geen KeystoneLens Setup, Windows-installatie, adminrechten of aparte Python-installatie nodig.
- [x] `runtime/windows/python-runtime.json` is de enige source voor CPython Windows versie/URL/SHA-256.
- [x] Runtimepackages zijn met `--require-hashes --no-deps --only-binary=:all:` vastgezet.
- [x] De portable launcher bewaart `Local\KeystoneLens.Companion.Singleton`; dubbel starten opent geen tweede Companion.
- [x] Niet-nul startup/SystemExit-fouten via `pythonw.exe` geven een zichtbare fout en diagnosebestand.
- [x] De verwachte Pythonversie komt uit meegeleverde runtime-metadata; geen los hard-coded patchnummer in de launcher.
- [x] De builder verifieert staged runtime, maakt de deterministische ZIP, pakt dezelfde ZIP opnieuw uit en verifieert opnieuw.
- [x] CI weigert `KeystoneLens-Setup.exe`, `KeystoneLens.exe`, `KeystoneLens-Uninstall.exe` en `KeystoneLens-WoW-Watcher.exe` in de portable ZIP.
- [x] Native Windows-tests behouden DPAPI/configvalidatie zonder de oude Go/Setup executables te bouwen.
- [ ] Clean-Windows extract/start/close/restart/double-start en taskbar/DPI acceptance zijn handmatig geslaagd.
- [ ] Unicode/long/read-only/locked portable paden zijn op een schone Windows-machine gecontroleerd.

## Packaging/supply chain

- [x] CurseForge ZIP heeft exact één top-level `KeystoneLensBridge/` map, matching TOC en geen EXE.
- [x] Bron-ZIP bevat portable/runtime source maar geen legacy installerbron of Windows binaries.
- [x] ZIP-integriteit wordt gecontroleerd en de core releasebuild draait tweemaal deterministisch.
- [x] Getagde release-assets krijgen SHA-256 checksums en GitHub provenance/CycloneDX attestations.
- [x] Een tag moet exact `v<VERSION>` zijn; anders stopt de workflow.
- [x] De releaseworkflow muteert geen bestaande GitHub Release en commit geen generated binaries naar `main`.

## Externe public-release gates

- [ ] Live WoW tooltip/screenshot/Bridge + Companion Data acceptance slaagt op de beoogde Retail client.
- [ ] Authenticated eerste-live Warcraft Logs `/api/v2/client` parse-matrix is gecontroleerd.
- [ ] CurseForge game-version/flavor/channel/dependencymetadata matcht het exact gevalideerde artifact.
- [ ] GitHub Dependency Graph, branch protection/rulesets en secret scanning/push protection zijn door de owner/admin gecontroleerd.
- [ ] Owner/legal review heeft de observation-only externe Companion beoordeeld tegen de actuele Blizzard EULA/policygrens.

Een groene CI-run bewijst source/buildcorrectheid. Live WoW-, clean-Windows-, CurseForge-, repository-admin- en policy/legal-gates blijven afzonderlijk vereist voor volledig publiek production-ready.
