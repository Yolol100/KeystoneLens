# KeystoneLens Windows Installer

De actuele releaseversie staat in `companion/source/VERSION`. De publish-workflow controleert die versie tegen Companion-, Bridge- en Windows-buildmetadata voordat een installer wordt gepubliceerd.

Bestandsnaam: `KeystoneLens-Setup-v<VERSION>-Windows-x64.exe`.

Gebruik voor integriteitscontrole uitsluitend `SHA256SUMS.txt` in de repository-root. Dat manifest wordt door de geverifieerde publish-workflow opnieuw opgebouwd en met `sha256sum -c` gecontroleerd, zodat er geen tweede handmatig checksumgetal kan verouderen.

De installer bevat de branded setupflow, progress/details, desktopkeuze, Windows-autostart, optionele WoW Retail-startmodus, repair en uninstall. Authenticode signing blijft een aparte externe releasepoort totdat een echt publishercertificaat/private key beschikbaar is; distribueer de EXE niet als publiek vertrouwde Windows-release voordat die ondertekening en Windows-acceptatietest zijn afgerond.
