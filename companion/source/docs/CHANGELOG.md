# Changelog


## 0.12.7 — Package consistency, crash-safe update recovery and API hardening

- Reworked Windows Setup into a KeystoneLens-styled decision/progress/completion flow with one launch-mode choice, real runtime-download byte progress, expandable installation details and a bounded install log.
- Added optional `Start when World of Warcraft Retail starts` behavior through a path-validated lightweight Windows watcher; no game memory access, injection or gameplay automation is used.
- Desktop shortcut creation now defaults off on a fresh install; Start menu registration remains automatic.
- Added safe cancel handling before the atomic commit phase and removed duplicate normal error popups between WPF Setup and the Go bootstrap.
- Added the WoW watcher to build, PE-resource, uninstall and Authenticode signing/verification pipelines; it now suppresses redundant Companion launches when the exact installed Companion is already running.
- Closing Setup from the initial decision screen is treated as an explicit cancellation instead of a successful installer exit.
- Fixed embedded Windows PowerShell script encoding by writing a UTF-8 BOM before execution.
- Fixed the dynamically generated `KeystoneLensCompanionData.toc`: it no longer declares an `IconTexture` asset that the Companion does not materialize at runtime.
- Added a regression test that keeps generated TOC metadata limited to files the runtime actually installs.
- Fixed interrupted Setup recovery so an `.old` rollback tree is restored when the active install directory is missing, instead of being discarded on the next run.
- Stale backup cleanup now occurs only after the replacement tree passes staged runtime verification.
- Raider.IO invalid/malformed HTTP 200 payloads are now retryable errors and are never cached as legitimate 0-score evidence.
- Added controlled network failure-matrix coverage for Raider.IO and Warcraft Logs.
- WoW Screenshots autodetection now refuses ambiguous multiple known Retail installs and requires an explicit folder choice instead of silently selecting the first one.
- Crash logging now records timestamp, FATAL severity, component and product version while retaining its size bound.
- Added atomic write-failure regression coverage for config and generated CompanionData files.
- Kept APS1 transport/schema, Season 2 registry, scoring behavior and the published `KeystoneLensBridge` addon contents unchanged apart from release metadata.

## 0.12.6 — State continuity and Windows trust hardening

- Fixed partial applicant-frame merging so unavailable rows are retained across listing-context changes until a complete Blizzard snapshot proves removal.
- Preserved confirmed region/default-realm context when partial APS1 frames omit version metadata.
- Kept WCL/Raider.IO evidence across title/comment-only listing edits while invalidating queues only when dungeon/key/region actually changes.
- Fixed QR decode precedence so incomplete fragments cannot mask a complete APS1 payload in the same or later decode pass.
- Replaced destructive Windows path decisions based on environment variables with Known Folder/GetSystemDirectory APIs.
- Added COM initialization/thread-affinity and `CoTaskMemFree` handling around Windows Known Folder resolution.
- Changed shutdown ordering to signal HTTP clients closed before joining enrichment workers.
- Made CPython installer footprint/path options explicit and corrected runtime wording to “dedicated per-user” rather than implying the embeddable distribution.
- Added regression coverage plus a 30,000-case randomized APS1 parser/fragment smoke run.

## 0.12.5 — Release hardening and runtime maintenance
- Malformed/short `APS1` QR payloads are rejected through the controlled parser path instead of raising an `IndexError`.
- Non-finite score inputs (`NaN`/`Inf`) are treated as unusable zero evidence and can no longer clamp to a maximum score.
- Raider.IO in-memory profile caches now enforce TTL, future-timestamp rejection and hard entry limits.
- Warcraft Logs cache rows now validate timestamps, run counts, key levels and finite 0–100 percentile evidence before use.
- Windows uninstall now refuses to delete anything unless its executable is running from the exact KeystoneLens per-user install directory.
- Setup validates rooted Windows profile/temp paths before touching install state.
- Private CPython runtime updated from 3.13.14 to 3.13.15 and pinned to Python.org's published Windows x64 SHA-256.
- Runtime dependency wheel hashes revalidated against the current official PyPI artifacts; no dependency churn was needed.

