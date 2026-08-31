# Live WoW acceptatie — 0.12.8

Handmatig testen op de exacte actuele WoW Retail-build + portable Windows Companion-build. Broncode/CI mag alleen `PASS-CI` claimen; deze matrix vereist echt clientbewijs voor `PASS-LIVE`.

Noteer per stap: **Geslaagd / Mislukt / Geblokkeerd**, plus datum/regio, WoW build/interface, Bridge SHA/version, Companion version, Raider.IO version, resolutie/UI-scale, dungeon/key/spec en relevante screenshots/logs.

## Group Finder en contextbinding

1. Start zonder listing: lege state, geen QR-captureloop en geen oude applicants.
2. Open eigen Mythic+ listing en laat meerdere rollen/specs aanmelden.
3. Controleer één lijst met `KL | Role | Player | Class | Spec | Raider.IO | WCL`.
4. Controleer dat KL tijdens enrichment `…` blijft en daarna hoogste→laagste sorteert.
5. Vergelijk Raider.IO rating/dungeonrun met dezelfde character/spec/dungeon-context.
6. Vergelijk WCL-detailmetrics met openbare data van dezelfde character/spec/dungeon.
7. Withdraw/invite: alleen actuele applicants blijven staan.
8. `/kl stop`: lijst wordt leeggemaakt, terminal clear wordt verwerkt en geen oude applicant komt terug.
9. Reopen applicantviewer: Bridge schakelt automatisch weer AAN wanneer recruitment opnieuw geldig is.
10. `/kl stop`, delist, nieuwe listing: nieuwe listing-generation; oude resultaten/frames mogen niet terugkeren.
11. `/kl on`, `/kl status`, `/kl sync`, `/kl help` testen.
12. Re-queue dezelfde speler in een andere dungeon/key: oude KL-regels blijven verborgen tot geldige nieuwe contextdata bestaat.
13. Wissel dezelfde applicant naar een andere spec: oude specscore blijft fail-closed verborgen.
14. Downgrade/rollback: door 0.12.8 geschreven v2-data mag nooit via de oude name-only cache zichtbaar worden.

## Midnight secret-value en lockdown-grenzen

15. Reproduceer Group Finder applicantvelden die tijdelijk onleesbaar/secret zijn. De Bridge moet `unknown`/lege veilige waarden gebruiken, nooit `tostring`/stringbewerkingen op secret data uitvoeren en geen Lua-error geven.
16. Start een capture terwijl de listing leesbaar is en laat daarna Chat Messaging Lockdown of een onleesbare LFG-state ontstaan. Er mag geen nieuwe recruitment-sessie uit alleen rosterdata ontstaan.
17. Start een Mythic+ challenge: capture moet vóór een volgende QR/screenshot stoppen/pauzeren; actieve dungeonstate mag nooit nieuwe applicant-screenshots produceren.
18. Ga een party-instance binnen zonder actieve challenge: dezelfde `dungeon-active` pausegrens geldt.
19. Vul de party tot vijf spelers: `party-full` moet capture pauzeren vóór een volgende dirty/poll-drain.
20. Verlaat/delist en maak daarna een nieuwe listing: auto-resume mag alleen op de nieuwe leesbare listing-signature plaatsvinden.

## Screenshot/QR-transport

21. Forceer een normale capture en controleer dat de QR pas na render-settle wordt vastgelegd en daarna verdwijnt.
22. Forceer `SCREENSHOT_SUCCEEDED` en `SCREENSHOT_FAILED`: in beide gevallen moet de state-machine terug naar idle en mag geen capture permanent geblokkeerd blijven.
23. Controleer dat `screenshotFormat` alleen tijdelijk naar PNG gaat en na succes/failure/disable naar de geldige eerdere waarde terugkeert.
24. Wijzig `screenshotFormat` handmatig terwijl KeystoneLens een lease heeft: restore mag een latere expliciete gebruikerswijziging niet overschrijven.
25. `/reload` of disable tijdens een onderbroken/legacy CVar-lease: de opgeslagen oude screenshotinstellingen moeten veilig herstellen.
26. Test 1920x1080, 2560x1440, 3840x2160 en ultrawide bij representatieve UI-scales/DPI. QR moet decodeerbaar blijven op de drie-fysieke-pixels-per-module baseline.
27. Open vendor/quest/mail/bank/map/character-achtige interactieframes tijdens recruitment: de tijdelijke QR mag UI niet onbruikbaar maken; na sluiten hervat transport alleen wanneer de recruitment-policy dit toestaat.
28. Companion minimaliseren/sluiten: Bridge blijft foutvrij, begrenst retries en herstelt wanneer Companion terugkomt.

## Addon-combinaties en databronnen

29. Test zonder Raider.IO: Bridge blijft bruikbaar en toont geen verzonnen RIO-data.
30. Test met actuele Raider.IO en controleer `hasRenderableData=false`, blocked/missing profile en ontbrekende dungeonhistorie fail-closed.
31. Test Bridge + KeystoneLensCompanionData + Raider.IO tegelijk na `/reload`; tooltipregels mogen niet dubbel of uit verkeerde activity/key/spec-context verschijnen.
32. Test schone SavedVariables, bestaande 0.12.x SavedVariables en beschadigde/herstelbare SavedVariables.
33. Test WCL auth/no-data/rate-limit en een tijdelijk netwerkfalen. Oude/in-flight Season-1/Season-2 resultaten mogen na een contextwissel niet als actuele evidence landen.
34. Laat Companion door de regionale Season-2/resetgrens heen draaien zonder restart en bevestig dat source/cache-context automatisch wisselt.

## Taint, fouten en duurtest

35. Test met Lua-errors en, waar praktisch, taint logging aan. Geen `ADDON_ACTION_BLOCKED`, protected-action of herhalende Lua-errors mogen uit KeystoneLensBridge komen.
36. Laat minimaal twintig applicant-update/capturecycli draaien met invite/withdraw/requeue. Controleer op begrensde memory-, texture-, timer-, cache- en screenshot-state groei.
37. Controleer dat de Bridge geen combatlog-, aura-, health/power-, cast-, target/focus-, raid-marker-, secure-action- of addon/chat-message-automatisering nodig heeft; recruitment/display + lokale screenshottransport blijft de volledige WoW-runtime-scope.

Pas `0.12.8` pas als publieke **Release** toe nadat alle toepasselijke livepunten slagen. Gebruik Beta zolang een live WoW-, clean-Windows-portable-, Season-2/WCL- of policygate openstaat.
