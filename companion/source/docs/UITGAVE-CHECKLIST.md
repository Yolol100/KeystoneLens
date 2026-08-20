# Uitgavechecklist 0.12.8

## Product/runtime

- [x] Exact één Companion-spelerslijst met instelbare KL-score-range (0–100).
- [x] Score, Class en Role filters combineren deterministisch.
- [x] Kolommen KL, Role, Player, Class, Spec, Raider.IO en WCL.
- [x] Exacte 50/50-formule zonder meta/group/setup-score.
- [x] Raider.IO-component is current-dungeon-only.
- [x] WCL-average is role-aware en current-dungeon-only.
- [x] WCL-hot-path gebruikt gebatchte rankingmetrics en geen blokkerende raw-report/eventscan.
- [x] Delist/re-queue wist de oude queue-generatie en negeert vertraagde oude frames/results.
- [x] `/kl stop|off`, `/kl on`, `/kl status`, `/kl sync`, `/kl help` functioneren volgens de source-contracttests.
- [x] Stop verstuurt terminal clear en leegt queued enrichment.
- [x] Tooltip cache is schema v2 en gebonden aan exacte activity, target key level en applicant specialization.
- [x] Schema v2 wist de legacy name-only global en gebruikt een aparte v2 global zodat rollback fail-closed is.
- [x] Malformed/short APS1 transport wordt gecontroleerd geweigerd.
- [x] Non-finite score/WCL-cachebewijs kan een score niet verhogen.
- [x] Raider.IO/WCL-caches begrenzen TTL/future-skew/omvang of bewijs.
- [x] Companion/installer source blijft observation-only: repository-audit blokkeert input-injectie, process-memory read/write, remote-process injection, global input hooks en bekende Python input-automationdependencies.
- [x] Raider.IO-client houdt een conservatieve request-pacing onder de publieke unauthenticated API-limiet, respecteert `Retry-After` bij 429 en bevat user-agent/attribution metadata.
- [x] Warcraft Logs OAuth-tokenexpiry, 429/`Retry-After`, GraphQL `rateLimitData` en bounded caches zijn fail-closed getest.

## Source/repository

- [x] `companion/source/VERSION` is de enige canonical release identity voor Companion, Bridge, data-addon en Windows metadata.
- [x] Repository-audit blokkeert tracked ZIP/EXE/build/release/cachebestanden en gangbare secrets/private-keybestanden.
- [x] Generated release-assets worden niet in `main` opgeslagen.
- [x] `.gitignore`, `.gitattributes` en `.editorconfig` leggen lokale output, binary/text en LF-regels vast.
- [x] GitHub Actions gebruikt immutable full-SHA action pins.
- [x] Iedere checkout zet `persist-credentials: false`; dit is centraal repositorybreed afgedwongen.
- [x] Alle GitHub-hosted runnerlabels zijn expliciet (`ubuntu-24.04` / `windows-2025`) zodat een toekomstige `-latest` migratie niet ongemerkt de releaseomgeving wijzigt.
- [x] Dependabot onderhoudt GitHub Actions-dependencies.
- [x] Dependabot monitort daarnaast de production Python requirements onder `companion/source/app`.
- [x] Een PR Dependency Review-workflow is aanwezig, gebruikt de full-SHA gepinde GitHub action en is blocking zodra GitHub Dependency Graph beschikbaar is; bij een uitgeschakelde graph rapporteert hij de adminblokkade expliciet terwijl de bestaande `pip-audit` gates blocking blijven.
- [x] `LICENSE-SCOPE.md` maakt duidelijk welke component expliciet gelicenseerd is zonder automatisch een repository-wide licentie te verlenen.
- [x] Python compile, volledige regressietests en native Windows-tests zijn releasegates.
- [x] Exacte production runtime dependency-versies worden in CI gebruikt en wekelijks met `pip-audit` gecontroleerd.
- [x] Kritieke adversarial suites voor lifecycle, secretmigratie, filesystem, netwerk, QR, release, Season-2-transitie en observation-only policy zijn verplichte repositorybestanden; verwijderen verlaagt de suite niet stil maar breekt de audit.
- [x] Dezelfde observation-only regressie werkt in de volledige checkout én in de opnieuw uitgepakte source release-ZIP.
- [x] Bridge-runtime wordt apart op Blizzard UI Add-On-policyhygiene gecontroleerd: geen in-game advertentie-, premium-, sponsorship- of donatiesolicitatiecode.

## Packaging/supply chain