## 0.12.4 — Season 2 final-prep fixes
- `King’s Rest` en overige gangbare Unicode-apostrofvarianten canonicaliseren nu betrouwbaar naar `Kings' Rest` voor WCL/Raider.IO.
- Season 2 alias-regressietests uitgebreid over registry, WCL-zone en Raider.IO.
- `go vet` geïntegreerd in de echte Windows buildvolgorde; bootstrap wordt gecontroleerd nadat `payload.zip` is gegenereerd.
- Releasebronnen/documentatie bijgewerkt naar live Curse of Ula'tek / 12.1-contentupdate en Season 2-start op 18 aug (NA) / 19 aug (EU).
- WCL zone 56 blijft expliciet post-reset te valideren zolang Warcraft Logs die catalogus nog als PTR markeert.

## 0.12.3 — Midnight Season 2 compatibility
- TOC compatibility uitgebreid naar `120007, 120100`.
- Season 2 registry van PTR-preload naar de 12.1 Season 2-ruleset gepromoveerd.
- Season 2-dungeonnamen en WCL zone 56 expliciet getest.
- LFG-dungeonnamen gecanonicaliseerd voor Blinding Vale en Kings' Rest-varianten.
- Hardcoded activity-ID mapping gedegradeerd tot legacy fallback; live WoW activity info blijft leidend.

## 0.12.2

- Restored the overlay's default KL range to 84–100 while keeping the user-selectable 0–100 range filter.
- Fixed the current APS1 v12/v13 applicant parser: `application_member_count` was incorrectly consumed twice, shifting Blizzard fallback fields in non-empty current snapshots. Added exact Lua-writer-compatible v12/v13 record tests.
- Hardened APS1 fragment reassembly with separate length, trailer-CRC metadata and full logical-payload CRC validation.
- Added bounded screenshot/QR image limits, fragment-stream limits and bounded watcher retry/bookkeeping caches.
- Made Raider.IO/WCL clients shutdown-aware after in-flight network calls and prevented late result writes after Companion shutdown.
- Hardened Windows process lifecycle with per-user single-instance launch, kill-on-close Job Object ownership, isolated Python startup and exact installed-path process termination.
- Added a maintenance mutex so install/repair/uninstall cannot race each other, and switched installer/uninstaller system-tool launches to absolute System32 paths.
- Fixed Repair self-copy handling and first-install rollback cleanup.
- Bounded crash-log growth and updated the generated data-addon TOC to the current Retail interface.
- Added current Raider.IO/WCL parser contract tests, installer/security contracts and stricter release-package verification.
- Corrected release documentation so WCL category averaging, score defaults and unresolved external signing/native-runtime gates match the implementation.

## 0.12.1

- Replaced `pyzbar` with `zxing-cpp 3.1.1` to use a current Windows x64 wheel compatible with the dedicated CPython 3.13 runtime.
- Locked the complete Windows runtime dependency graph to exact versions and SHA-256 wheel hashes.
- Moved CPython into a KeystoneLens-dedicated per-user runtime directory and added best-effort dedicated-runtime removal during uninstall.
- Added a real Repair/Modify path in Windows Installed Apps and preserved existing Desktop/autostart preferences during update/repair.
- Fixed uninstall cleanup for redirected/OneDrive Desktop folders by resolving the Windows Desktop Known Folder instead of assuming `%USERPROFILE%\\Desktop`.
- Added deterministic Windows icon, VERSIONINFO and DPI-aware/asInvoker manifest resources to Setup, launcher and uninstaller.
- Added root-level source test configuration, QR backend contract tests and release/package contract checks.
- Added a machine-readable runtime SBOM and signing/verification workflow documentation.
- Kept Authenticode, native-Windows, live-WoW and CurseForge moderation as explicit external release gates rather than claiming unverified readiness.

## 0.12.0

