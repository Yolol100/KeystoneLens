# KeystoneLens Companion

De actuele releaseversie staat in `companion/source/VERSION`. Die ene versiebron stuurt Companionmetadata, Bridge-/data-addonmetadata, Windows PE-metadata en versiegebonden artifactnamen.

## Windows-uitgaven

KeystoneLens heeft twee Windows-routes die dezelfde Companion-code en dezelfde vastgezette runtime-dependencies gebruiken:

- **Installer:** `KeystoneLens-Setup-v<VERSION>-Windows-x64.exe`. Deze route ondersteunt installatie, repair/uninstall en starten handmatig, met Windows of wanneer World of Warcraft Retail start.
- **Portable:** `KeystoneLens-Portable-<VERSION>-Windows-x64.zip`. Deze route vereist geen KeystoneLens-installatie, administratorrechten of apart geïnstalleerde Python; pak de volledige ZIP uit en start `START-COMPANION.cmd`.

De portable build haalt de canonieke Python-runtime-URL en SHA-256 rechtstreeks uit de installerbron, installeert dezelfde hash-locked runtimepackages en verifieert zowel de staged map als de opnieuw uitgepakte ZIP. Third-party notices worden in de portable ZIP opgenomen.

De reproduceerbare bronbundel `KeystoneLens-Source-<VERSION>.zip` is een gegenereerd GitHub Release-artifact en wordt niet in `main` opgeslagen. De bronbundel bevat ook de portable buildtooling, zodat de huidige release-engineering compleet reproduceerbaar blijft.

Voor een publieke Windows-release wordt de installer via de tag-releaseflow Authenticode-ondertekend en RFC 3161-getimestamped; ontbrekende signing identity laat die release bewust falen. De portable ZIP en de overige release-assets worden in dezelfde tagflow geverifieerd, gehasht en van GitHub attestations voorzien.

Gebruik `SHA256SUMS.txt` naast de release-assets voor integriteitscontrole. Een public release vereist daarna nog de gedocumenteerde clean-Windows-acceptatie voor zowel de geïnstalleerde als portable route.
