# Testscenario's 0.12.8

## Eén lijst

- Er is exact één spelerslijst.
- Definitieve KL-scores worden zichtbaar wanneer ze binnen het ingestelde 0–100 scorebereik vallen; loading-scores blijven verborgen.
- Class en Role combineren met de score-range; sortering blijft op definitieve KL-score.
- Kolomvolgorde: KL, Role, Player, Class, Spec, Raider.IO, WCL.
- Settings/minimize/close, keyboardbediening, scroll en resize blijven bruikbaar op kleine desktops.
- Een Screenshots-pad moet syntactisch eindigen op `_retail_\Screenshots`.

## Score

- Bevestig met fixturedata: `KL = round(0.5 × RIO + 0.5 × WCL)`.
- Wijzig alleen meta/group/classdata: KL mag niet veranderen.
- Wijzig alleen een andere dungeon: current-dungeon RIO-component mag niet veranderen.
- WCL zonder data = vast WCL 0/100, geen herweging.
- WCL-average gebruikt alleen beschikbare role-aware metrics.
- Applicants uit dezelfde regio/dungeon worden waar mogelijk gebatcht; de score-hot-path vraagt geen combat-eventstream.

## Stop/auto-resume

1. Open listing met applicants.
2. `/kl stop`: Bridge UIT, terminal clear, Companionlijst leeg, oude queued enrichment stopt.
3. Oude applicants mogen daarna niet terugkomen.
4. `/kl on`: huidige listing synchroniseert weer.
5. Sluit/reopen applicantviewer of maak een nieuwe listing: auto-resume volgt de bestaande policy.
6. Delist/re-queue: listing generation stijgt; vertraagde oude snapshots/results worden geweigerd.
7. Volle party of actieve dungeon/Challenge Mode pauzeert nieuwe recruitment-captures.
8. Sluit de Companion met X: watcher-thread en engine-workers stoppen vóór het root-window wordt vernietigd.

## Overlay-scroll/resize

- Meer dan zes applicants: alle rows blijven beschikbaar en de scrollbar werkt.
- Resize verandert alleen de applicantviewport; kolomgeometrie blijft consistent.
- Opgeslagen `overlay_height` wordt na herstart begrensd tegen de beschikbare schermhoogte.

## Transport

- Nieuwe QR-screenshot wordt gedecodeerd.
- Een complete snapshot met minimaal 14 applicants komt volledig aan; zes is alleen de standaard viewportlimiet.
- Normale applicantbursts blijven single-screenshot waar mogelijk; grotere payloads vallen terug op fragmenttransport.
- Fragmenten worden pas na complete delivery verwijderd; handmatige screenshots blijven staan.
- Terminal clear en meerdere gelijktijdige fragmentstreams mogen geen nieuwere sessie overschrijven.
- Na WoW `/reload` wordt de eerstvolgende geldige listing generation als nieuw geaccepteerd.
- Generated `Data.lua`/TOC write-failures zijn zichtbaar en mogen geen half-geldige addonstatus achterlaten.
- Tooltipdata voor een andere dungeon/key/spec wordt fail-closed geweigerd.

## Protocol / lifecycle hardening

- Decode APS1 v12/v13 records en verifieer byte-alignment van member/RIO/Blizzard fallbackvelden.
- Reject malformed/oversized screenshots en inconsistente fragmentmetadata zonder onbegrensde groei.
- Sluit de Companion terwijl Raider.IO/WCL werk in-flight is; late resultaten mogen de gestopte engine niet muteren.
- Start een tweede Companion: de bestaande per-user instance blijft de enige actieve sessie.
- Forceer een niet-nul startup `SystemExit`: de `pythonw.exe` route moet een zichtbare fout en diagnosebestand opleveren.
- Maak `portable-startup.log` naast de launcher onschrijfbaar: de foutlog valt terug naar de tijdelijke map.

## Portable Windows package

1. Pak `KeystoneLens-Portable-0.12.8-Windows-x64.zip` volledig uit naar een normale lokale map.
2. Verifieer dat `START-COMPANION.cmd`, `portable_launcher.py`, `runtime/python.exe`, `runtime/pythonw.exe`, `runtime/python-version.txt`, `app/` en `packages/` aanwezig zijn.
3. Verifieer dat `KeystoneLens-Setup.exe`, `KeystoneLens.exe`, `KeystoneLens-Uninstall.exe` en `KeystoneLens-WoW-Watcher.exe` nergens in de portable ZIP staan.
4. Start `START-COMPANION.cmd`: de runtimecheck slaagt en de GUI opent zonder aparte Python- of Windows-installatie.
5. Start `START-COMPANION.cmd` opnieuw terwijl de GUI open is: er ontstaat geen tweede Companionproces en de gebruiker krijgt de bestaande-instance melding.
6. Sluit de GUI en start opnieuw: de mutex is vrijgegeven en de Companion opent normaal.
7. Start vanuit een pad met spaties en Unicode; alle relatieve runtime/app/packagepaden blijven geldig.
8. Verplaats alleen `START-COMPANION.cmd` uit de map: de launcher faalt duidelijk en vraagt de volledige ZIP opnieuw uit te pakken.
9. Verwijder/beschadig runtimeversie-metadata: de runtimecheck faalt duidelijk en start de app niet half.
10. Controleer een read-only/locked diagnosepad: startupfouten vallen terug naar een tijdelijk log waar mogelijk.
11. Test Windows taskbar/minimize/close/DPI en de Settings-flow op de beoogde clean-Windows omgeving.
12. Controleer dat de appconfig/DPAPI-credentials van de bestaande Companioncode blijven werken vanuit de portable distributie.

## Release artifact contract

- Core source/CurseForge packaging is twee opeenvolgende builds byte-identiek.
- Source ZIP bevat portable/runtime source en geen `installer/` tree of Windows executable.
- De tag-job bouwt de portable ZIP op `windows-2025` uit exact dezelfde commit.
- De tag moet exact `v0.12.8` bij `VERSION=0.12.8` zijn.
- Final payload bevat source, CurseForge, portable Windows ZIP, audit/release notes, SBOM en SHA256SUMS.
- GitHub provenance en CycloneDX attestations worden geverifieerd vóór de draft release wordt gemaakt.