- Added a dual-handle KL score range filter (0–100), plus class and role filters. The previous hard 84+ display floor is removed.
- Added persistent Overlay column settings for Role, Class, Spec, Raider.IO and Warcraft Logs. Hiding Class/Role also hides its dependent filter; hiding Raider.IO/WCL does not change KL scoring.
- Added active-filter count, Reset filters, filtered/result count, clearer empty states and automatic table reflow when columns are hidden.
- Split pure filtering/normalization from Tk rendering and debounce preference persistence; display-only settings no longer restart network/watcher runtime.
- Fixed a watcher race where a screenshot deleted between directory enumeration and stat could abort a polling pass.
- Fixed keyboard accessibility in the score slider: Tab now leaves the control normally; Up/Down switches the active handle and Left/Right adjusts it.
- Fixed runtime reconfiguration so clearing an invalid Screenshots setup cannot leave the previous watcher running.
- Removed obsolete Blizzard screenshot-status suppression code. Normal WoW screenshot feedback remains visible.
- Added a compact Windows x64 bootstrap installer with branded progress UI, SHA-256 verification of the official Python runtime, Start Menu registration, uninstall support, and optional launch/desktop/autostart finish actions.
- Added clean CurseForge packaging: the CurseForge ZIP contains only the WoW addon tree; the Companion installer is distributed separately inside the master release ZIP.

## 0.11.5

- Overlay shows only applicants with a final KL Score of 84 or higher; lower and still-loading scores stay out of the visible list.
- Added a compact Class dropdown above the table; it lists only classes currently present among KL 84+ applicants and filters the list immediately.
- Class and Spec are now separate columns in the single applicant list.
- Role icons reduced to text-scale; Role header and icons share an 11 px optical left offset while the physical column gutters stay equal.
- Fixed Retail 12.x LFG member parsing to the current 17-value `GetApplicantMemberInfo` return order.
- Applicant list completeness is cross-checked and partial reads keep polling until every readable LFG member is captured.
- QR transport uses 1 physical pixel per module; normal applicant bursts stay single-frame up to 1400 APS1 bytes and larger payloads fall back to bounded 320-byte fragments.
- Blizzard screenshot status remains suppressed while QR pixels stay present until the screenshot result event for reliability.
- Each new LFG `CreateListing` gets a queue-generation marker. Delist/re-queue clears the old applicant state immediately and delayed frames/results from the previous generation are ignored.
- WCL enrichment now batches up to 10 applicants per region/dungeon request and uses stable character dungeon ranking metrics only in the score hot path; serial recent-report/event scans no longer block KL completion.
- WCL realm-catalog lookup is lazy and only runs as a miss fallback; normal realms avoid that extra first-use request.
- WCL batch results are persisted with one cache rewrite, and same-dungeon re-queues at another keylevel reuse valid cached ranking evidence.
- Raider.IO raw character profiles are cached independently of keylevel/dungeon interpretation so re-queues can reuse the same current profile response.
- Removed the obsolete recommendation/group-fit implementation and related dead registries/helpers after the single-list 50/50 score architecture made them unreachable.
- Windows minimize/restore now temporarily uses a normal top-level window so the taskbar button restores the borderless overlay correctly.
- WoW TOC icon paths now use the extensionless `IconTexture` convention used by Raider.IO.
- Added a Windows application icon for the Companion taskbar entry.
- Settings dialog redesigned as a flatter 480 px form with clearer labels, one section divider, fixed footer actions and improved focus visibility.
- Removed redundant settings intro/copy, simplified Warcraft Logs helper text and kept the Save action visible on short desktops.
- Settings keyboard handling now respects focused Browse/Show/Cancel controls instead of treating every Enter press as Save.
- Settings validation now rejects incorrect offline/non-existing folder shapes instead of accepting any missing path.
- Settings titlebar now uses a single bold `Settings` title instead of a separate KeystoneLens brand/context pair.
- Primary Save button now has an explicit lighter-blue hover state matching the existing KeystoneLens accent.
- Recruitment capture now auto-pauses silently when a normal Mythic+ party reaches 5 members or the player enters/starts a party dungeon; roster-only state no longer keeps screenshot transport alive after the LFG listing ends.
- Auto-paused capture stays paused while the party is still full/in the dungeon, but a later explicit new listing or reopened applicant viewer can resume recruitment once the pause condition is gone.
- Applicant viewport keeps its scrollbar for overflow and adds a persistent vertical resize grip; manual height is remembered without changing table column geometry.
- Closing the Companion stops the local screenshot watcher and enrichment workers immediately.
- Capture lifecycle policy moved into a small pure Lua module so full-party/dungeon/listing decisions can be regression-tested independently of the WoW runtime.

## 0.11.4

