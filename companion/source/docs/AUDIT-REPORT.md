# KeystoneLens 0.12.7 audit report

## Status

**WINDOWS/WOW RUNTIME TEST REQUIRED**

Binnen de daadwerkelijk uitvoerbare source-, controlled-runtime-, build-, package-, parser-, UI-smoke-, filesystem-, network-failure- en cross-component contractscope zijn alle gevonden reproduceerbare defects gerepareerd. De resterende gaten vereisen een echte Windows- of WoW-runtime, Authenticode/private signing key of externe distributieservice en zijn op verzoek niet verder uitgevoerd.

## Components

| Component | Confirmed findings | Fixed | Open confirmed | Testniveau |
| --- | ---: | ---: | ---: | --- |
| WoW AddOn | 0 | 0 | 0 | source/package/protocol parity; live WoW niet uitgevoerd |
| Windows companion | 2 | 2 | 0 | 105 tests, compileall, Linux/Xvfb UI-smoke, failure injection |
| Installer | 2 | 2 | 0 | XAML/source failure model, Go vet/build/PE resources; native Windows niet uitgevoerd |
| Updater | 0 apart | n.v.t. | 0 | update/repair is onderdeel van Setup |
| Integratie | 1 | 1 | 0 | APS1/cache/package contract; echte WoW screenshot roundtrip niet uitgevoerd |

## Confirmed findings and repair evidence

`ID | component | root cause | fix | regression evidence`

- `KL-001 | CompanionData integration | generated TOC referenced Media\KeystoneLensIcon although runtime never materialized it | removed unmanaged IconTexture declaration | RED regression failed before fix; generated-addon reproduction + full suite pass`
- `KL-002 | Windows Setup crash recovery | next Setup run deleted .old before checking whether it was the only valid pre-crash install tree | restore .old first when InstallDir is missing; retire stale .old only after staged replacement verification | RED interrupted-swap contract failed before fix; GREEN afterward`
- `KL-003 | Raider.IO enrichment | HTTP 200 invalid JSON / missing character identity was interpreted and cached as legitimate zero-score evidence | fail as retryable malformed-response error and do not cache | RED malformed-200 tests failed before fix; GREEN afterward`
- `KL-004 | WoW installation discovery | autodetect returned the first known Retail Screenshots directory when multiple known installs existed | autodetect only when exactly one unique valid candidate exists; otherwise require manual selection | RED ambiguity test failed before fix; GREEN afterward`
- `KL-005 | Windows Setup UI | WPF XAML used x:Name without declaring the required xmlns:x namespace, so strict XML parsing fails before the installer UI can load | declare the XAML x namespace and regression-parse the embedded XAML | pre-fix XAML reproduction fails with unbound prefix; repaired XAML parse PASS`

Alle vijf staan **CONFIRMED → FIXED**. Er zijn geen open CONFIRMED defects in de uitvoerbare scope.

## Installation and update

- Per-user installmodel, `asInvoker`, dedicated private CPython runtime, exact-path process stopping, maintenance mutex, known-folder path safety en staged replacement zijn source/buildmatig gecontroleerd.
- Setup gebruikt nu een branded decision/progress/completion flow met één launch-mode-keuze, echte byteprogress voor de runtime-download, Details/install.log en safe-point cancellation vóór de atomic commit.
- Een optionele WoW-launch watcher start de Companion alleen voor een nieuw `Wow.exe` waarvan via `QueryFullProcessImageNameW` is bevestigd dat het pad een `_retail_` component bevat.
- Interrupted atomic swap heeft nu expliciete recovery van de laatste geldige `.old` tree vóór nieuw installatiewerk.
- Stale `.old` cleanup gebeurt pas nadat de nieuwe staged runtime importverificatie is geslaagd.
- Config- en generated `Data.lua` replace-failures zijn geïnjecteerd: het vorige geldige bestand blijft intact.
- Fresh install, repair, upgrade, uninstall, reinstall, registry/shortcut failure-injection, disk-full, AV locks en OS shutdown zijn **niet native op Windows uitgevoerd**.
- Setup/launcher/uninstaller/WoW-watcher cross-build als Windows x64 GUI PE en resourceverificatie slagen; artifacts blijven unsigned.

## WoW installation discovery

- Exact één bekende Retail `Screenshots`-map: autodetect PASS.
- Meerdere bekende Retail-installaties: fail-safe naar handmatige selectie PASS.
- Handmatige paden op andere drives, met spaties en Unicode: validation PASS.
- Verkeerde clientvariant (`_classic_` waar Retail vereist is): reject PASS.
- Geen destructieve drive-scan toegevoegd.
- Echte Battle.net/custom multi-drive discovery op Windows is niet uitgevoerd.

## Integration

Werkelijk gegevenspad:

`WoW AddOn → APS1 snapshot/fragment → QR → WoW screenshot → Windows watcher/decoder → enrichment → atomic Data.lua/TOC write → KeystoneLensCompanionData → WoW tooltip consumer`

- Geen localhost-server, WebSocket, named pipe of WoW-process-memoryintegratie aangetroffen.
- APS1 parser ondersteunt de actuele v12/v13 snapshotvormen en v10 fragment envelope.
- `aps1.py` is byte-identiek tussen de aangeleverde 0.12.6 source en 0.12.7; SHA-256: `75f4b6d998358b0cee637ea3d99ce03f9c3aef8bf8f2dde5e6a87087b54b4b71`.
- De volledige gepubliceerde `KeystoneLensBridge` codeboom van 0.12.6 naar 0.12.7 verschilt alleen in TOC-release metadata; de Lua transport/consumercode is ongewijzigd.
- `addon_sync.py` wijzigde in het data-contract alleen door het verwijderen van de niet-bestaande IconTexture metadata; `Data.lua` schema bleef gelijk.
- Daardoor is 0.12.6 ↔ 0.12.7 source-level wire/cachecompatibiliteit sterk bewezen; echte mixed-version Windows/WoW runtime blijft niet uitgevoerd.
- 100.000 deterministisch gerandomiseerde APS1-like payloads: 0 onverwachte exceptions.

## Network and external API failure matrix

Controlled-runtime tests dekken:

- Raider.IO: HTTP 400/401/403/404/409/429/500/502/503, timeout/offline, invalid JSON, malformed successful schema, retry/backoff en no-error-cache behavior.
- Warcraft Logs OAuth: 400/401/403/429/500/502/503 en invalid JSON.
- Warcraft Logs GraphQL: 400/401/403/404/409/429/500/502/503 en invalid HTTP-200 JSON.
- HTTPS endpoints en expliciete timeouts zijn aanwezig; geen `verify=False` of equivalente TLS-disable gevonden.
- Live serviceacceptatie met echte WCL credentials en post-reset Season 2 data is niet uitgevoerd.

## Filesystem, concurrency and crash recovery

- Kritieke config-, WCL-cache-, generated TOC- en `Data.lua` writes gebruiken temp + replace waar relevant.
- Config replace-failure behoudt aantoonbaar het vorige geldige configbestand.
- Generated `Data.lua` replace-failure behoudt aantoonbaar het vorige geldige tooltipbestand en retourneert een foutstatus.
- Single-instance Companion en single-instance maintenance contract zijn aanwezig.
- Shutdown/stale-result lifecycletests blijven groen.
- Echte NTFS locked-file, antivirus, disk-full, power-loss en Windows shutdown failure injection is niet uitgevoerd.

## Security and supply chain

- Geen WoW process-memory read/write, DLL/code injection, gameplay/input automation of localhost gameplay bridge aangetroffen.
- De nieuwe WoW-launch watcher opent kandidaat-`Wow.exe` processen uitsluitend met `PROCESS_QUERY_LIMITED_INFORMATION` om via `QueryFullProcessImageNameW` het executable-pad te valideren; hij leest/schrijft geen gamegeheugen en gebruikt geen injectie/inputautomation.
- Overig `OpenProcess`-gebruik blijft begrensd tot het eigen child-process Job Object en exact-path uninstall process matching.
- Geen gebundelde WCL client secret, API key of private signing key aangetroffen.
- WCL secret persistence gebruikt Windows DPAPI; niet-Windows hosts schrijven het secret niet plaintext weg.
- CPython 3.13.15 is naar python.org gepind met SHA-256.
- Runtime packages zijn exact geversioneerd en hash-locked; SBOM en lock zijn versieconsistent met 0.12.7.
- De vastgezette Windows-wheel hashes zijn op 2026-08-12 tegen de officiële PyPI releasebestanden gecontroleerd.
- Een echte `pip-audit`/OSV vulnerability scan kon in deze runtime niet als executable oracle worden uitgevoerd.
- Authenticode blijft **RELEASE TRUST RISK — unsigned** totdat het echte publishercertificaat wordt gebruikt.

## Logging and UX controlled-runtime evidence

- Crashlog bevat timestamp, `[FATAL]`, productversie, component en exceptiondetails en blijft size-bounded.
- Linux/Xvfb Companion demo/UI-smoke start, rendert en sluit gecontroleerd.
- Settings save-failures geven een veilige foutstatus en vervangen de actieve config niet.
- Installer-XAML is als XML geregressietest; pre-fix ontbrak de `xmlns:x` namespace en faalde strict parsing, repaired XAML parseert correct.
- Native Windows taskbar, first-start, SmartScreen, installer button/cancel interaction en echte error-dialog UX zijn niet uitgevoerd.

## Verification