- [x] Bridge standalone en embedded source zijn bytegelijk in de buildflow.
- [x] CurseForge ZIP heeft exact één top-level `KeystoneLensBridge/` map met `KeystoneLensBridge/KeystoneLensBridge.toc`.
- [x] CurseForge ZIP bevat geen EXE en behoudt license/third-party notices.
- [x] Bron-ZIP bevat geen secrets, config, cache, screenshots, `.venv`, `__pycache__`, build-output of Windows binaries.
- [x] ZIP-integriteit wordt met `unzip -t` gecontroleerd.
- [x] Releasebuild draait tweemaal en vereist byte-identieke deterministische outputs.
- [x] Release-assets krijgen een `SHA256SUMS.txt` manifest.
- [x] Getagde release-assets krijgen GitHub artifact attestations/provenance.
- [x] De bestaande CycloneDX 1.5 SBOM wordt bij de uiteindelijke source-ZIP en getekende Windows-installer als aparte SBOM-predicate geattesteerd.
- [x] De releaseworkflow verifieert voor beide runtime-artifacts zowel de standaard SLSA-provenance als predicate-type `https://cyclonedx.org/bom` vóór de draft release wordt aangemaakt.
- [x] Een tag moet exact `v<VERSION>` zijn; anders stopt de workflow.
- [x] De releaseworkflow muteert geen bestaande GitHub Release en commit geen generated binaries terug naar `main`.

## CurseForge public-release gate

- [ ] Project game-version/flavor is beperkt tot daadwerkelijk gevalideerde Retail-versies en blijft in sync met de Bridge TOC-interface.
- [ ] File channel blijft **Beta** zolang live WoW/Windows/policy acceptance openstaat; pas na die gates wordt **Release** gebruikt.
- [ ] Project dependency-relaties komen overeen met de werkelijke runtime: geen externe library als hard required declareren wanneer de code optioneel/fail-safe werkt.
- [ ] Project distribution toggle en project-level license scope zijn bewust door de owner gecontroleerd; GitHub-source/licentiescope wordt niet automatisch naar CurseForge vertaald.
- [ ] De geüploade CurseForge ZIP is exact de door CI gevalideerde `KeystoneLensBridge-0.12.8-CurseForge.zip`, niet lokaal opnieuw verpakt.

## Windows public-release gate

- [x] `sign-release.ps1` leest de canonical `VERSION`; geen hard-coded releaseversie.
- [x] Signing gebruikt SHA-256 Authenticode en RFC 3161/SHA-256 timestamping.
- [x] Payload binaries worden eerst getekend, daarna wordt Setup met de signed payload opnieuw gebouwd en zelf getekend.
- [x] `signtool verify` én `Get-AuthenticodeSignature` moeten alle vier publieke binaries als geldig bevestigen.
- [ ] Repository secrets `KEYSTONELENS_PFX_BASE64` en `KEYSTONELENS_PFX_PASSWORD` (of een later beheerde signing service) zijn veilig geconfigureerd voor de tag-release.
- [ ] Alle publieke Windows executables zijn met de echte publisher identity getekend en getimestamped.
- [ ] Clean-Windows install/repair/uninstall, taskbar/DPI en SmartScreen/AV acceptance zijn handmatig geslaagd.
- [ ] Unicode gebruikersnaam/pad, lang pad, read-only/locked bestand, reparse-point/symlink en onvoldoende schijfruimte zijn op een schone Windows-machine gecontroleerd zonder silent partial install.

## WoW / Season 2 public-release gate

- [ ] Live WoW tooltip-context/rollbackmatrix slaagt op de beoogde Retail client.
- [ ] Screenshot transport en Bridge + Companion Data co-load zijn live geslaagd.
- [ ] Eerste live Season 2 Warcraft Logs parse-matrix is gecontroleerd.
- [ ] CurseForge game-versionselectie is beperkt tot daadwerkelijk live gevalideerde Retail-versies.
- [ ] Owner/legal review heeft de observation-only externe Companion expliciet beoordeeld tegen Blizzard's actuele EULA/policygrens; source-audit alleen is geen Blizzard-autorisatie.
- [ ] Blizzard performance-policy is live gecontroleerd: geen excessive chat, onnodige disk-I/O of addon-caused FPS/frame-time degradatie tijdens listing-/screenshotbursts en herhaalde queuecycli.
- [ ] `0.12.8` wordt pas als **Release** gepubliceerd na live acceptance; gebruik **Beta** zolang die gate nog openstaat.

## Repository-admin gate

- [ ] GitHub Dependency Graph is ingeschakeld; de nieuwe Dependency Review-run bewees op 2026-08-20 expliciet dat deze repositoryfeature op dat moment uit stond.
- [ ] `main` is beschermd met PR-only merge, required checks voor Build/Stage, Windows Platform, CodeQL, dependency audit/review waar van toepassing, conversation resolution en zonder routine bypass.
- [ ] GitHub secret scanning/push protection en Dependabot/security alerts zijn waar beschikbaar bewust geactiveerd en gecontroleerd.

Een groene CI-run bewijst source/buildcorrectheid. De handmatige WoW-, Windows-, CurseForge-, repository-admin- en policy/legal-gates blijven afzonderlijk vereist voordat KeystoneLens als volledig publiek production-ready wordt verklaard.