- Frontend switched to English throughout the Companion UI and runtime status messages.
- Role header is centered exactly over the tank/healer/DPS icons.
- Added more vertical spacing around the `All players` summary.
- Renamed the table header from `WCL gem.` to `WCL`.
- Tightened the overlay and WCL column to remove excess right-side whitespace.

## 0.11.3

- Raider.IO-detailtekst vereenvoudigd: `runscore 370.0 (+12)` wordt `Beste run: +12`.
- De officiële Raider.IO-runscore blijft intern ongewijzigd gebruikt voor de RIO-berekening.

## 0.11.2

- Raider.IO's eigen hoogste exact-dungeon runscore is nu de primaire RIO-scorebron (70%).
- RIO normaliseert die officiële runscore tegen Raider.IO's gepubliceerde on-time basisscore van het gezochte keylevel.
- Hoogste dungeon-key en hoogst scorende dungeonrun worden apart bijgehouden, zodat een hogere maar slechter scorende run de officiële best-scorecontext niet overschrijft.
- Recente dungeonervaring blijft 20% en role evidence 10% binnen het RIO-deel.
- KL blijft exact 50% Raider.IO + 50% Warcraft Logs.
- Release packaging sluit `__pycache__`, `.pyc` en `.pytest_cache` expliciet uit.

## 0.11.1

- UI: tekst in de rolkolom vervangen door compacte vectoriconen voor tank, healer en DPS; geen class-kleuring toegevoegd.
- Raider.IO-half verfijnd met rol-specifieke score-evidence naast exact-dungeon key, timing en recente repeat-runs; KL blijft exact 50% RIO / 50% WCL.
- WCL-gemiddelde voorkomt dubbele throughputweging door gecorreleerde rankingmetrics eerst per rol in categorieën samen te voegen.
- WCL execution-reports worden alleen gebruikt wanneer de fight-spec overeenkomt met de LFG-spec.
- Damage-taken voor DPS/healer wordt tegen passende peers genormaliseerd; tanks worden niet op raw damage intake gescoord omdat WCL tank-survivabilityranking deprecated is.
- Publieke commandset blijft bewust beperkt tot on/off, status, sync en help; `stop` blijft alleen een alias van `off`.

## 0.11.0

- UI teruggebracht naar één lijst: KL, rol, speler, class/spec, Raider.IO en WCL-gemiddelde.
- Definitieve KL Score is uitsluitend 50% current-dungeon Raider.IO + 50% current-dungeon Warcraft Logs.
- WCL middelt role-aware rankingpercentielen over de beschikbare parses in de dungeon en verrijkt best-effort met deaths, interrupts, dispels en damage taken uit recente openbare reports.
- Interim scores worden niet meer als eindscore getoond terwijl online enrichment nog laadt.
- `/kl stop|off` stopt de huidige zoekronde; `/kl on`, `/kl status`, `/kl sync` en `/kl help` vormen de minimale publieke commandset.
- Auto-resume toegevoegd voor een nieuwe LFG-listing én voor opnieuw openen van de applicantviewer.
- WCL execution-only evidence kan nu als geldige evidence worden gecachet/getoond.

## 0.10.0

- KL Score vereenvoudigd naar exact 50% Raider.IO + 50% Warcraft Logs.
- Dungeon Fit, Group Fit, Raider.IO meta/compositiebonussen en Blizzard-fallback verwijderd uit de score.
- Exact-dungeonervaring is opgenomen in de Raider.IO-helft.
- WCL-gemiddelde uitgebreid naar alle bruikbare specifieke-dungeonmetrics: playerscore, playerspeed, DPS, boss DPS en rolmetric (WDPS/HPS).
- WCL-kolom blijft één gemiddeld cijfer van 0-100 tonen en dat cijfer vormt exact de helft van KL.
- ★ Groep kiest alleen nog op geldige rolverdeling + hoogste gemiddelde KL Scores; geen setup/meta-bonus.
- WCL zonder bruikbare openbare ranking blijft als vast 0/100 WCL-deel staan; er wordt niet naar andere scorebronnen herwogen.

## 0.9.9

- WCL-kolom toont nu één gemiddelde WCL-score van 0-100.
- De WCL-score is het rekenkundig gemiddelde van alle beschikbare WCL P-metrics (momenteel Points/playerscore + WDPS of HPS).
- Ditzelfde gemiddelde wordt als de 35% WCL-component in de KL Score gebruikt.
- Detailweergave toont zowel het gemiddelde als alle individuele P-metrics.
- Ontbrekende WCL-metrics tellen niet als nul.

