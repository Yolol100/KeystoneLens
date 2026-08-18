# Testscenario's 0.12.8

## Eén lijst

- Er is exact één spelerslijst.
- Definitieve KL-scores worden zichtbaar wanneer ze binnen het ingestelde 0–100 scorebereik vallen; loading-scores blijven verborgen.
- Een kandidaat blijft tijdens RIO/WCL loading buiten de zichtbare lijst totdat de definitieve KL-score bekend is.
- Class en Role staan in de samenvattingsbalk; filters combineren met de score-range en verdwijnen wanneer hun kolom in Settings verborgen is.
- Class-selectie filtert direct, reset de scroll naar boven en houdt de KL-sortering intact.
- Kolomvolgorde: KL, Role, Player, Class, Spec, Raider.IO, WCL
- Tank/healer/DPS staan samen en sorteren op definitieve KL-score.
- Tijdens RIO/WCL loading staat KL op `…`.
- Alle zes fysieke kolomgaps blijven gelijk; Role-header en role-iconen gebruiken dezelfde 11 px optische offset naar links.
- Settings, minimize en close staan in één titlebar; minimize en close delen exact dezelfde verticale glyph-middenlijn.
- Het woord Settings staat 4 px optisch naar links binnen een onveranderde klikzone.
- Settings-popup blijft volledig bruikbaar op een desktop van 1024×480; Save, Cancel, Browse en Show blijven zichtbaar en uitgelijnd.
- Settings gebruikt geen geneste kaartkaders of losse introzin; secties worden met spacing en één subtiele divider gegroepeerd.
- Enter op Browse/Show/Cancel activeert die control en wordt niet dubbel als Save verwerkt; close/minimize keyboard-invokes stoppen event-propagatie.
- Ook een tijdelijk offline Screenshots-pad moet syntactisch eindigen op `_retail_\Screenshots`.

## Score

- Bevestig met fixturedata: `KL = round(0.5 × RIO + 0.5 × WCL)`.
- Wijzig alleen meta/group/classdata: KL mag niet veranderen.
- Wijzig alleen een andere dungeon: current-dungeon RIO-component mag niet veranderen.
- WCL zonder data = vast WCL 0/100, geen herweging.
- WCL-average gebruikt alleen beschikbare metrics.

## Role-aware WCL

- DPS: Score/Speed + WDPS/DPS/Boss DPS.
- Tank: Score/Speed + WDPS/DPS/Boss DPS.
- Healer: Score/Speed + HPS/Tank HPS + DPS/Boss DPS.
- Maximaal 10 characters uit dezelfde regio/dungeon gaan in één core GraphQL-request; 14 applicants worden dus in 10+4 gebatcht.
- De score-hot-path vraagt geen `recentReports`, `reportData` of losse combat-eventstreams.
- Check dat rankingdata uit een andere dungeon niet wordt meegenomen.
- Re-queue naar een ander keylevel in dezelfde dungeon mag geldige WCL-cachedata hergebruiken.

## Stop/auto-resume

1. Open listing met applicants.
2. `/kl stop`: Bridge UIT, terminal clear, Companionlijst leeg, oude queued enrichment stopt.
3. Wacht: oude applicants mogen niet terugkomen.
4. `/kl on`: huidige listing synchroniseert weer.
5. Herhaal `/kl stop`, sluit/reopen applicantviewer: auto-resume.
6. Herhaal `/kl stop`, delist en maak nieuwe listing: auto-resume.
7. `/kl status` toont AAN/UIT en auto-startstatus.
8. Onbekende oude debugcommands worden niet publiek uitgevoerd.
9. Delist en maak direct opnieuw dezelfde listing: de oude applicantlijst wordt onmiddellijk gewist, de queue-generatie stijgt en vertraagde oude snapshots/results mogen niet terugkomen.
10. Vul een normale party tot 5 spelers: Bridge pauzeert vóór een volgende scheduler-capture en plant geen terminal-clear screenshot voor die auto-pauze.
11. Start/enter een party-dungeon of actieve Challenge Mode: zelfde stille auto-pauze, ook wanneer de listing nog actief lijkt.
12. Open de applicantviewer terwijl de party nog vol/in de dungeon is: géén auto-resume. Verlaat de pauseconditie en open de viewer opnieuw: auto-resume mag dan wel.
13. Een expliciete nieuwe `CreateListing` na de pauseconditie mag auto-resume afdwingen, ook als de zichtbare listingvelden identiek zijn.
14. Sluit de Windows Companion met X: watcher-thread en engine-workers stoppen vóór het root-window wordt vernietigd.

## Overlay-scroll/resize

