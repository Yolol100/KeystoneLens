# Uitgavechecklist 0.12.7

- exact één Companion-spelerslijst met instelbare KL-score-range (0–100);
- Score, Class en Role filters combineren deterministisch; gekoppelde Class/Role filters verdwijnen wanneer hun kolom verborgen is;
- kolommen KL, Role, Player, Class, Spec, Raider.IO, WCL;
- exacte 50/50-formule zonder meta/group/setup-score;
- RIO-component current-dungeon-only;
- WCL-average role-aware en current-dungeon-only;
- WCL-hot-path gebruikt gebatchte rankingmetrics en geen blokkerende raw-report/eventscan;
- queues met meer dan zes applicants worden volledig vervoerd; alleen definitieve kandidaten binnen de actieve filters worden gerenderd;
- delist/re-queue wist de oude queue-generatie en negeert vertraagde oude frames/results;
- `/kl stop|off`, `/kl on`, `/kl status`, `/kl sync`, `/kl help` functioneren;
- stop verstuurt terminal clear en leegt queued enrichment;
- auto-resume bij nieuwe listing en opnieuw openen applicantviewer;
- Python compile en regressietests groen;
- Bridge standalone en embedded bytegelijk;
- geen secrets, config, cache, screenshots, `.venv`, `__pycache__` of testfiles in ZIP;
- ZIP heeft exact één juiste top-level map;
- `unzip -t` groen;
- echte WoW/Windows/WCL runtime handmatig testen voor productie-GO.

## 0.12.7 hardening gates
- [x] Malformed/short APS1 transport is rejected without uncontrolled exceptions.
- [x] Non-finite score/WCL cache evidence cannot increase a score.
- [x] RIO/WCL caches enforce TTL/future-skew/size or evidence bounds.
- [x] Setup/uninstall unsafe-path guards pass source contract tests.
- [x] Dedicated per-user runtime is CPython 3.13.15 with the published python.org SHA-256.
- [x] APS1 v12/v13 record alignment tests pass.
- [x] Raider.IO/WCL parser contract tests pass.
- [x] Installer/Repair/Uninstall concurrency and exact-process contracts pass.
- [x] Source ZIP extracts and `pytest -q` passes from its root.
- [x] Master SHA-256 manifest validates after extraction.
- [x] Standalone Setup/CurseForge/source artifacts are byte-identical to the copies inside the master ZIP.
- [ ] All public Windows executables are Authenticode-signed and RFC 3161 timestamped before public distribution.