## 0.9.8

- Fix: gedeeltelijk leesbare LFG-snapshots leveren nu alle wel leesbare applicants door; de Companion merge-t ze zonder ontbrekende spelers onterecht te verwijderen.
- Fix: `invited`/`none` worden niet langer als verdwenen applicant gefilterd.
- Fix: één Warcraft Logs GraphQL-fout maakt niet langer de volledige batch `fout`; succesvolle partial data blijft bruikbaar en globale batchfouten worden geïsoleerd.
- Diagnose: WCL-fouten worden in de lijst specifieker gelabeld.
- UI: addon-lijsticonen toegevoegd voor Bridge en Companion Data.

## 0.9.7

- Refactor: screenshot lifecycle in de WoW Bridge is nu een expliciete state-machine (`IDLE → BUILDING → SETTLING → WAITING_RESULT`).
- Refactor: screenshot-CVar-lease en Blizzard screenshot-statusonderdrukking zijn uit `Transport.lua` gehaald naar `Core/ScreenshotController.lua`.
- Refactor: Companion scheidt polling van bestand/lifecycle-logica via `transport_pipeline.py`.
- Fix: initial backfill verwerkt historische screenshots in batches; nieuwe live captures worden niet meer minutenlang geblokkeerd door een grote Screenshots-map.
- Fix: oude backfillbestanden slaan de 80ms write-settle over zodra ze aantoonbaar stabiel zijn; recente bestanden behouden de dubbele stat-check.
- Veiligheid: transportscreenshots worden nog steeds pas verwijderd nadat een complete snapshot aan de engine is doorgegeven.
- Diagnostiek: transportproblemen blijven zichtbaar en worden niet meer automatisch overschreven door alleen `Warcraft Logs verbonden`.

## 0.9.6

- Fix: QR blijft zichtbaar tot `SCREENSHOT_SUCCEEDED`/`SCREENSHOT_FAILED` in plaats van direct na `Screenshot()`.
- Fix: screenshot-CVar lease blijft actief tot de capture echt klaar is.
- Betrouwbaarheid: QR-modules terug naar 3 fysieke pixels en render-settle naar 0,30 s.
- Compatibiliteit: WoW Retail interface `120100` toegevoegd.
- Diagnostiek: Companion meldt nieuwe screenshots zonder leesbare KeystoneLens-QR expliciet.

## 0.9.5

- Screenshottransport robuuster: geldige QR-fragmenten blijven op disk totdat een volledige snapshot is samengesteld.
- Voorkomt dat een gemist fragment of Companion-herstart een multi-frame applicant snapshot onherstelbaar maakt.
- Transportscreenshots worden pas na succesvolle volledige snapshotverwerking permanent verwijderd.
- Backfill replay-fix: oudere screenshots kunnen na herstel niet meer alsnog een oude terminal-clear afspelen en de actuele applicantlijst wissen.


## 0.9.4
- WCL-rankings gebruiken nu `compare: Parses` zodat percentielen tegen recente parses uit een tweewekenvenster worden vergeleken.
- Ontbrekende Raider.IO-evidence wordt, net als ontbrekende WCL/Dungeon Fit, niet als kunstmatige nul gewogen.
- Raider.IO runtime-requests worden lokaal gepaced onder de publieke unauthenticated rate limit.
- Officiële Season 2-naam gecorrigeerd naar `Kings' Rest`.

- Live Raider.IO character-enrichment toegevoegd met lokale addondata als veilige fallback.
- Actuele Raider.IO top-run rosters/composities toegevoegd als begrensde dungeon- en group-fit meta.
- KL-eindmodel gewijzigd naar 35% Raider.IO + 35% Warcraft Logs + 15% Dungeon Fit + 15% Group Fit wanneer alle bronnen beschikbaar zijn.
- Ontbrekende bronnen worden herwogen in plaats van als nul gescoord.
- WCL uitgebreid van alleen `playerscore` naar `playerscore` + `wdps` voor tank/DPS of `hps` voor healers.
- `★ Groep` beoordeelt utility, specdiversiteit en live succesvolle dungeoncomposities; DP-state houdt nu de speccompositie bij zodat pruning correct blijft.
- Tooltipcache toont afzonderlijke RIO/WCL/Dungeon-componenten.
- Raider.IO requests gebruiken cache en 429/Retry-After backoff.

