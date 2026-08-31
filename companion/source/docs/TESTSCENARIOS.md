# Testscenario's 0.12.8

## Companion / score

- Er is exact één spelerslijst; alleen definitieve KL-scores binnen de actieve filters renderen.
- `KL = round(0.5 × RIO + 0.5 × WCL)` blijft vast; ontbrekende WCL-data is 0 voor de WCL-helft en veroorzaakt geen herweging.
- Class/Role/scorefilters combineren deterministisch en opgeslagen UI-voorkeuren overleven restart.
- Sluiten met X stopt watcher, netwerkclients en engineworkers vóór de UI wordt vernietigd.

## Queue / transport

- `/kl stop` leegt de actuele queue en oude enrichment mag niet terugkomen.
- Delist/re-queue verhoogt de generation; vertraagde oude frames/results mogen de nieuwe listing niet overschrijven.
- Fragmenten worden pas na complete delivery verwijderd; gewone screenshots blijven staan.
- Twee incomplete fragmentstreams kunnen naast elkaar bestaan zonder elkaars recoverybestanden te verwijderen.
- `/reload` van WoW mag de eerstvolgende nieuwe listinggeneration niet als stale laten afwijzen.
- Een volle party of actieve dungeon pauzeert nieuwe recruitmentcaptures vóór de volgende geplande screenshot.

## Context / tooltip

- Activity, target key en applicant spec moeten overeenkomen voordat schema-v2 KL-regels zichtbaar zijn.
- Rollback naar een oudere name-only Bridge mag de v2-cache niet als geldige actuele score interpreteren.
- Generated Companion Data write-failures moeten zichtbaar falen en geen halfgeschreven TOC/Data-paar achterlaten.

## Portable Windows contract

1. Bouw `KeystoneLens-Portable-0.12.8-Windows-x64.zip` tweemaal vanaf exact dezelfde tree; SHA-256 moet byte-identiek zijn.
2. Pak de ZIP opnieuw uit en start `runtime\python.exe -I portable_launcher.py --verify`; alle imports en runtimeversie moeten slagen.
3. Controleer dat `START-COMPANION.cmd`, `RUNTIME.json`, `runtime\python.exe`, `runtime\pythonw.exe`, `app\keystonelens_companion` en `packages` aanwezig zijn.
4. Controleer dat `KeystoneLens-Setup.exe`, custom `KeystoneLens.exe`, `KeystoneLens-Uninstall.exe` en `KeystoneLens-WoW-Watcher.exe` nergens in de ZIP staan.
5. Controleer dat `runtime\Scripts\pip.exe` niet wordt meegeleverd; pip is alleen build-time.
6. Start `START-COMPANION.cmd` vanaf een pad met spaties. De Companion moet dezelfde uitgepakte map gebruiken en geen globale Python nodig hebben.
7. Start `START-COMPANION.cmd` een tweede keer terwijl de eerste draait. De named mutex `KeystoneLens.Companion.Singleton` moet een tweede instance blokkeren.
8. Verplaats de complete uitgepakte map en start opnieuw; er mogen geen registry/Start-menu/install-path assumptions bestaan.
9. Forceer een ontbrekend/kapot runtimebestand; het startvenster moet de verificatiefout tonen in plaats van een stille mislukking.
10. Verwijder de portable map na afsluiten. Er hoort geen productinstallatie achter te blijven; lokale gebruikersconfig onder `%LOCALAPPDATA%\KeystoneLens` is aparte user data.

## Live WoW / netwerk

- Test actuele Raider.IO-data, geen-data en 429/Retry-After.
- Test Warcraft Logs auth/no-data/rate-limit met echte releasecredentials vóór publieke release.
- Test representatieve resoluties/UI-scales, repeated captures en Bridge + Companion Data co-load in de echte WoW Retail client.
