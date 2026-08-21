# Comparable Add-on Audit — 2026-08-21

This checklist compares KeystoneLens with established Group Finder / player-information addons. It records product patterns and adoption decisions only; no third-party code is copied.

## Compared projects

1. **Raider.IO** — context-specific Mythic+ evidence, role evidence, exact-dungeon history, main/alt context, frequent data refresh and explicit rejection of outdated profile data.
2. **Premade Applicants Filter** — hard applicant filters separate from ranking, including role/class/member composition and external-score evidence.
3. **Premade Groups Filter** — persistent standard filters, advanced filtering/sorting and compact composition signals alongside Blizzard's LFG UI.
4. **Pinta Group Finder** — persistent filter panels, role/rating filters, simple reset/debug recovery and English fallback localization.
5. **LFM+** — active-role filtering, score/class filters, compact LFG enhancements and persistent user preferences.
6. **Premade Regions** — additional regional context; reviewed but not copied because KeystoneLens' region field is not a reliable datacenter/latency classification.

## Adoption checklist

- [x] Keep the displayed KL Score exactly 50% Raider.IO + 50% Warcraft Logs; do not silently add unrelated signals.
- [x] Keep exact-dungeon and queued-role Raider.IO evidence separate and explainable.
- [x] Keep score/class/role filters separate from the score calculation.
- [x] Keep stale tooltip data fail-closed: generated cache entries remain bound to exact listing, key and specialization and expire after the configured maximum age.
- [x] Expose the existing score confidence (`high` / `medium` / `low`) and data age in the in-game tooltip cache so a leader can see evidence strength rather than interpreting one number without context.
- [x] Add native localized **Dungeons & Raids** metadata to the Bridge and group the generated Companion Data addon under the Bridge in the modern WoW AddOns list.
- [x] Preserve the observation-only Bridge boundary: no automated applicant acceptance/decline, input injection, process memory access or hidden LFG actions.
- [ ] Do **not** add region/datacenter filtering until the source can distinguish actual datacenter/language information from a broad Raider.IO region.
- [ ] Do **not** add one-click applicant actions. KeystoneLens remains an evidence/decision-support tool, not an automated Group Finder operator.
- [ ] Do **not** change score weights based on competitor behavior without a separate evidence/calibration study.

## Result

The comparison supports better evidence transparency rather than a more complicated score. Confidence and freshness become visible to the user while the existing deterministic scoring, stale-data rejection and observation-only boundaries remain unchanged.
