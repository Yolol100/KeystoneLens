#!/usr/bin/env python3
"""Source-level contract checks for the intentionally small KeystoneLens architecture."""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "companion" / "source"
APP = SOURCE / "app" / "keystonelens_companion"
BRIDGE = ROOT / "addon" / "KeystoneLensBridge"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


errors: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


version = read(SOURCE / "VERSION").strip()
require(bool(re.fullmatch(r"\d+\.\d+\.\d+", version)), "VERSION is not semantic x.y.z")
version_sources = {
    "python": re.search(r'__version__\s*=\s*"([^"]+)"', read(APP / "__init__.py")),
    "bridge": re.search(r"## Version:\s*([^\n]+)", read(BRIDGE / "KeystoneLensBridge.toc")),
    "data": re.search(
        r"## Version:\s*([^\n]+)",
        read(SOURCE / "data-addon" / "KeystoneLensCompanionData" / "KeystoneLensCompanionData.toc"),
    ),
}
for label, match in version_sources.items():
    require(match is not None and match.group(1).strip() == version, f"{label} version does not match VERSION")

removed_modules = [
    "filters.py",
    "rio.py",
    "scoring.py",
    "ui.py",
    "ui_layout_patch.py",
    "ui_recruitment_patch.py",
    "ui_recruitment_persistence_patch.py",
]
for name in removed_modules:
    require(not (APP / name).exists(), f"obsolete module returned: {name}")

app_text = "\n".join(read(path) for path in sorted(APP.glob("*.py")))
for token in ("from .rio", "from .scoring", "from .filters", "from .ui"):
    require(token not in app_text, f"obsolete import returned: {token}")

wcl = read(APP / "wcl.py")
require('role_metric = "hps" if spec_id in HEALER_SPECS else "dps"' in wcl, "role metric selection changed")
require("metric:{role_metric}" in wcl, "role metric is not used in the WCL query")
require("metric:playerscore" not in wcl, "playerscore query returned")
require("fetch_batch_previous_season" not in wcl, "previous-season scoring path returned")
require(
    wcl.find("live_id = mapping.get") >= 0
    and wcl.find("known = DUNGEONS.get") >= 0
    and wcl.find("live_id = mapping.get") < wcl.find("known = DUNGEONS.get"),
    "live WCL zone catalog must be authoritative before hardcoded fallback IDs",
)

constants = read(APP / "constants.py")
for dungeon_id in ("12993", "12813", "12825", "12859", "12923"):
    require(dungeon_id in constants, f"missing live Season 2 fallback ID {dungeon_id}")
for stale_id in ("62993", "62813", "62825", "62859", "62923"):
    require(stale_id not in constants, f"stale PTR-like fallback ID returned: {stale_id}")

engine = read(APP / "engine.py")
main_app = read(APP / "__main__.py")
watcher = read(APP / "watcher.py")
for token, label in (
    ("def _clear_wcl_queue_locked", "WCL queue invalidation"),
    ("self._listing_closed = False", "listing closed generation guard"),
    ("self._listing_closed and snapshot.listing is not None", "late same-generation snapshot rejection"),
    ("Group Finder data temporarily unavailable • keeping last valid list", "non-authoritative LFG preservation"),
    ("canonical_dungeon_name", "dungeon canonicalization"),
):
    require(token in engine, f"missing lifecycle protection: {label}")

for token, label in (
    ('self.root.protocol("WM_DELETE_WINDOW", self.quit)', "window X shutdown route"),
    ('text="Afsluiten", command=self.quit', "Afsluiten button shutdown route"),
    ("def _cleanup_after_ui", "central shutdown cleanup"),
    ("def _bounded_cleanup", "bounded shutdown cleanup"),
    ("def _arm_force_exit_watchdog", "shutdown watchdog"),
    ("self.root.destroy()", "immediate UI destruction"),
    ("finally:\n            self._cleanup_after_ui()", "cleanup after Tk mainloop"),
):
    require(token in main_app, f"missing shutdown protection: {label}")
