# KeystoneLens Windows Installer

Installer voor KeystoneLens 0.12.7.

Bestandsnaam: `KeystoneLens-Setup-v0.12.7-Windows-x64.exe`

Gebruik voor integriteitscontrole uitsluitend `SHA256SUMS.txt` in de repository-root. Dat manifest wordt door de geverifieerde publish-workflow opnieuw opgebouwd en met `sha256sum -c` gecontroleerd, zodat er geen tweede handmatig checksumgetal kan verouderen.

De installer bevat de branded setupflow, progress/details, desktopkeuze, Windows-autostart, optionele WoW Retail-startmodus, repair en uninstall. Authenticode signing blijft een aparte externe releasepoort totdat een echte publisher certificate/private key beschikbaar is; distribueer de EXE niet als publiek vertrouwde Windows-release voordat die ondertekening en Windows-acceptatietest zijn afgerond.
