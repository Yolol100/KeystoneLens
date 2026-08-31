# KeystoneLens Companion

De actuele releaseversie staat in `companion/source/VERSION`. Die ene versiebron stuurt Companion-, Bridge-/data-addonmetadata en versiegebonden artifactnamen.

De ondersteunde Windows Companion is portable: pak `KeystoneLens-Portable-<VERSION>-Windows-x64.zip` volledig uit en start `START-COMPANION.cmd`. Er is geen KeystoneLens Setup, Windows-installatie, administratorrecht of apart geinstalleerde Python nodig.

De Windows runtimebron staat centraal in `companion/source/runtime/windows/python-runtime.json`; het exacte packagegraph staat hash-locked in `companion/source/runtime/windows/requirements-runtime.lock`.

De reproduceerbare bronbundel `KeystoneLens-Source-<VERSION>.zip` en de portable Windows ZIP zijn gegenereerde GitHub artifacts en worden niet in `main` opgeslagen. De releaseflow controleert deterministische core packaging en verifieert de portable ZIP na opnieuw uitpakken op Windows.
