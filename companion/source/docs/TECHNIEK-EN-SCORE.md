# Techniek en KL Score — 0.12.7

## Source of truth

WoW bepaalt welke applicants op dit moment bestaan. Online services verrijken alleen identities die nog in de actuele of laatst betrouwbare Group Finder-snapshot staan.

## Eén ranking

De UI heeft één lijst `Alle spelers`. Er bestaat geen aparte Tank/Heal/DPS/Group-tab en geen groepsadvies-score meer.

## Exacte formule

`KL = 0,50 × RIO_component + 0,50 × WCL_average`

Beide componenten zijn 0–100. Geen andere factor kan punten toevoegen of aftrekken.

## Raider.IO-component

De 0–100 RIO-component gebruikt alleen Raider.IO-data en blijft specifiek voor de huidige dungeon/rol:

- 70%: de officiële Raider.IO `score` van de hoogst scorende bekende run in exact deze dungeon, genormaliseerd tegenover Raider.IO's gepubliceerde on-time basisscore voor het gezochte keylevel;
- 20%: recente timed/near-target repeat evidence in exact deze dungeon;
- 10%: hoeveel van de actuele Raider.IO-score aantoonbaar in de aangevraagde rol is verdiend.

De officiële runscore is bewust de primaire bron omdat Raider.IO daarin keylevel en timing al samenweegt. Een run die precies de gepubliceerde on-time score van het gezochte keylevel heeft, wordt als 94/100 genormaliseerd; snellere of sterkere runs houden daardoor nog ruimte tot 100. Als de API geen officiële runscore levert, valt alleen dat 70%-deel terug op de bekende exacte-dungeon-key in plaats van ontbrekende API-data als een kunstmatige nul te behandelen.

Raider.IO publiceert zowel een all-role score als rol-specifieke scores. De rolcomponent voorkomt dat een hoge score die hoofdzakelijk als andere rol is verdiend volledig wordt behandeld als bewijs voor de aangevraagde rol. Als live rolvelden ontbreken, wordt die 10% conservatief gevuld met de exacte dungeon-evidence.

## WCL-average

Warcraft Logs wordt per character + spec + huidige dungeon bevraagd. `byBracket:true` gebruikt keystone-brackets. KeystoneLens gebruikt de beschikbare rankingpercentielen van die spec/dungeon en bundelt maximaal 10 applicants uit dezelfde regio/dungeon in één GraphQL-request.

Rankingmetrics:

- iedereen: `playerscore`, `playerspeed`;
- DPS: `wdps`, `dps`, `bossdps`;
- tank: `wdps`, `dps`, `bossdps`;
- healer: `hps`, `tankhps`, plus `dps` en `bossdps` voor damagebijdrage.

De query gebruikt `compare:Parses`. De hot path vraagt geen recente reports en geen losse combat-eventstreams op; de KL-score hoeft daardoor niet op meerdere seriële reportrequests per applicant te wachten.

Om dubbele weging te voorkomen worden sterk gecorreleerde metrics eerst samengevoegd in categorieën:

- Score;
- Speed;
- role-throughput (DPS/tank: WDPS+DPS+Boss DPS, healer: HPS+Tank HPS);
- healer damagebijdrage (DPS+Boss DPS, indien beschikbaar).

`WCL gem.` is daarna het rekenkundig gemiddelde van de beschikbare categorieën. Alle onderliggende rankingmetrics blijven zichtbaar in de detailregel. Ontbrekende data wordt niet verzonnen en wordt niet als kunstmatige nul in een categorie gestopt.

De WCL-cache is per character/spec/dungeon. Een re-queue naar een ander keylevel in dezelfde dungeon hergebruikt daarom geldige rankingdata. Realmcanonicalisatie wordt alleen opgehaald wanneer de normale realm-slug geen character oplevert, zodat een gezonde eerste batch geen extra realm-catalogrequest nodig heeft.

## Stop/start lifecycle

`/kl stop`:

1. Bridge verstuurt een terminal-clear snapshot;
2. Companion verwijdert de actuele applicantstate;
3. queued RIO/WCL-jobs worden geleegd;
4. Bridge stopt applicant-scans en nieuwe snapshots.

Een HTTP-request dat al fysiek onderweg is kan niet betrouwbaar midden in de socketcall worden afgebroken; het resultaat wordt door revision/context-checks genegeerd en er worden na de stop geen nieuwe applicantlookups uit de oude queue gestart.

Auto-resume gebeurt bij een nieuwe active listing of wanneer de applicantviewer opnieuw wordt geopend terwijl een listing actief is. `/kl on` forceert direct resume.

## Transport

- `Core/ScreenshotController.lua`: screenshot lifecycle/CVar-lease;
- `Core/Transport.lua`: WoW snapshot + QR + pause/resume;
- `watcher.py`: detecteert nieuwe screenshots;
- `transport_pipeline.py`: decode, fragments, delivery en veilige cleanup.

Een KeystoneLens-screenshot wordt pas verwijderd nadat een complete snapshot succesvol is verwerkt.

Normale applicantbursts blijven tot 1400 APS1-bytes in één QR-screenshot. Alleen grotere payloads vallen terug op begrensde 320-byte fragmenten. De APS1-header bevat daarnaast een queue-generatie; een nieuwe `CreateListing` forceert een nieuwe generatie zodat oude applicants en vertraagde frames niet in de nieuwe queue kunnen blijven staan.
