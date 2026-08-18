# KeystoneLens Companion

De actuele releaseversie staat in `companion/source/VERSION`. Die ene versiebron stuurt Companionmetadata, Bridge-/data-addonmetadata, Windows PE-metadata en versiegebonden artifactnamen.

De Companion-installer biedt installatie, repair/uninstall en startmodi voor handmatig starten, Windows-start en World of Warcraft Retail-start.

De reproduceerbare bronbundel `KeystoneLens-Source-<VERSION>.zip` is een gegenereerd GitHub Release-artifact en wordt niet meer in `main` opgeslagen. De releaseworkflow bouwt de bronbundel tweemaal en accepteert hem alleen als de outputs byte-identiek zijn.

Voor een publieke Windows-release moet de uiteindelijke installer via de tag-releaseflow Authenticode-ondertekend en RFC 3161-getimestamped zijn; een ontbrekende signing identity laat de release bewust falen.
