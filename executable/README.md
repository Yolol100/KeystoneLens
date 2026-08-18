# KeystoneLens Windows Installer

De actuele releaseversie staat in `companion/source/VERSION`. De releaseworkflow controleert die versie tegen Companion-, Bridge-, data-addon- en Windows-buildmetadata voordat release-assets worden aangemaakt.

Publieke bestandsnaam: `KeystoneLens-Setup-v<VERSION>-Windows-x64.exe`.

De installer wordt niet in `main` bewaard. Een getagde release bouwt hem vanaf de exacte tag, ondertekent de geïnstalleerde launcher/uninstaller/WoW watcher vóór het opnieuw embedden van de payload, ondertekent daarna Setup zelf en controleert alle Authenticode-signatures. Ontbrekende signing-secrets blokkeren de tag-release in plaats van een unsigned EXE te publiceren.

Gebruik voor integriteitscontrole de `SHA256SUMS.txt` die als GitHub Release-asset naast de uiteindelijke binaries wordt gepubliceerd. GitHub artifact attestations leggen daarnaast de build provenance van de release-assets vast.

Een public release vereist na signing nog een clean-Windows installatie/repair/uninstall- en SmartScreen/AV-acceptatietest.
