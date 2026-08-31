# Live WoW acceptatie — 0.12.8

Handmatig testen op de exacte actuele WoW Retail-build + de door CI gevalideerde portable Windows Companion. Broncode/CI mag alleen `PASS-CI` claimen; deze matrix vereist echt clientbewijs voor `PASS-LIVE`.

Noteer per stap: **Geslaagd / Mislukt / Geblokkeerd**, plus datum/regio, WoW build/interface, Bridge SHA/version, Companion version, Raider.IO version, resolutie/UI-scale, dungeon/key/spec en relevante screenshots/logs.

## Portable Windows startgrens

1. Pak de volledige `KeystoneLens-Portable-0.12.8-Windows-x64.zip` uit op een schone Windows x64 useromgeving.
2. Start alleen `START-COMPANION.cmd`; controleer dat geen install-, admin-, registry- of Start-menuactie nodig is.
3. Herhaal vanaf een pad met spaties en een representatieve Unicode-gebruikersmap.
4. Start een tweede keer terwijl de eerste instance draait; er mag geen tweede Companioninstance ontstaan.
5. Sluit de Companion en verwijder/verplaats de uitgepakte map; er mag geen productinstallatiepad achterblijven. Lokale config onder `%LOCALAPPDATA%\KeystoneLens` is aparte user data.

## Group Finder en contextbinding

6. Start zonder listing: lege state, geen QR-captureloop en geen oude applicants.
7. Open eigen Mythic+ listing en laat meerdere rollen/specs aanmelden.
8. Controleer `KL | Role | Player | Class | Spec | Raider.IO | WCL` en definitieve score-sortering.
9. Withdraw/invite: alleen actuele applicants blijven staan.
10. `/kl stop`: lijst leeg, terminal clear verwerkt en geen oude applicant komt terug.
11. Reopen applicantviewer: auto-resume alleen wanneer recruitment opnieuw geldig is.
12. Delist/nieuwe listing: generation wisselt en oude resultaten/frames blijven weg.
13. Wijzig dungeon/key/spec: oude tooltipregels blijven verborgen tot nieuwe geldige contextdata bestaat.
14. Rollback: door 0.12.8 geschreven v2-data mag nooit via de oude name-only cache zichtbaar worden.

## Secret-value / lifecycle / screenshot

15. Tijdelijk secret/onleesbare Group Finder velden moeten fail-closed blijven zonder Lua-error.
16. Chat Messaging Lockdown of onleesbare LFG-state mag geen recruitment-sessie uit alleen rosterdata creëren.
17. Actieve Mythic+ of party-instance pauzeert capture vóór een nieuwe screenshot.
18. Party met vijf spelers pauzeert capture vóór de volgende scheduler drain.
19. `SCREENSHOT_SUCCEEDED` en `SCREENSHOT_FAILED` herstellen de capture-state en tijdelijke screenshot-CVars.
20. Test 1920x1080, 2560x1440, 3840x2160 en ultrawide bij representatieve UI-scales/DPI.
21. Companion minimaliseren/sluiten: Bridge blijft foutvrij en hervat correct wanneer de Companion later terugkomt.

## Databronnen / soak

22. Test zonder Raider.IO, met actuele Raider.IO en met ontbrekende profiel/dungeondata.
23. Test Bridge + KeystoneLensCompanionData + Raider.IO tegelijk na `/reload`; geen dubbele/verkeerde contexttooltipregels.
24. Test WCL auth/no-data/rate-limit/netwerkfalen met echte releasecredentials.
25. Laat Companion door een regionale Season/resetgrens draaien zonder restart en controleer context/cachewisseling.
26. Laat minimaal twintig applicant-update/capturecycli draaien; memory/texture/timer/cache/screenshot-state moet begrensd blijven.
27. Controleer dat de Bridge observation/display + lokaal screenshottransport blijft en geen protected-action/chat/input-automation nodig heeft.

Publiceer 0.12.8 pas als **Release** nadat de toepasselijke live WoW-, clean-Windows-, CurseForge- en policygates slagen; gebruik Beta zolang die nog openstaan.
