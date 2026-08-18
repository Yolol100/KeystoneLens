from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "companion/source/app/keystonelens_companion/engine.py",
    "from .registries import MIDNIGHT_SEASON_1, canonical_dungeon_name, DUNGEON_TO_SEASON, use_previous_wcl_for_dungeon, wcl_source_season_for_dungeon\n",
    "from .registries import MIDNIGHT_SEASON_1, canonical_dungeon_name, DUNGEON_TO_SEASON, season2_transition_phase, use_previous_wcl_for_dungeon, wcl_source_season_for_dungeon\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/engine.py",
    '''        self._default_realm = ""\n        self._region = "EU"\n        self._stop = threading.Event()\n''',
    '''        self._default_realm = ""\n        self._region = "EU"\n        self._season_phase_by_region: dict[str, str] = {}\n        self._stop = threading.Event()\n''',
)
replace_once(
    "companion/source/app/keystonelens_companion/engine.py",
    '''        self._pending.clear()\n        self._rio_pending.clear()\n\n    def set_wcl(self, client: WCLClient | None) -> None:\n''',
    '''        self._pending.clear()\n        self._rio_pending.clear()\n\n    def refresh_season_transition(self) -> bool:\n        """Refresh a long-running session when a regional season phase changes.\n\n        This is intentionally cheap and safe to call periodically. A phase change\n        invalidates both online sources, bumps the view revision so in-flight old\n        requests cannot land, and requeues enrichment without needing a new WoW\n        screenshot or companion restart.\n        """\n        with self._lock:\n            regions = {view.region for view in self._views.values() if view.region}\n            changed: set[str] = set()\n            for region in regions:\n                phase = season2_transition_phase(region=region)\n                previous = self._season_phase_by_region.get(region)\n                self._season_phase_by_region[region] = phase\n                if previous is not None and previous != phase:\n                    changed.add(region)\n            if not changed:\n                return False\n\n            self._clear_enrichment_queues_locked()\n            self._revision += 1\n            revision = self._revision\n            for view in self._views.values():\n                if view.region not in changed:\n                    continue\n                view.revision = revision\n                view.wcl = None\n                view.rio = None\n                view.wcl_status = "queued" if self.wcl else "disabled"\n                view.rio_status = "queued" if self.rio else "disabled"\n                view.score = calculate_score(\n                    view.applicant, view.snapshot_listing, None, None,\n                )\n                view.updated_at = time.time()\n\n            self._queue_missing_rio_locked()\n            self._queue_missing_wcl_locked()\n            self._emit_locked()\n            return True\n\n    def set_wcl(self, client: WCLClient | None) -> None:\n''',
)
replace_once(
    "companion/source/app/keystonelens_companion/engine.py",
    '''            self._revision += 1\n            revision = self._revision\n            old_listing = self._listing\n''',
    '''            current_phase = season2_transition_phase(region=region)\n            previous_phase = self._season_phase_by_region.get(region)\n            phase_changed = previous_phase is not None and previous_phase != current_phase\n            self._season_phase_by_region[region] = current_phase\n\n            self._revision += 1\n            revision = self._revision\n            old_listing = self._listing\n''',
)
replace_once(
    "companion/source/app/keystonelens_companion/engine.py",
    '''            if (_listing_context(old_listing), old_region) != (new_enrichment_context, region):\n''',
    '''            if phase_changed or (_listing_context(old_listing), old_region) != (new_enrichment_context, region):\n''',
)
replace_once(
    "companion/source/app/keystonelens_companion/engine.py",
    '''                same_wcl_context = bool(same_character_context and _result_matches_listing(old.wcl, effective_listing, region))\n                same_rio_context = bool(same_character_context and _result_matches_listing(old.rio, effective_listing, region))\n''',
    '''                same_wcl_context = bool(\n                    same_character_context\n                    and not phase_changed\n                    and _result_matches_listing(old.wcl, effective_listing, region)\n                )\n                same_rio_context = bool(\n                    same_character_context\n                    and not phase_changed\n                    and _result_matches_listing(old.rio, effective_listing, region)\n                )\n''',
)
replace_once(
    "companion/source/app/keystonelens_companion/engine.py",
    "                    revision=old.revision if same_character_context else revision,\n",
    "                    revision=old.revision if same_character_context and not phase_changed else revision,\n",
)

