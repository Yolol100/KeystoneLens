#!/usr/bin/env python3
"""Bounded worst-case performance check for the generated WoW preload database."""
from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "companion" / "source" / "app"
sys.path.insert(0, str(APP_ROOT))

from keystonelens_companion.preload import MAX_RECORDS, render_lua_dataset  # noqa: E402

NOW = time.time()


def record(index: int):
    return {
        "full_name": f"Player{index}-Draenor",
        "spec_id": 62,
        "dungeon": "Altar of Fangs",
        "season": "midnight-s2",
        "metric": "DPS",
        "percentile": float(index % 101),
        "fetched_at": NOW,
    }


def main() -> int:
    started = time.perf_counter()
    lua = render_lua_dataset("EU", (record(i) for i in range(MAX_RECORDS)), now=NOW)
    render_seconds = time.perf_counter() - started
    size_bytes = len(lua.encode("utf-8"))

    assert size_bytes < 12 * 1024 * 1024, f"preload Lua too large: {size_bytes} bytes"
    assert render_seconds < 10.0, f"preload render too slow: {render_seconds:.3f}s"

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Data.lua"
        path.write_text(lua, encoding="utf-8")
        probe = r'''
local before = collectgarbage("count")
local started = os.clock()
dofile(os.getenv("KL_DATA"))
local loaded = os.clock() - started
collectgarbage("collect")
local after = collectgarbage("count")
local key = "player24999-draenor|62|altaroffangs"
local lookupStarted = os.clock()
local found = nil
for i = 1, 100000 do
    found = _G.KeystoneLensPreloadV4.entries[key]
end
local lookup = os.clock() - lookupStarted
if not found then error("worst-case preload lookup key missing") end
print(string.format("%.6f %.3f %.6f", loaded, after - before, lookup))
'''
        env = dict(os.environ)
        env["KL_DATA"] = str(path)
        run = subprocess.run(
            ["lua5.1", "-e", probe],
            check=True,
            text=True,
            capture_output=True,
            env=env,
        )
        loaded_s, memory_kib, lookup_s = map(float, run.stdout.strip().split())
        assert loaded_s < 10.0, f"Lua preload load too slow: {loaded_s:.3f}s"
        assert memory_kib < 120 * 1024, f"Lua preload memory too high: {memory_kib:.1f} KiB"
        assert lookup_s < 5.0, f"100k O(1) lookups too slow: {lookup_s:.3f}s"

    print(
        "KeystoneLens preload performance passed: "
        f"records={MAX_RECORDS} size={size_bytes}B render={render_seconds:.3f}s "
        f"lua_load={loaded_s:.3f}s lua_memory={memory_kib:.1f}KiB "
        f"100k_lookups={lookup_s:.3f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
