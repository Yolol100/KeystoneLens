# KeystoneLens Companion 0.12.8

KeystoneLens spiegelt applicants uit je eigen WoW Retail Mythic+ Group Finder-listing naar één Windows-lijst en verrijkt alleen die spelers met Raider.IO en Warcraft Logs.

## Score en filtering

`KL Score = 50% Raider.IO + 50% Warcraft Logs`.

De score blijft current-dungeon-only en bevat geen verborgen meta-, setup-, group- of classbonus. De Companion toont alleen definitieve scores en ondersteunt de bestaande score-, Class- en Role-filters. Raider.IO en Warcraft Logs blijven afzonderlijk zichtbaar als bewijs/context.

## Commands

- `/kl stop` of `/kl off` — stop applicant-capture en nieuwe lookups voor de huidige groep;
- `/kl on` — weer inschakelen;
- `/kl status` — korte status;
- `/kl sync` — huidige listing opnieuw synchroniseren;
- `/kl help` — commands.

Delist/re-queue gebruikt een nieuwe listing-generatie, zodat vertraagde screenshots of resultaten van een vorige queue niet terugkomen. De Bridge stopt nieuwe recruitment-screenshots bij een volle party of actieve dungeon/Mythic+.

## Companion: portable, zonder Windows-installatie

1. Download `KeystoneLens-Portable-0.12.8-Windows-x64.zip`.
2. Pak de **hele** ZIP uit naar een gewone map, bijvoorbeeld `C:\KeystoneLens`.
3. Dubbelklik `START-COMPANION.cmd`.
4. Open Settings en kies `_retail_\Screenshots`.
5. Vul voor de volledige score optioneel je Warcraft Logs Client ID/Secret in.

Niet nodig: `KeystoneLens-Setup.exe`, een Windows-installatie, administratorrechten, register-/Start-menu-installatie of een apart geïnstalleerde Python.

De portable map bevat zijn eigen lokale Python-runtime en hash-locked packages. Laat `runtime`, `app`, `packages`, `portable_launcher.py` en `START-COMPANION.cmd` bij elkaar staan. Een tweede startpoging opent geen tweede Companion. Bij een niet-nul startupfout verschijnt een foutmelding en wordt een diagnosebestand geschreven.

## WoW addon

Installeer `KeystoneLensBridge-0.12.8-CurseForge.zip` via CurseForge of handmatig in AddOns en doe `/reload`. De Windows Companion zit bewust niet in de CurseForge-addon-ZIP.

KeystoneLens nodigt, weigert of kickt nooit automatisch spelers.
