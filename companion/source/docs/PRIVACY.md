# Privacy en credentials

- KeystoneLens gebruikt de Warcraft Logs Client Credentials-flow alleen wanneer jij Client ID en Client Secret invult.
- Credentials staan nooit in de WoW-addon, QR-payload, gegenereerde tooltipdata of publieke release-ZIP.
- De lokale companionconfig staat in `%LOCALAPPDATA%\KeystoneLens\config.json`. Op Windows wordt het Client Secret met DPAPI beschermd en niet als leesbare tekst opgeslagen.
- De gegenereerde addon `KeystoneLensCompanionData` bevat alleen publieke spelerstatistieken, scoremetadata en tijdstempels die nodig zijn voor de in-game tooltip.
- `KeystoneLensBridge` doet geen externe HTTP-calls.
- KeystoneLens verwijdert alleen screenshots waarvan een geldige eigen APS1/QR-transportpayload succesvol door de companion is opgenomen. De verwijdering gebruikt een directe filesystem-delete (`Path.unlink`) en gaat dus niet via de Windows-prullenbak. Gewone WoW-screenshots worden nooit als KeystoneLens-bestand verwijderd.
- De KL Score is lokaal berekend en wordt niet teruggestuurd naar Raider.IO of Warcraft Logs.
