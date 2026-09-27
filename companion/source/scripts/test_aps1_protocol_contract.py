#!/usr/bin/env python3
"""Controlled-runtime APS1 protocol invariants for existing KeystoneLens transport."""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "companion" / "source" / "app"
sys.path.insert(0, str(APP_ROOT))

from keystonelens_companion.aps1 import APS1Error, parse_snapshot  # noqa: E402


def _wrap(version: int, body: bytes, *, flags: int = 0, generation: int = 1) -> bytes:
    total_len = 13 + len(body)
    if total_len > 0xFFFF:
        raise AssertionError("test payload exceeds APS1 uint16 length")
    head = b"APS1" + bytes([version]) + struct.pack(">H", total_len) + bytes([flags, generation])
    unsigned = head + body
    return unsigned + struct.pack(">I", zlib.crc32(unsigned) & 0xFFFFFFFF)


def _text(value: str) -> bytes:
    raw = value.encode("utf-8")
    if len(raw) > 255:
        raise AssertionError("test string too long")
    return bytes([len(raw)]) + raw


def _minimal_snapshot(version: int) -> bytes:
    body = bytearray()
    body += b"\x00"  # no listing
    body += b"\x00"  # no version info
    if version >= 7:
        body += b"\x00"  # no leader key
    body += struct.pack(">H", 0)  # applicants
    if version >= 6:
        body += struct.pack(">H", 0)  # roster
    return _wrap(version, bytes(body), generation=0)


def _v12_with_application_member_count(member_count: int) -> bytes:
    body = bytearray()
    body += b"\x00"  # no listing
    body += b"\x00"  # no version info
    body += b"\x00"  # no leader key
    body += struct.pack(">H", 1)

    body += struct.pack(">I", 101)
    body += bytes([1, 8])  # member_idx, class_id
    body += struct.pack(">H", 62)  # spec
    body += struct.pack(">H", 639)  # ilvl
    body += struct.pack(">H", 2800)  # legacy/wire score
    body += struct.pack(">H", 3000)  # rio main score
    body += bytes([1, 15, 14, 8, 4, 2, 7, 1])  # rio summary
    body += bytes([2])  # damage role
    body += _text("Alice-Draenor")
    body += bytes([member_count])
    body += struct.pack(">H", 3000)
    body += bytes([14, 15])
    body += struct.pack(">H", 0)  # empty roster
    return _wrap(12, bytes(body))


def _assert_rejected(raw: bytes, label: str) -> None:
    try:
        parse_snapshot(raw)
    except APS1Error:
        return
    raise AssertionError(f"{label} was accepted")


def test_supported_snapshot_versions() -> None:
    for version in range(1, 14):
        if version == 10:
            _assert_rejected(_minimal_snapshot(version), "fragment version as snapshot")
            continue
        snapshot = parse_snapshot(_minimal_snapshot(version))
        assert snapshot.listing is None
        assert snapshot.applicants == ()
        assert snapshot.party == ()


def test_unknown_versions_are_rejected() -> None:
    _assert_rejected(_minimal_snapshot(0), "wire version 0")
    _assert_rejected(_minimal_snapshot(14), "wire version 14")


def test_truncation_is_rejected_at_every_boundary() -> None:
    raw = _v12_with_application_member_count(1)
    for cut in range(len(raw)):
        _assert_rejected(raw[:cut], f"truncated payload at byte {cut}")


def test_crc_valid_trailing_byte_is_rejected() -> None:
    body = bytearray()
    body += b"\x00\x00\x00"
    body += struct.pack(">H", 0)
    body += struct.pack(">H", 0)
    body += b"\x00"
    _assert_rejected(_wrap(12, bytes(body)), "CRC-valid trailing body byte")


def test_application_member_count_must_match_encoder_contract() -> None:
    for invalid in (0, 6):
        _assert_rejected(
            _v12_with_application_member_count(invalid),
            f"invalid application member count {invalid}",
        )


if __name__ == "__main__":
    test_supported_snapshot_versions()
    test_unknown_versions_are_rejected()
    test_truncation_is_rejected_at_every_boundary()
    test_crc_valid_trailing_byte_is_rejected()
    test_application_member_count_must_match_encoder_contract()
    print("KeystoneLens APS1 protocol contract passed.")
