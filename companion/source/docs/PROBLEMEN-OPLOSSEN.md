# Problemen oplossen — 0.12.7

## Geen spelers

- Controleer of Bridge en Companion allebei 0.12.7 zijn.
- Controleer `_retail_\Screenshots` in Instellingen.
- Open je eigen Mythic+ listing.
- Gebruik `/kl status`.
- Gebruik `/kl on` als je eerder `/kl stop` gebruikte.
- Gebruik `/kl sync` om een verse snapshot te forceren.

## KL blijft op `…`

RIO en/of WCL is nog aan het laden. 0.12.7 toont bewust geen tijdelijke halve eindscore.

## WCL `geen data`

Voor dit character/spec is geen bruikbare openbare ranking-evidence gevonden in de huidige dungeon. Het vaste WCL-deel blijft dan 0/100.

## WCL fout/auth/limiet

- Controleer Client ID/Secret;
- wacht op quota-reset bij `limiet`;
- controleer character-realm bij `realm fout`;
- een individuele characterfout mag succesvolle resultaten uit dezelfde batch niet ongeldig maken.

## WCL blijft lang op `loading...`

0.12.7 gebruikt geen seriële recente-reportscan meer voor de KL-score. Applicants uit dezelfde regio/dungeon worden in batches van maximaal 10 bevraagd. Bij een koude cache kan de openbare API nog steeds tijd kosten, maar één trage applicant hoort de overige succesvolle batchresultaten niet te blokkeren.

## Niet alle applicants zichtbaar

- Open de huidige applicantviewer en gebruik `/kl sync` voor een verse complete snapshot.
- Normale queues met meer dan zes spelers horen volledig in de Companion te staan; zes is alleen de zichtbare viewportgrootte, niet de datalimiet.
- Bij delist/re-queue wordt de oude queue-generatie gewist en start de nieuwe listing leeg. Vertraagde screenshots/resultaten van de vorige generatie worden genegeerd.
- Zeer grote payloads gebruiken automatisch fragmenttransport; verwijder KeystoneLens-screenshots niet handmatig terwijl zo'n transport bezig is.

## `/kl stop` staat nog uit

Open de applicantviewer opnieuw of maak een nieuwe LFG-listing; auto-resume hoort dan in te schakelen. Anders `/kl on`.