- Meer dan zes applicants: alle rows blijven gerenderd en de verticale scrollbar is zichtbaar.
- Sleep de resize-grip omlaag: alleen de applicantviewport wordt hoger; vensterbreedte en kolomgeometrie blijven gelijk.
- Opgeslagen `overlay_height` wordt na herstart opnieuw toegepast en tegen de beschikbare schermhoogte begrensd.
- Bij voldoende hoogte verdwijnt de scrollbar automatisch; bij weer kleiner maken verschijnt hij opnieuw.

## Transport

- Nieuwe QR-screenshot wordt gedecodeerd.
- Een complete snapshot met minimaal 14 applicants komt volledig in de Companion aan; alleen definitieve applicants die aan de actieve filters voldoen renderen, en zes blijft alleen de standaard viewportlimiet.
- Normale applicantbursts tot 1400 APS1-bytes blijven single-screenshot; grotere payloads vallen terug op 320-byte fragmenten.
- Fragmenten worden pas na complete delivery verwijderd.
- Handmatige screenshots blijven staan.
- Terminal clear mag geen nieuwe sessie overschrijven.
- Twee fragmentstreams mogen tegelijk pending zijn; een complete stream verwijdert niet de recovery-screenshot(s) van de andere incomplete stream.
- Laat de Companion open, doe in WoW `/reload`, en maak/refresh daarna een listing: de eerstvolgende post-reload generation moet als nieuw worden geaccepteerd en mag niet als stale worden geweigerd.
- Forceer een generated `Data.lua` write-failure: de Companion toont een tooltip-syncfout in plaats van een normale live-status.
- Forceer die write-failure bij de allereerste generated-addon sync: er mag geen TOC achterblijven dat naar een ontbrekende `Data.lua` verwijst.
- Verwijder na een geslaagde sync alleen de generated TOC en voer dezelfde semantische sync opnieuw uit: de TOC wordt hersteld zonder onnodige Data.lua-wijziging.
- Laat een score voor dungeon/key/spec A schrijven, wijzig de actieve listing naar dungeon/key B en verifieer dat de oude KL-regels niet verschijnen.
- Wijzig dezelfde applicant naar een andere spec en verifieer opnieuw fail-closed gedrag.
- Schrijf v2-data met 0.12.8, laad daarna een oude name-only Bridge: `_G.KeystoneLensTooltipCache` moet nil blijven en de oude Bridge mag geen KL-score tonen.

## Protocol / lifecycle hardening
- Decode a non-empty APS1 v12 and v13 applicant record and verify member count, RIO fields and Blizzard fallback fields remain byte-aligned.
- Reject malformed/oversized screenshot input and inconsistent fragment metadata without unbounded fragment/cache growth.
- Close the Companion while Raider.IO/WCL work is in-flight and verify no late result mutates the stopped engine.
- Start a second Companion instance and verify the existing per-user instance remains authoritative.
- Attempt overlapping Setup/Repair/Uninstall and verify the maintenance mutex rejects the second destructive operation.
- Repair an installed copy using the cached Setup executable and verify Setup never copies the repair executable onto itself.

## Windows Setup UX / launch modes

1. Fresh install: Setup starts on a KeystoneLens decision page with exactly one of `Start manually`, `Start with Windows`, or `Start when World of Warcraft Retail starts` selectable. Manual is the fresh default.
2. Fresh install: `Create desktop shortcut` is off by default; `Launch KeystoneLens after installation` is on by default.
3. During Python runtime download, verify the status shows transferred bytes/total bytes when the server provides Content-Length and the shared progress bar never restarts.
4. Expand `Details` and verify preparation, runtime verification, pinned dependency names, staged verification, Windows integration and selected launch behavior are visible. No WCL credentials or other secrets may be logged.
5. Cancel during download or dependency installation: the new application tree is not committed. Cancel during the atomic apply phase is disabled until the verified swap completes.
6. Select `Start with Windows`: only `Startup\KeystoneLens.lnk` is present for KeystoneLens launch behavior.
7. Select `Start when World of Warcraft Retail starts`: only `Startup\KeystoneLens-WoW-Watcher.lnk` is present; the watcher starts the Companion for a new `Wow.exe` whose full path contains a `_retail_` path component.
8. Launch an unrelated `Wow.exe` outside `_retail_`: the watcher must ignore it.
9. Restart WoW Retail with a new process ID while the watcher remains running: it may trigger the Companion again; the Companion singleton prevents duplicate live instances.
10. Update/repair preserves the previously selected launch mode and current desktop-shortcut preference unless the user changes them.
11. Force a normal Setup error after the WPF UI has loaded: show one branded error page, not a second generic bootstrap MessageBox.
12. Uninstall removes both possible Startup shortcuts, stops the exact installed WoW watcher, and removes the new helper with the installation tree.
13. Verify Setup, launcher, uninstaller and WoW watcher PE resources all report version `0.12.8.0`. Public direct-download signing remains a separate external gate.