# Poll the cheap phase check at a bounded cadence so a companion left open over
# weekly reset changes source policy without waiting for a new screenshot.
replace_once(
    "companion/source/app/keystonelens_companion/__main__.py",
    '''        self._preferences_save_job: str | None = None\n        self.engine = ApplicantEngine(None, lambda state: self.q.put(("state", state)), rio=self.rio)\n''',
    '''        self._preferences_save_job: str | None = None\n        self._next_season_transition_check = 0.0\n        self.engine = ApplicantEngine(None, lambda state: self.q.put(("state", state)), rio=self.rio)\n''',
)
replace_once(
    "companion/source/app/keystonelens_companion/__main__.py",
    '''    def _poll(self) -> None:\n        try:\n            while True:\n''',
    '''    def _poll(self) -> None:\n        try:\n            now = time.monotonic()\n            if now >= self._next_season_transition_check:\n                self._next_season_transition_check = now + 30.0\n                self.engine.refresh_season_transition()\n            while True:\n''',
)

# Direct long-running-session regression without network clients.
test_path = ROOT / "companion/source/app/tests/test_season_transition.py"
text = test_path.read_text(encoding="utf-8")
marker = "\n\ndef test_real_season1_listing_is_not_mistaken_for_s2_carryover():\n"
if text.count(marker) != 1:
    raise SystemExit("transition refresh test insertion marker changed")
extra = r'''


def test_long_running_engine_invalidates_online_evidence_on_phase_change_without_snapshot():
    states = []
    app_engine = engine.ApplicantEngine(None, states.append, rio=None)
    try:
        listing = Listing(key_level=10, dungeon_name="Altar of Fangs")
        applicant = _applicant()
        old_wcl = WCLResult(
            "Applicant", "Realm", "Altar of Fangs", 71,
            WCLBracket(0, 80, 80, 1, 80), time.time(), target_key=10,
            source_season="midnight-s1",
        )
        old_rio = rio.RIOResult(
            "Applicant", "realm", "EU", "Altar of Fangs", 10,
            score=0, previous_score=2784, fetched_at=time.time(),
        )
        view = ApplicantView(
            applicant=applicant,
            snapshot_listing=listing,
            region="EU",
            wcl=old_wcl,
            wcl_status="ready",
            rio=old_rio,
            rio_status="ready",
            revision=4,
        )
        view.score = engine.calculate_score(applicant, listing, old_wcl, old_rio)
        with app_engine._lock:
            app_engine._views = {applicant.identity: view}
            app_engine._listing = listing
            app_engine._revision = 4
            app_engine._season_phase_by_region["EU"] = "week1"

        with patch.object(engine, "season2_transition_phase", return_value="current"):
            assert app_engine.refresh_season_transition() is True

        assert view.revision == 5
        assert view.wcl is None
        assert view.rio is None
        assert view.wcl_status == "disabled"
        assert view.rio_status == "disabled"
        assert states and states[-1].revision == 5
    finally:
        app_engine.stop()


def test_long_running_engine_phase_check_is_noop_when_phase_is_unchanged():
    app_engine = engine.ApplicantEngine(None, lambda _state: None, rio=None)
    try:
        listing = Listing(key_level=10, dungeon_name="Altar of Fangs")
        applicant = _applicant()
        view = ApplicantView(applicant=applicant, snapshot_listing=listing, region="EU", revision=3)
        with app_engine._lock:
            app_engine._views = {applicant.identity: view}
            app_engine._season_phase_by_region["EU"] = "week1"
        with patch.object(engine, "season2_transition_phase", return_value="week1"):
            assert app_engine.refresh_season_transition() is False
        assert view.revision == 3
    finally:
        app_engine.stop()
'''
test_path.write_text(text.replace(marker, extra + marker, 1), encoding="utf-8")

print("Long-running transition refresh hardening applied")
