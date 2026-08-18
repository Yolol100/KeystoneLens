# Live WoW acceptatie — 0.12.8

Handmatig testen op actuele WoW Retail + Windows:

1. Start zonder listing: lege state.
2. Open eigen Mythic+ listing en laat meerdere rollen/specs aanmelden.
3. Controleer één lijst met `KL | Role | Player | Class | Spec | Raider.IO | WCL`.
4. Controleer dat KL tijdens enrichment `…` blijft en daarna hoogste→laagste sorteert.
5. Vergelijk Raider.IO rating/dungeonrun met de characterpagina.
6. Vergelijk WCL-detailmetrics met openbare data van dezelfde character/spec/dungeon.
7. Withdraw/invite: alleen actuele applicants blijven staan.
8. `/kl stop`: lijst wordt leeggemaakt en geen oude applicant komt terug.
9. Reopen applicantviewer: Bridge schakelt automatisch weer AAN.
10. `/kl stop`, delist, nieuwe listing: Bridge schakelt automatisch weer AAN.
11. `/kl on`, `/kl status`, `/kl sync`, `/kl help` testen.
12. WCL auth/no-data/rate-limit testen.
13. Tooltipcache na `/reload` testen voor dezelfde dungeon/key/spec.
14. Re-queue dezelfde speler in een andere dungeon/key en controleer dat oude KL-regels niet worden getoond vóór een geldige nieuwe sync/reload.
15. Wissel dezelfde applicant naar een andere spec en controleer dezelfde fail-closed contextbinding.
16. Test downgrade/rollback: met door 0.12.8 geschreven v2-data mag een oude name-only Bridge geen KL-score tonen.
17. Companion minimaliseren/sluiten testen.

Noteer per stap: Geslaagd / Mislukt / Geblokkeerd + WoW build, dungeon/key/spec en evidence.
