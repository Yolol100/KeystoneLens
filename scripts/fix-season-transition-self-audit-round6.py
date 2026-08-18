from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "companion/source/app/keystonelens_companion/__main__.py"
text = path.read_text(encoding="utf-8")
old = '''    def _poll(self) -> None:\n        try:\n            now = time.monotonic()\n            if now >= self._next_season_transition_check:\n                self._next_season_transition_check = now + 30.0\n                self.engine.refresh_season_transition()\n            while True:\n'''
new = '''    def _poll(self) -> None:\n        try:\n            now = time.monotonic()\n            next_check = getattr(self, "_next_season_transition_check", 0.0)\n            if now >= next_check:\n                self._next_season_transition_check = now + 30.0\n                engine = getattr(self, "engine", None)\n                if engine is not None:\n                    engine.refresh_season_transition()\n            while True:\n'''
if text.count(old) != 1:
    raise SystemExit(f"poll marker changed: {text.count(old)} matches")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Defensive poll initialization applied")
