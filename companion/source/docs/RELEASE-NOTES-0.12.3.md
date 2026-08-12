# KeystoneLens 0.12.3 — Midnight Season 2 compatibility

- WoW TOCs now accept both Retail 12.0.7 (`120007`) and 12.1.0 (`120100`) during the patch transition.
- Midnight Season 2 registry promoted from PTR preload to `retail-12.1-season2`.
- Verified Season 2 pool: Altar of Fangs, Murder Row, Den of Nalorakk, The Blinding Vale, Voidscar Arena, Kings' Rest, Ruby Life Pools and Temple of Sethraliss.
- Warcraft Logs Season 2 continues to resolve dynamically through zone 56.
- Blizzard LFG name variants such as `Blinding Vale` / `The Blinding Vale` and apostrophe variants of `Kings' Rest` are canonicalized before WCL/Raider.IO enrichment.
- Legacy hard-coded LFG activity IDs remain a fallback only; current-season dungeon identity is taken from WoW's live `C_LFGList.GetActivityInfoTable`.

Season timing note: the Curse of Ula'tek 12.1.0 content update lands before the Mythic+ Season 2 weekly reset. This build is prepared for the transition without falsely depending on Season 2 already being active.
