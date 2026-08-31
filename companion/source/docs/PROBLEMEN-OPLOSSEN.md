# Problemen oplossen — 0.12.8

## Companion start niet

- Pak de **hele** portable ZIP uit; start niet rechtstreeks vanuit de ZIP.
- Laat `START-COMPANION.cmd`, `portable_launcher.py`, `runtime`, `app` en `packages` in dezelfde uitgepakte map staan.
- Start alleen `START-COMPANION.cmd`; een KeystoneLens Setup of installed launcher is niet nodig.
- Als de runtimecontrole mislukt, blijft het CMD-venster open en staat de technische fout in `%TEMP%\keystonelens-portable-check.txt`.
- Als de grafische Companion daarna met een niet-nul fout stopt, verschijnt een foutmelding en wordt `portable-startup.log` naast de launcher geschreven; als die map niet schrijfbaar is wordt een tijdelijk log gebruikt.
- Een tweede startpoging opent bewust geen tweede Companion. Sluit eerst de bestaande Companion als je opnieuw wilt starten.

## Geen spelers

- Controleer of Bridge en Companion allebei 0.12.8 zijn.
- Controleer `_retail_\Screenshots` in Instellingen.
- Open je eigen Mythic+ listing.
- Gebruik `/kl status`.
- Gebruik `/kl on` als je eerder `/kl stop` gebruikte.
- Gebruik `/kl sync` om een verse snapshot te forceren.

## KL blijft op `…`

Raider.IO en/of Warcraft Logs is nog aan het laden. 0.12.8 toont bewust geen tijdelijke halve eindscore.

## Oude KL-regels verdwijnen na listing/spec-wijziging

Dit is bedoeld fail-closed gedrag. Tooltipcache v2 is gebonden aan de exacte activity, target key en applicant spec. Na een gewijzigde scoringcontext moet de Companion nieuwe data schrijven en moet WoW die data via `/reload` opnieuw laden voordat de nieuwe KL-regels geldig zijn.

## WCL `geen data`

Voor dit character/spec is geen bruikbare openbare ranking-evidence gevonden in de huidige dungeon. Het vaste WCL-deel blijft dan 0/100.

## WCL fout/auth/limiet

- Controleer Client ID/Secret;
- wacht op quota-reset bij `limiet`;
- controleer character-realm bij `realm fout`;
- een individuele characterfout mag succesvolle resultaten uit dezelfde batch niet ongeldig maken.

## Niet alle applicants zichtbaar

- Open de huidige applicantviewer en gebruik `/kl sync` voor een verse complete snapshot.
- Zes spelers is alleen de zichtbare viewportgrootte, niet de datalimiet.
- Bij delist/re-queue wordt de oude queue-generatie gewist. Vertraagde screenshots/resultaten van de vorige generatie worden genegeerd.
- Zeer grote payloads gebruiken fragmenttransport; verwijder KeystoneLens-screenshots niet handmatig terwijl zo'n transport bezig is.
