# Uitgavechecklist 0.12.8

## Product/runtime

- [x] Exact één Companion-spelerslijst met deterministic score/Class/Rolefilters.
- [x] KL-score blijft exact 50% Raider.IO + 50% Warcraft Logs.
- [x] Queue-generation, stop/resume, fragmentdelivery en stale-result guards zijn regressiegedekt.
- [x] Tooltipcache v2 is gebonden aan activity, target key en spec en rollbackt fail-closed.
- [x] Companion blijft observation-only; repository-audit blokkeert input-injectie/process-memory/remote-process automatisering.
- [x] Raider.IO/WCL request-, quota-, retry- en cachegrenzen zijn fail-closed getest.

## Source/repository

- [x] `companion/source/VERSION` is de canonieke release identity.
- [x] Generated ZIP/EXE/build/release/cachebestanden staan niet op `main`.
- [x] De oude `companion/source/installer/` en root `executable/` source stack is verwijderd.
- [x] `.gitignore`, `.gitattributes`, `.editorconfig`, full-SHA Action pins en `persist-credentials: false` zijn repositorygates.
- [x] CodeQL analyseert de actuele Pythonruntime; obsolete installer-only Go analysis is verwijderd.
- [x] Dependabot/pip-audit volgen zowel app requirements als het portable runtime lock.

## Portable Windows packaging

- [x] Windowsgebruik vereist alleen de volledig uitgepakte `KeystoneLens-Portable-0.12.8-Windows-x64.zip` en `START-COMPANION.cmd`.
- [x] Geen `KeystoneLens-Setup.exe`, custom `KeystoneLens.exe`, uninstaller of WoW-watcher wordt gebouwd/geleverd.
- [x] Geen Windows register-, Start-menu- of administratorinstallatie.
- [x] De officiële CPython 3.13.15 buildinput is vastgezet in `runtime/windows-x64.json` met SHA-256.
- [x] Exacte runtime packages zijn hash-locked met `--require-hashes --no-deps`.
- [x] Build-only pip/runtime package-management shims, `packages/bin`, generated `RECORD`, `__pycache__` en `.pyc/.pyo` worden vóór packaging verwijderd.
- [x] Verificatie/packaging gebruikt `-B`, zodat controles geen nieuwe bytecode in de stage kunnen terugschrijven.
- [x] `python.exe`/`pythonw.exe` blijven als noodzakelijke upstream interpreterruntime in de portable map.
- [x] Single-instance gedrag blijft behouden via `KeystoneLens.Companion.Singleton`.
- [x] Twee onafhankelijke schone Windows runners bouwen elk één portable ZIP; alleen byte-identieke SHA-256 output gaat door.
- [x] CI pakt daarna de canonieke ZIP opnieuw uit en verifieert runtime/imports én de afwezigheid van legacy/custom executables en generated build artifacts.
- [x] Tagrelease bevat Bridge-, source- en portable-ZIP plus SHA-256 checksums en attestations; release wordt draft aangemaakt.

## CurseForge public-release gate

- [ ] Project game-version/flavor is beperkt tot daadwerkelijk live gevalideerde Retail-versies.
- [ ] File channel blijft Beta zolang live WoW/Windows/policy acceptance openstaat.
- [ ] De geüploade CurseForge ZIP is exact de door CI gevalideerde `KeystoneLensBridge-0.12.8-CurseForge.zip`.

## Clean Windows / live WoW gate

- [ ] Op een schone ondersteunde Windows x64 machine: ZIP uitpakken, `START-COMPANION.cmd` starten, Settings openen en schoon afsluiten.
- [ ] Pad met spaties/Unicode en verplaatsbare uitgepakte map zijn handmatig gecontroleerd.
- [ ] AV/SmartScreengedrag van de ZIP en de door Python.org geleverde runtime is geobserveerd; geen claim zonder echt bewijs.
- [ ] Live WoW tooltip-context/rollbackmatrix, screenshottransport en Bridge + Companion Data co-load slagen.
- [ ] Authenticated eerste-live Warcraft Logs `/api/v2/client` parse-matrix met echte releasecredentials is gecontroleerd.
- [ ] Blizzard performance/policy/legal review is expliciet afgerond.

## Repository-admin gate

- [ ] GitHub Dependency Graph is ingeschakeld zodat Dependency Review blocking kan worden.
- [ ] `main` heeft passende PR-only protection/required checks/conversation resolution.
- [ ] GitHub secret scanning/push protection en security alerts zijn waar beschikbaar geactiveerd.

Een groene CI-run bewijst source/buildcorrectheid en portable artifactintegriteit. De handmatige WoW-, clean-Windows-, CurseForge-, repository-admin- en policy/legal-gates blijven afzonderlijk vereist voor publieke production-ready status.