## 0.9.3

- Midnight Season 2 registry toegevoegd met de 8 officieel aangekondigde Mythic+-dungeons.
- WCL Season 2 zone 56 toegevoegd; encounter-ID wordt runtime uit de officiële WCL worldData-catalogus opgelost in plaats van gegokt/hardcoded.
- WCL-cachecontext season-aware gemaakt zodat Season 1- en Season 2-evidence nooit door elkaar loopt.
- Onbekende toekomstige dungeonmechanics geven geen verborgen utilitybonus; conservatieve fallback behouden.
- Release opnieuw geaudit op season-mapping, ranking, recommendation en packaging.


## 0.9.3

- Automatische transportcaptures gebruiken tijdelijk lossless PNG en een 1px micro-QR; de companion schaalt de QR-crop voor decode op zonder de volledige screenshot op te blazen.
- De normale transportstatus maakt per stabiele snapshot nog één capture in plaats van twee; gefragmenteerde overflow behoudt extra redundantie.
- Blizzard `Screenshot captured`-feedback wordt alleen tijdens KeystoneLens-captures tijdelijk onderdrukt en direct daarna hersteld.
- QR-supportzichtbaarheid is sessiegebonden en kan niet meer per ongeluk na `/reload` zichtbaar blijven.
- PNG is toegevoegd aan de screenshotwatcher.
- UX/UI opnieuw gecontroleerd: huidige donkere palette, hiërarchie en compacte progressive-disclosure layout blijven behouden; geen onnodige visuele redesign.
- Geselecteerde filters gebruiken alleen nog de duidelijke accentachtergrond (geen dubbele vink/ster-markering) en de `/reload`-statusmelding verdwijnt na een korte actieperiode in plaats van permanent in de footer te blijven staan.
- Testharness gerepareerd zodat alle regressietests daadwerkelijk via script/discovery worden uitgevoerd.

## 0.9.0

- WoW Group Finder is expliciet de source of truth voor de actuele applicantpool.
- Event-driven LFG dirty-signals plus trage recovery-poll.
- APS1 wire v12/v13 scheidt echte Raider.IO-score van Blizzard dungeonScore/context.
- Partial/secret applicant snapshots behouden de laatste geldige lijst.
- Huidige party, inclusief solo host, wordt naar de companion gespiegeld.
- Deterministische Score ↓ ranking uitgebreid met vaste evidence tie-breakers.
- Nieuwe `★ Groep` recommendation met hard-locked partyleden en atomic multi-member applications.
- Exacte bounded recommendation-DP gevalideerd tegen brute-force-orakel; tie-break pruningfix toegevoegd.
- Async WCL-resultaten worden context/revision-safe toegepast.
- WCL-cache krijgt season/metric-context; alleen echte not-found wordt negatief gecachet.
- Midnight Season 1 registry gecentraliseerd; utilityregistry gebruikt alleen gegarandeerde specutility.
- UX uitgebreid zonder dashboardcomplexiteit: `Alles | Tank | Heal | DPS | ★ Groep`.
- Companion-start midden in een al gevulde listing doet een eenmalige newest-first backfill tot 2000 screenshots en pakt de nieuwste complete KeystoneLens-snapshot; daarna gaat de watcher terug naar de kleine live window.

- Overlay vereenvoudigd volgens Windows desktop-UX: lege toestand toont alleen de hoofdactie en status; tabel, filters en scrollbar verschijnen pas wanneer ze nodig zijn.
- Hoofdtabel teruggebracht naar vier besliskolommen: Score, Speler/spec, Raider.IO + dungeonervaring en WCL.
- Spelerdetails zijn nu progressief: pas zichtbaar na selectie en direct weer te sluiten.
- Vensterhoogte past zich aan lege lijst, aantal zichtbare spelers en detailweergave aan.
- Statusregel toont standaard alleen integratiestatus; technische details verschijnen uitsluitend wanneer actie nodig is.
- De `—`-knop minimaliseert de companion naar de Windows-taakbalk zonder watcher, Raider.IO/WCL-verwerking of engine af te sluiten; alleen sluiten beëindigt de app.
- Borderless Windows-window krijgt expliciet taskbar-presence via `WS_EX_APPWINDOW` en gebruikt `SW_MINIMIZE` voor de Windows-minimizeactie.