- Python unit/regression tests: **PASS — 105/105**.
- Python `compileall`: **PASS**.
- Go formatting: **PASS**.
- Go vet: **PASS in payload-aware Windows build order**.
- Windows cross-build/resource verification: **PASS**.
- Linux/Xvfb Companion UI smoke: **PASS**.
- APS1 adversarial pass: **PASS — 100,000 cases, 0 unexpected exceptions**.
- Network failure matrix: **PASS**.
- Atomic file-replace failure injection: **PASS**.
- Multiple-WoW-install ambiguity + custom drive/spaces/Unicode validation: **PASS**.
- 0.12.6 ↔ 0.12.7 source protocol compatibility: **PASS at source/contract layer**.
- ZIP/package traversal, duplicate-entry, symlink, checksum and exact-artifact checks: executed by the 0.12.7 release gate.
- Clean-room source/build/package re-audit: executed after packaging.
- Stable source/build/package pass 1 and pass 2: executed after packaging.

## Masterprompt self-check

| # | Scope | Result |
|---|---|---|
| 1–3 | inventory, source of truth, baseline | DONE |
| 4 | target environments | SOURCE DONE; TARGET RUNTIME SKIPPED |
| 5 | WoW AddOn audit | SOURCE/PACKAGE DONE; LIVE WOW SKIPPED |
| 6 | Windows Companion audit | CONTROLLED DONE; NATIVE WINDOWS SKIPPED |
| 7 | WoW install discovery | CONTROLLED PATH/AMBIGUITY DONE; NATIVE DISCOVERY SKIPPED |
| 8 | AddOn install/update by Companion | N/A for published Bridge; generated data-addon covered |
| 9–10 | compatibility/data exchange | CONTROLLED DONE; REAL QR/WOW ROUNDTRIP SKIPPED |
| 11 | concurrency/file safety | CONTROLLED DONE; NATIVE NTFS/POWER-LOSS SKIPPED |
| 12 | prohibited WoW techniques | DONE |
| 13 | local IPC | N/A — none present |
| 14–15 | network/downloads | CONTROLLED DONE; LIVE/NATIVE DOWNLOAD FAILURES PARTIAL |
| 16 | Windows security | SOURCE/CONTROLLED DONE; NATIVE + VULN ORACLE PARTIAL |
| 17–18 | installer/elevation | SOURCE/XAML/BUILD DONE; NATIVE INSTALL/ELEVATION SKIPPED |
| 19 | signing/release trust | CHECKED; SIGNING NOT POSSIBLE HERE |
| 20 | clean Windows machine | SKIPPED — unavailable |
| 21 | Companion UX | CONTROLLED UI SMOKE DONE; NATIVE UX SKIPPED |
| 22 | logging | DONE WITH CONTROLLED FAILURE TEST |
| 23 | crash recovery | CONTROLLED DONE; TRUE POWER-LOSS SKIPPED |
| 24–25 | bug validation + repair loop | DONE for KL-001..KL-004 |
| 26 | end-to-end scenarios | SOURCE/CONTRACT PARTIAL; REAL WINDOWS↔WOW E2E SKIPPED |
| 27 | adversarial pass | CONTROLLED DONE; TARGET-RUNTIME ADVERSARIAL SKIPPED |
| 28 | clean-room re-audit | SOURCE/BUILD/PACKAGE DONE; TARGET RUNTIME SKIPPED |
| 29 | two stable final rounds | SOURCE/BUILD/PACKAGE DONE; TARGET RUNTIME SKIPPED |
| 30 | release package verification | DONE for produced unsigned package; install execution skipped |
| 31 | forbidden fixes | DONE — none used |
| 32 | final report | DONE |

## Intentionally left outside this environment

Per user instruction, the following are left as external/manual gates rather than blocking more local work:

1. Native Windows 10/11 clean install, repair, update, uninstall and reinstall.
2. Native registry/shortcut rollback injection, NTFS locked-file, disk-full, antivirus/SmartScreen and OS shutdown/power-loss tests.
3. Authenticode signing with the real private publisher certificate and timestamp verification.
4. Live WoW Retail Group Finder, `/reload`, combat/taint/secure-execution and physical screenshot-event tests.
5. Full QR decode through the exact installed Windows `zxing-cpp` wheel; the Linux audit runtime could not install that wheel for execution.
6. Live Raider.IO/WCL Season 2 service acceptance with production credentials/data.
7. CurseForge upload, processing and moderation.

## Release decision

**0.12.7 is clean within the source/controlled-runtime/build/package scope that can actually be executed here.** Er zijn geen open CONFIRMED defects binnen die scope.

De formele masterprompt-status blijft **WINDOWS/WOW RUNTIME TEST REQUIRED**, omdat de definitieve acceptatiepoort echte Windows-, installer- en WoW-runtimebewijzen vereist. Die externe gates zijn op verzoek bewust niet verder uitgevoerd en worden niet als geslaagd voorgesteld.