require("def request_stop" in watcher, "watcher must support immediate shutdown signaling")
require("def request_stop" in engine, "engine must support immediate shutdown signaling")
require((SOURCE / "scripts" / "test_shutdown_contract.py").is_file(), "shutdown regression test is missing")
require((SOURCE / "scripts" / "test_window_visibility_contract.py").is_file(), "window restore regression test is missing")
require("class SettingsDialog" not in main_app, "modal SettingsDialog must not return")
require("grab_set()" not in main_app, "modal Tk grab must not return")
require('self.root.bind("<Map>", self._on_root_mapped' in main_app, "taskbar restore Map binding is missing")
require("def _show_main_window" in main_app, "main-window restore helper is missing")

tooltip = read(BRIDGE / "Core" / "Tooltip.lua")
bridge_toc = read(BRIDGE / "KeystoneLensBridge.toc")
for token, label in (
    ("REQUIRED_CACHE_VERSION = 3", "cache v3"),
    ("local specID = results[17]", "current applicant spec extraction"),
    ("tonumber(entry.activityID) ~= activityID", "activity guard"),
    ("tonumber(entry.specID) ~= specID", "spec guard"),
    ('metric ~= "DPS" and metric ~= "HPS"', "DPS/HPS metric guard"),
    ("RegisterRaiderIOScoreHook", "Raider.IO score-line integration"),
    ('plain == "Raider.IO M+ Score" or plain == "Current M+ Score"', "Raider.IO current-score detection"),
    ("AppendCurrentTooltipContext", "shared LFG/unit tooltip context"),
    ("TooltipDataProcessor.AddTooltipPostCall", "normal player tooltip integration"),
    ("TooltipUtil.GetDisplayedUnit", "taint-safe displayed-unit lookup"),
    ("ScrollBoxUtil.OnViewFramesChanged", "current LFG recycled-frame hook"),
):
    require(token in tooltip, f"tooltip contract changed: {label}")
require("RaiderIO" in bridge_toc, "RaiderIO must remain an OptionalDep for deterministic tooltip order")
require((SOURCE / "scripts" / "test_tooltip_contract.lua").is_file(), "Raider.IO tooltip regression suite is missing")
for unwanted in ("KL Score", "KL evidence", "KL bronnen", "rioComponent", "wclRuns"):
    require(unwanted not in tooltip, f"tooltip is no longer minimal: {unwanted}")

for rel in (
    "portable/build-portable.ps1",
    "portable/portable_launcher.py",
    "portable/START-COMPANION.cmd",
    "runtime/windows-x64.json",
    "runtime/requirements-runtime.lock",
):
    require((SOURCE / rel).is_file(), f"required portable component missing: {rel}")

launcher = read(SOURCE / "portable" / "portable_launcher.py")
start_cmd = read(SOURCE / "portable" / "START-COMPANION.cmd")
builder = read(SOURCE / "portable" / "build-portable.ps1")
require('os.environ["TCL_LIBRARY"]' in launcher, "portable launcher must bind bundled Tcl")
require('os.environ["TK_LIBRARY"]' in launcher, "portable launcher must bind bundled Tk")
require("def verify_ui_runtime" in launcher, "portable launcher must perform a real Tk smoke")
require("--verify-ui" in start_cmd, "START-COMPANION must run the GUI smoke before pythonw")
require("--verify-ui" in builder, "portable build must verify the extracted GUI runtime")
require("def restore_existing_window" in launcher, "portable launcher must restore an existing window")
require("if restore_existing_window():" in launcher, "second start must foreground the existing Companion")

requirements = read(SOURCE / "runtime" / "requirements-runtime.txt").casefold()
for package in ("requests", "pillow", "zxing-cpp"):
    require(package in requirements, f"required portable dependency missing: {package}")

if errors:
    print("KeystoneLens minimal-architecture verification FAILED:")
    for error in errors:
        print(f" - {error}")
    raise SystemExit(1)

print(f"KeystoneLens minimal-architecture verification passed for {version}.")