## 0.8.4

- Scenario-audit uitgebreid naar de volledige companion/addon/installatie/workflow.
- APS1 QR-transport gebruikt nu altijd hex; de raw-binary QR-fallback is verwijderd nadat een echte QR roundtrip bytecorruptie aantoonde.
- WCL aan/uit werkt direct op een al geopende spelerslijst: uitschakelen verwijdert WCL meteen uit de score, inschakelen queued bestaande spelers.
- Verlopen WCL-cache wordt opgeschoond en tijdelijke GraphQL/API-fouten worden niet als langdurige miss bewaard.
- Tijdelijke Blizzard LFG-lockdown wist de laatst geldige spelerslijst niet meer.
- Raider.IO-profielen met geldige character-rating maar ontbrekende detailruns krijgen een conservatieve ratingfallback in plaats van automatisch 0.
- Dynamische tooltipdata verhuisd naar de aparte lokale addon `KeystoneLensCompanionData`; normale companionupdates wijzigen `KeystoneLensBridge` niet meer.
- Installer beschermt een nieuwere reeds geïnstalleerde CurseForge-versie tegen downgrade en heeft backup/rollback voor upgrades.
- Oude automatische LFG-entry/playstyle-hooks worden niet meer bij login/ticker geactiveerd; transport blijft de runtime-hoofdtaak.
- Instellingen normaliseren corrupte/onjuiste configtypes veilig.
- UI uitgebreid met niet-kleurafhankelijke actieve filtermarkering, zichtbaar/totaal-aantal, scrollbar, muiswiel en Home/End-selectie.
- Ongebruikte Python-constanten en aantoonbaar dode Lua-helpercode verwijderd.
- Beginnersdocumentatie, troubleshooting, privacy, techniek, releasechecklist en testscenario's bijgewerkt.
- Gelokaliseerde realmnamen worden via de officiële Warcraft Logs-realmcatalogus naar de juiste Retail-slug vertaald; tijdelijke catalogusfouten worden later opnieuw geprobeerd.
- WCL-auth-, enable/disable- en clientwissel-races kunnen geen oude resultaten meer terug in een nieuwere spelerslijst plaatsen.
- `START-HIER.cmd` controleert nu ook de QR-runtime en herstelt een beschadigde dependencyomgeving automatisch.
- Instellingen sluiten alleen na een bevestigde succesvolle opslag; bij een schrijffout blijven de ingevoerde waarden staan.
- De statusbalk adviseert `/reload` pas nadat lopende WCL-verrijking klaar is.
- Zichtbare termen zijn consequent Nederlands gemaakt en interne score-uitleg is uit de snelle beslisinterface gehaald.

## 0.8.3

- WCL volledig optioneel gemaakt; ontbrekende credentials blokkeren Raider.IO-only gebruik niet meer.
- WCL-query gebruikt Mythic+ `playerscore` in plaats van DPS-throughput.
- GraphQL-fouten worden niet meer als langdurig "niet gevonden" gecachet.
- Wisselen van target key kan niet meer blijven hangen op een oude WCL-aanvraag.
- Deterministische beste-naar-laagste sortering toegevoegd.
- Gecachte KeystoneLens + WCL-regels onder Group Finder-tooltips toegevoegd.
- Verouderde WCL-resultaten worden niet toegepast wanneer character/spec/context tijdens een lopende aanvraag verandert.
- Tooltip toont WCL median + best + key + run count en voorkomt een uitgestelde hover-race naar de verkeerde speler.
- Raider.IO-profielen met `hasRenderableData=false` worden genegeerd.
- Legacy ApplicantScout-instellingen/PVEFrame-verplaatsing/Auto Hi worden niet meer automatisch geactiveerd door KeystoneLens.
- Companion-UI compacter gemaakt en instellingen teruggebracht tot Screenshots + optionele WCL-credentials.
- WCL Client Secrets worden op Windows met DPAPI beschermd.
- Professionele distributiestructuur: app, addon, scripts en docs gescheiden.
