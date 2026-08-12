# KeystoneLens Companion 0.12.7

KeystoneLens spiegelt applicants uit je eigen WoW Retail Mythic+ Group Finder-listing naar één Windows-lijst en verrijkt alleen die spelers met Raider.IO en Warcraft Logs.

## Wat je ziet

De overlay toont applicants pas zodra hun KL-score definitief is. Boven de tabel kun je de lijst direct verfijnen met:

- een scorebereik van 0–100 met twee handles; standaard staat dit op 84–100, maar je kunt de range bewust lager zetten;
- Class;
- Role;
- Reset filters.

Settings bepaalt welke optionele kolommen zichtbaar zijn: Role, Class, Spec, Raider.IO en WCL. Wanneer Class of Role wordt verborgen, verdwijnt ook de gekoppelde filter. Raider.IO/WCL verbergen wijzigt alleen de presentatie; de KL-score blijft dezelfde 50/50-berekening gebruiken. De instellingen en actieve filters worden lokaal onthouden.

De tabel past zich automatisch aan verborgen kolommen aan en toont een zichtbaar/totaal-aantal plus actieve-filterstatus.

## Score

`KL Score = 50% Raider.IO + 50% Warcraft Logs`

Er zijn geen losse Dungeon Fit-, Group Fit-, meta-, setup- of classbonussen meer.

### Raider.IO 50%

De RIO-helft gebruikt alleen bewijs voor de dungeon waarvoor je nu host. De officiële Raider.IO-runscore van de hoogst scorende bekende run in die dungeon vormt 70% van het RIO-deel; recente herhaling in dezelfde dungeon vormt 20% en rolbewijs 10%. De gewone Raider.IO-rating blijft zichtbaar als herkenbare context, maar andere dungeons geven geen verborgen bonus aan de KL Score.

### Warcraft Logs 50%

De WCL-helft is een rolbewust rekenkundig gemiddelde van stabiele 0–100 WCL-categorieën voor dit character/spec in de huidige dungeon. `playerscore` en `playerspeed` tellen ieder als eigen categorie; sterk gecorreleerde throughputmetrics worden eerst binnen één throughputcategorie gemiddeld zodat dezelfde performance niet meerdere keren wordt meegeteld.

Rankingmetrics omvatten waar WCL ze levert:

- iedereen: `playerscore`, `playerspeed`;
- DPS/tank: `wdps`, `dps`, `bossdps`;
- healer: `hps`, `tankhps`, `dps`, `bossdps`.

KeystoneLens vraagt deze rankingmetrics in batches van maximaal 10 applicants op. Zware report-/eventscans blokkeren de KL-score niet meer. Ontbrekende rankingmetrics worden binnen het WCL-gemiddelde overgeslagen; ze worden niet verzonnen.

Als helemaal geen bruikbare openbare WCL-data bestaat, blijft het vaste WCL-deel 0/100. De formule wordt dan niet stiekem herwogen naar 100% Raider.IO.

## Commands

- `/kl stop` of `/kl off` — stop applicant-capture en nieuwe online lookups voor de huidige groep;
- `/kl on` — direct weer inschakelen;
- `/kl status` — korte status;
- `/kl sync` — huidige listing opnieuw synchroniseren;
- `/kl help` — toon alleen deze commands.

Na `/kl stop` wordt de huidige Companion-lijst leeggemaakt. KeystoneLens schakelt zichzelf weer in zodra een nieuwe actieve LFG-listing wordt gedetecteerd of wanneer jij later de applicantviewer opnieuw opent om weer spelers te zoeken.

Iedere nieuw aangemaakte LFG-listing krijgt bovendien een nieuwe queue-generatie. Daardoor wordt bij delist/re-queue de oude applicantlijst direct vervangen en mogen vertraagde screenshots of online resultaten van de vorige queue niet terugkomen.

Tijdens recruitment stopt de Bridge nu automatisch met nieuwe QR-screenshots zodra een normale party 5 spelers telt of zodra je een party-dungeon/actieve Mythic+ ingaat. Alleen een al lopende fysieke screenshot kan dan nog afronden; er wordt geen nieuwe capture meer gepland. Als de actieve LFG-listing eindigt, houdt alleen een resterende party-roster het transport niet meer kunstmatig actief.

De Companion toont standaard maximaal zes rijen tegelijk. Bij meer spelers verschijnt de verticale scrollbar. Rechtsonder zit daarnaast een kleine verticale resize-grip: sleep die omlaag om meer applicants tegelijk te tonen. De gekozen hoogte wordt lokaal onthouden.

Het kruisje in de Windows Companion stopt de lokale screenshotwatcher, Raider.IO/WCL-workers en UI direct. Een WoW-addon kan vanuit de game-sandbox niet live horen dat een extern Windows-venster is gesloten; de Bridge zelf stopt daarom op de bovengenoemde WoW-lifecycle-signalen (groep vol, dungeon actief of listing beëindigd).

## Installatie

### Companion

1. Start `KeystoneLens-Setup.exe`.
2. Volg de installatievoortgang. De installer haalt de benodigde Windows-runtime en Python-packages automatisch op.
   De runtime wordt per gebruiker in een eigen KeystoneLens-runtimepad geplaatst; packages worden met vastgezette SHA-256-hashes gecontroleerd.
3. Kies na afloop eventueel `Start KeystoneLens`, `Create desktop shortcut` en `Start with Windows`. Autostart staat standaard uit.
4. Open Settings en kies `_retail_\Screenshots`.
5. Vul voor de volledige score optioneel je Warcraft Logs Client ID/Secret in.

### WoW addon

Installeer alleen `KeystoneLensBridge-0.12.7-CurseForge.zip` via CurseForge/manual AddOns-installatie en doe `/reload`. De Companion-executable zit bewust niet in de CurseForge-addon-ZIP.

KeystoneLens nodigt, weigert of kickt nooit automatisch spelers.
