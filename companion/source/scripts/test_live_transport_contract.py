#!/usr/bin/env python3
"""Protocol and engine contract for APS1 v14 live hover delivery."""
from __future__ import annotations

import struct
import sys
import types
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "companion" / "source" / "app"
sys.path.insert(0, str(APP_ROOT))

requests_stub = types.ModuleType("requests")
requests_stub.RequestException = RuntimeError
requests_stub.Session = object
sys.modules.setdefault("requests", requests_stub)

from keystonelens_companion.aps1 import APS1Error, parse_snapshot  # noqa: E402
from keystonelens_companion.engine import ApplicantEngine  # noqa: E402
from keystonelens_companion.models import (  # noqa: E402
    Applicant,
    LiveHover,
    Listing,
    Snapshot,
)


def text(value: str) -> bytes:
    raw = value.encode("utf-8")
    assert len(raw) <= 255
    return bytes([len(raw)]) + raw


def wrap(version: int, body: bytes, *, listing_generation: int = 7) -> bytes:
    header = b"APS1" + bytes([version]) + b"\x00\x00" + b"\x00" + bytes([listing_generation])
    total = len(header) + len(body) + 4
    header = header[:5] + struct.pack(">H", total) + header[7:]
    without_crc = header + body
    return without_crc + struct.pack(">I", zlib.crc32(without_crc) & 0xFFFFFFFF)


def v14_payload() -> bytes:
    body = bytearray()
    body += b"\x00"  # no listing
    body += b"\x00"  # no version info
    body += b"\x00"  # no leader key
    body += struct.pack(">H", 0)  # applicants
    body += struct.pack(">H", 0)  # roster
    body += b"\x01"  # live hover present
    body += struct.pack(">H", 9)
    body += struct.pack(">I", 42)
    body += bytes([1])
    body += struct.pack(">H", 62)
    body += struct.pack(">I", 777)
    body += text("Alice-Draenor")
    for value in (40000, 30000, 10000, 1200, 25000, 20000, 9000, 1800):
        body += struct.pack(">H", value)
    return wrap(14, bytes(body))


def test_v14_hover_round_trip() -> None:
    snapshot = parse_snapshot(v14_payload())
    hover = snapshot.live_hover
    assert snapshot.listing_generation == 7
    assert hover is not None
    assert hover.generation == 9
    assert hover.applicant_id == 42
    assert hover.member_idx == 1
    assert hover.name == "Alice-Draenor"
    assert hover.spec_id == 62
    assert hover.activity_id == 777
    assert (hover.value_x, hover.value_y, hover.value_w, hover.value_h) == (40000, 30000, 10000, 1200)
    assert (hover.owner_x, hover.owner_y, hover.owner_w, hover.owner_h) == (25000, 20000, 9000, 1800)


def test_v13_stays_backward_compatible() -> None:
    body = b"\x00\x00\x00" + struct.pack(">H", 0) + struct.pack(">H", 0)
    snapshot = parse_snapshot(wrap(13, body))
    assert snapshot.live_hover is None


def test_unknown_version_fails_closed() -> None:
    try:
        parse_snapshot(wrap(15, b"\x00"))
    except APS1Error:
        return
    raise AssertionError("unsupported APS1 v15 was accepted")


def applicant() -> Applicant:
    return Applicant(
        applicant_id=42,
        member_idx=1,
        class_id=8,
        spec_id=62,
        ilvl=700,
        rio_score=0,
        rio_main_score=0,
        role_byte=3,
        name="Alice-Draenor",
    )


def listing() -> Listing:
    return Listing(activity_id=777, key_level=12, dungeon_name="Test Dungeon")


def hover(generation: int) -> LiveHover:
    return LiveHover(
        generation=generation,
        applicant_id=42,
        member_idx=1,
        name="Alice-Draenor",
        spec_id=62,
        activity_id=777,
        value_x=40000,
        value_y=30000,
        value_w=10000,
        value_h=1200,
        owner_x=25000,
        owner_y=20000,
        owner_w=9000,
        owner_h=1800,
    )


def test_engine_keeps_newest_matching_hover() -> None:
    states = []
    engine = ApplicantEngine(None, states.append)
    try:
        base = dict(
            listing=listing(),
            applicants=(applicant(),),
            listing_generation=7,
        )
        assert engine.handle_snapshot(Snapshot(**base, live_hover=hover(10)))
        assert states[-1].live_hover is not None
        assert states[-1].live_hover.generation == 10

        assert engine.handle_snapshot(Snapshot(**base, live_hover=hover(9)))
        assert states[-1].live_hover is not None
        assert states[-1].live_hover.generation == 10

        assert engine.handle_snapshot(
            Snapshot(
                listing=listing(),
                applicants=(),
                listing_generation=7,
            )
        )
        assert states[-1].live_hover is None
    finally:
        engine.stop(timeout=1.0)


if __name__ == "__main__":
    test_v14_hover_round_trip()
    test_v13_stays_backward_compatible()
    test_unknown_version_fails_closed()
    test_engine_keeps_newest_matching_hover()
    print("KeystoneLens APS1 live-hover transport contract passed.")
