# KeystoneLens Companion 0.12.8

KeystoneLens spiegelt applicants uit je eigen WoW Retail Mythic+ Group Finder-listing naar één Windows-lijst en verrijkt alleen die spelers met Raider.IO en Warcraft Logs.

## Wat je ziet

De overlay toont applicants pas zodra hun KL-score definitief is. Je kunt filteren op een KL-scorebereik van 0–100, Class en Role. Settings bepaalt welke optionele kolommen zichtbaar zijn. De instellingen, filters, vensterpositie en gekozen hoogte worden lokaal onthouden.

`KL Score = 50% Raider.IO + 50% Warcraft Logs`.

De Raider.IO-helft gebruikt alleen bewijs voor de dungeon waarvoor je nu host. De Warcraft Logs-helft gebruikt rolbewuste openbare rankingmetrics voor hetzelfde character/spec/dungeon. Ontbrekende WCL-data blijft 0/100 voor de vaste WCL-helft; de formule wordt niet stil herwogen.

De Bridge en Companion gebruiken een generation-gebonden APS1/QR-transport. Oude frames van een vorige listing mogen een nieuwere queue niet overschrijven. Fragmenten worden pas verwijderd nadat een complete snapshot is afgeleverd. Gewone WoW-screenshots worden niet verwijderd.

## Commands

- `/kl stop` of `/kl off` — stop applicant-capture en nieuwe online lookups voor de huidige groep;
- `/kl on` — direct weer inschakelen;
- `/kl status` — korte status;
- `/kl sync` — huidige listing opnieuw synchroniseren;
- `/kl help` — toon deze commands.

De Bridge pauzeert nieuwe recruitmentcaptures wanneer een normale party vol is of een dungeon/actieve Mythic+ start. Een nieuwe geldige listing kan de recruitmentflow weer activeren.

## Portable Windows Companion

1. Download `KeystoneLens-Portable-0.12.8-Windows-x64.zip`.
2. Pak de **hele** ZIP uit naar een normale map, bijvoorbeeld `C:\KeystoneLens`.
3. Dubbelklik `START-COMPANION.cmd`.
4. Open Settings en kies je `_retail_\Screenshots`-map.
5. Vul voor de volledige score optioneel je Warcraft Logs Client ID/Secret in.

Niet nodig:

- geen `KeystoneLens-Setup.exe`;
- geen Windows-installatie of registerwijziging;
- geen administratorrechten;
- geen apart geïnstalleerde Python;
- geen custom `KeystoneLens.exe`.

De uitgepakte map bevat wel `runtime\python.exe` en `runtime\pythonw.exe`. Dat zijn de gebundelde upstream Python-runtimebestanden die de Tkinter Companion nodig heeft. Open ze niet zelf; `START-COMPANION.cmd` controleert en gebruikt ze automatisch. De build-only pip-command shims worden niet meegeleverd.

De portable launcher gebruikt dezelfde Windows named mutex als de eerdere launchercontracten (`KeystoneLens.Companion.Singleton`), zodat een tweede start geen tweede Companionproces opent.

## WoW addon

Installeer `KeystoneLensBridge-0.12.8-CurseForge.zip` via CurseForge of handmatig en doe `/reload`. De Windows Companion/runtime zit bewust niet in de CurseForge addon-ZIP.

KeystoneLens nodigt, weigert of kickt nooit automatisch spelers.
