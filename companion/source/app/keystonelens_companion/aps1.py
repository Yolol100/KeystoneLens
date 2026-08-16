"""APS1 transport decoder.

The WoW addon owns the current Group Finder snapshot. The companion only applies
complete authoritative domains: applicant or roster partials retain the last
confirmed state instead of being interpreted as removals.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct
import time
import warnings
import zlib
from pathlib import Path
from typing import Iterable

from .models import Applicant, Listing, PartyMember, Snapshot, VersionInfo

MAGIC = b"APS1"
SUPPORTED = set(range(1, 14))
FRAGMENT_VERSION = 10
FRAGMENT_CHUNK_BYTES = 320
FLAG_TERMINAL_CLEAR = 0x01
FLAG_LFG_UNAVAILABLE = 0x02
FLAG_ROSTER_UNAVAILABLE = 0x04
FLAG_APPLICANTS_UNAVAILABLE = 0x08
MAX_FRAGMENT_STREAMS = 64
MAX_SCREENSHOT_BYTES = 128 * 1024 * 1024
MAX_IMAGE_PIXELS = 50_000_000
MAX_IMAGE_DIMENSION = 16_384


class APS1Error(ValueError):
    pass


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def _take(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise APS1Error("truncated APS1 body")
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def u8(self) -> int:
        return self._take(1)[0]

    def u16(self) -> int:
        return struct.unpack(">H", self._take(2))[0]

    def u32(self) -> int:
        return struct.unpack(">I", self._take(4))[0]

    def boolean(self) -> bool:
        value = self.u8()
        if value not in (0, 1):
            raise APS1Error(f"invalid bool {value}")
        return bool(value)

    def text(self, encoding: str = "utf-8") -> str:
        n = self.u8()
        try:
            return self._take(n).decode(encoding)
        except UnicodeDecodeError as exc:
            raise APS1Error("invalid APS1 string") from exc


@dataclass(frozen=True)
class Fragment:
    stream_id: int
    generation: int
    index: int
    count: int
    inner_len: int
    inner_crc: int
    chunk: bytes


def _validate_outer(raw: bytes) -> tuple[int, int, int, bytes]:
    if not raw.startswith(MAGIC) or len(raw) < 13:
        raise APS1Error("not a complete APS1 payload")
    version = raw[4]
    if version not in SUPPORTED:
        raise APS1Error(f"unsupported APS1 wire version {version}")
    total_len = struct.unpack(">H", raw[5:7])[0]
    if total_len != len(raw) or total_len < 13:
        raise APS1Error("APS1 total length mismatch")
    body = raw[:-4]
    expected = struct.unpack(">I", raw[-4:])[0]
    actual = zlib.crc32(body) & 0xFFFFFFFF
    if expected != actual:
        raise APS1Error("APS1 CRC mismatch")
    flags = raw[7]
    reserved = raw[8]
    return version, flags, reserved, raw[9:-4]


def parse_fragment(raw: bytes) -> Fragment:
    version, flags, reserved, body = _validate_outer(raw)
    if version != FRAGMENT_VERSION:
        raise APS1Error("not an APS1 fragment")
    if flags or reserved:
        raise APS1Error("invalid fragment flags")
    if len(body) < 19:
        raise APS1Error("fragment metadata truncated")
    stream_id, generation, index, count, inner_len, inner_crc = struct.unpack(">IIHHHI", body[:18])
    chunk = body[18:]
    if count < 2 or count > 128 or index >= count:
        raise APS1Error("invalid fragment sequence")
    expected_count = (inner_len + FRAGMENT_CHUNK_BYTES - 1) // FRAGMENT_CHUNK_BYTES
    if count != expected_count:
        raise APS1Error("fragment count does not match inner length")
    expected_chunk = (
        FRAGMENT_CHUNK_BYTES
        if index < count - 1
        else inner_len - FRAGMENT_CHUNK_BYTES * (count - 1)
    )
    if len(chunk) != expected_chunk:
        raise APS1Error("fragment chunk length mismatch")
    return Fragment(stream_id, generation, index, count, inner_len, inner_crc, chunk)


def _read_rio_summary(r: _Reader, version: int) -> tuple[int, bool, int, int, int, int, int, int, int]:
    if version >= 5:
        main_score = r.u16()
        rio_profile = r.boolean()
        rio_best_key = r.u8()
        rio_best_dungeon_key = r.u8()
        rio_timed = r.u8()
        rio_timed_m1 = r.u8()
        rio_timed_m2 = r.u8()
        rio_completed_m1 = r.u8()
        rio_dungeon_count = r.u8()
        return (
            main_score, rio_profile, rio_best_key, rio_best_dungeon_key,
            rio_timed, rio_timed_m1, rio_timed_m2, rio_completed_m1,
            rio_dungeon_count,
        )
    return (0, False, 0, 0, 0, 0, 0, 0, 0)


def parse_snapshot(raw: bytes) -> Snapshot:
    version, flags, listing_generation, body = _validate_outer(raw)
    if version == FRAGMENT_VERSION:
        raise APS1Error("fragment must be assembled first")
    r = _Reader(body)

    listing = None
    if r.boolean():
        activity_id = r.u32()
        category_id = difficulty_id = 0
        if version >= 3:
            category_id = r.u16()
            difficulty_id = r.u16()
        key_level = r.u8()
        listing = Listing(
            activity_id=activity_id,
            key_level=key_level,
            dungeon_name=r.text(),
            listing_name=r.text(),
            comment=r.text(),
            category_id=category_id,
            difficulty_id=difficulty_id,
        )

    version_info = None
    if r.boolean():
        version_info = VersionInfo(
            addon_version=r.text("ascii"),
            game_version=r.text("ascii"),
            region_id=r.u8(),
            player_name=r.text(),
        )

    if version >= 7 and r.boolean():
        r.u8()   # leader key
        r.u16()  # challenge map
        r.text() # leader name

    count = r.u16()
    if count > 500:
        raise APS1Error("unreasonable applicant count")
    applicants: list[Applicant] = []
    for _ in range(count):
        aid = r.u32()
        member_idx = r.u8() if version >= 2 else 1
        class_id = r.u8()
        spec_id = r.u16()
        ilvl = r.u16()
        wire_score = r.u16()
        (
            main_score, rio_profile, rio_best_key, rio_best_dungeon_key,
            rio_timed, rio_timed_m1, rio_timed_m2, rio_completed_m1,
            rio_dungeon_count,
        ) = _read_rio_summary(r, version)
        role = r.u8()
        if role not in (0, 1, 2, 3):
            raise APS1Error("invalid role")
        name = r.text()

        application_member_count = 1
        blizzard_score = 0
        blizzard_best_dungeon_key = 0
        blizzard_best_key = 0
        if version >= 12:
            application_member_count = max(1, min(5, r.u8()))
            blizzard_score = r.u16()
            blizzard_best_dungeon_key = r.u8()
            blizzard_best_key = r.u8()
            rio_score = wire_score
        else:
            # <=0.8.5 wrote Blizzard's dungeonScore into the slot named
            # rio_score. Do not keep propagating that semantic mistake.
            rio_score = 0
            blizzard_score = wire_score

        if name:
            applicants.append(Applicant(
                applicant_id=aid,
                member_idx=member_idx,
                class_id=class_id,
                spec_id=spec_id,
                ilvl=ilvl,
                rio_score=rio_score,
                rio_main_score=main_score,
                role_byte=role,
                name=name,
                rio_profile=rio_profile,
                rio_best_key=rio_best_key,
                rio_best_dungeon_key=rio_best_dungeon_key,
                rio_timed_at_or_above=rio_timed,
                rio_timed_at_or_above_minus1=rio_timed_m1,
                rio_timed_at_or_above_minus2=rio_timed_m2,
                rio_completed_at_or_above_minus1=rio_completed_m1,
                rio_dungeon_count=rio_dungeon_count,
                application_member_count=application_member_count,
                blizzard_score=blizzard_score,
                blizzard_best_dungeon_key=blizzard_best_dungeon_key,
                blizzard_best_key=blizzard_best_key,
            ))

    party: list[PartyMember] = []
    if version >= 6:
        roster_count = r.u16()
        if roster_count > 40:
            raise APS1Error("unreasonable roster count")
        for _ in range(roster_count):
            unit_index = r.u8()
            roster_flags = r.u8()
            subgroup = r.u8()
            class_id = r.u8()
            spec_id = r.u16()
            ilvl = r.u16()
            rio_score = r.u16()
            (
                main_score, rio_profile, rio_best_key, rio_best_dungeon_key,
                rio_timed, rio_timed_m1, rio_timed_m2, rio_completed_m1,
                rio_dungeon_count,
            ) = _read_rio_summary(r, version)
            role = r.u8()
            if role not in (0, 1, 2, 3):
                raise APS1Error("invalid roster role")
            name = r.text()
            if name:
                party.append(PartyMember(
                    unit_index=unit_index,
                    flags=roster_flags,
                    subgroup=subgroup,
                    class_id=class_id,
                    spec_id=spec_id,
                    ilvl=ilvl,
                    rio_score=rio_score,
                    rio_main_score=main_score,
                    role_byte=role,
                    name=name,
                    rio_profile=rio_profile,
                    rio_best_key=rio_best_key,
                    rio_best_dungeon_key=rio_best_dungeon_key,
                    rio_timed_at_or_above=rio_timed,
                    rio_timed_at_or_above_minus1=rio_timed_m1,
                    rio_timed_at_or_above_minus2=rio_timed_m2,
                    rio_completed_at_or_above_minus1=rio_completed_m1,
                    rio_dungeon_count=rio_dungeon_count,
                ))

    if r.pos != len(body):
        raise APS1Error(f"trailing APS1 bytes ({len(body) - r.pos})")

    return Snapshot(
        listing=listing,
        version=version_info,
        applicants=tuple(applicants),
        party=tuple(party),
        listing_generation=listing_generation,
        terminal_clear=bool(flags & FLAG_TERMINAL_CLEAR),
        lfg_unavailable=bool(flags & FLAG_LFG_UNAVAILABLE),
        roster_unavailable=bool(flags & FLAG_ROSTER_UNAVAILABLE),
        applicants_unavailable=bool(flags & FLAG_APPLICANTS_UNAVAILABLE),
    )


def qr_candidates(payloads: Iterable[bytes]) -> Iterable[bytes]:
    for data in payloads:
        if data.startswith(MAGIC):
            yield data
            continue
        try:
            decoded = bytes.fromhex(data.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            continue
        if decoded.startswith(MAGIC):
            yield decoded


class FragmentAssembler:
    def __init__(self, ttl: float = 300.0, max_streams: int = MAX_FRAGMENT_STREAMS):
        self.ttl = max(1.0, float(ttl))
        self.max_streams = max(1, int(max_streams))
        self._streams: dict[tuple[int, int], tuple[float, Fragment, dict[int, bytes]]] = {}

    def has_pending_streams(self) -> bool:
        now = time.monotonic()
        self._streams = {
            key: value
            for key, value in self._streams.items()
            if now - value[0] <= self.ttl
        }
        return bool(self._streams)

    def push(self, fragment: Fragment) -> bytes | None:
        now = time.monotonic()
        self._streams = {key: value for key, value in self._streams.items() if now - value[0] <= self.ttl}
        key = (fragment.stream_id, fragment.generation)
        if key not in self._streams:
            # A Screenshots folder is user-controlled input. Keep incomplete or
            # malicious fragment IDs from growing the Companion without bound.
            while len(self._streams) >= self.max_streams:
                oldest = min(self._streams, key=lambda item: self._streams[item][0])
                self._streams.pop(oldest, None)
            self._streams[key] = (now, fragment, {})
        _created, first, chunks = self._streams[key]
        if (first.count, first.inner_len, first.inner_crc) != (
            fragment.count, fragment.inner_len, fragment.inner_crc,
        ):
            self._streams.pop(key, None)
            raise APS1Error("fragment metadata changed mid-stream")
        chunks[fragment.index] = fragment.chunk
        if len(chunks) != fragment.count:
            return None
        raw = b"".join(chunks[index] for index in range(fragment.count))
        self._streams.pop(key, None)
        if len(raw) != fragment.inner_len:
            raise APS1Error("reassembled APS1 length mismatch")
        if len(raw) < 4 or struct.unpack(">I", raw[-4:])[0] != fragment.inner_crc:
            raise APS1Error("reassembled APS1 CRC metadata mismatch")
        # parse_snapshot independently verifies the CRC over the reassembled
        # logical payload. Keep the fragment metadata check separate so a
        # corrupted payload can never pass merely because its trailer matches.
        parse_snapshot(raw)
        return raw


def decode_image_result(path: Path, assembler: FragmentAssembler) -> tuple[bool, bool, Snapshot | None]:
    """Return (owned_by_APS1_transport, consumed, complete_snapshot_or_none).

    ``consumed`` is true only when a valid KeystoneLens payload was accepted by
    the fragment assembler/parser. The watcher may permanently delete a file
    only after this flag is true.
    """
    try:
        from PIL import Image
        import zxingcpp
    except Exception as exc:  # pragma: no cover - depends on Windows runtime
        raise RuntimeError(f"QR decoder unavailable: {exc}") from exc

    def decode_qr(image) -> list[bytes]:
        # zxing-cpp accepts PIL images directly and ships a current CPython
        # 3.12+ Windows x64 ABI3 wheel. Limit scanning to QR codes only.
        results = zxingcpp.read_barcodes(
            image,
            formats=zxingcpp.BarcodeFormat.QRCode,
        )
        return [bytes(item.bytes) for item in results]

    def accept_batch(payloads: list[bytes]) -> tuple[bool, bool, Snapshot | None]:
        owned = False
        fragment_consumed = False
        for raw in qr_candidates(payloads):
            owned = True
            try:
                if len(raw) > 4 and raw[4] == FRAGMENT_VERSION:
                    assembled = assembler.push(parse_fragment(raw))
                    if assembled is None:
                        # A valid fragment was consumed, but another QR in this
                        # same screenshot may already contain a complete newer
                        # snapshot. Keep scanning before returning partial work.
                        fragment_consumed = True
                        continue
                    return True, True, parse_snapshot(assembled)
                return True, True, parse_snapshot(raw)
            except APS1Error:
                # A malformed APS1-looking QR must not mask another valid QR in
                # the same screenshot or prevent the full-image fallback.
                continue
        return owned, fragment_consumed, None

    try:
        file_size = path.stat().st_size
    except OSError as exc:
        raise APS1Error("screenshot disappeared before decode") from exc
    if file_size <= 0 or file_size > MAX_SCREENSHOT_BYTES:
        raise APS1Error("screenshot file size outside safe decode limits")

    # Pillow guards decompression bombs with a warning/error around its default
    # pixel threshold. Treat the warning as a hard failure and apply a stricter
    # product-specific pixel/dimension cap before loading image data.
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as image:
            width, height = image.size
            if (
                width <= 0 or height <= 0
                or width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION
                or width * height > MAX_IMAGE_PIXELS
            ):
                raise APS1Error("screenshot dimensions outside safe decode limits")
            image.load()
            crop_width, crop_height = min(width, 720), min(height, 720)
            owned_any = False
            consumed_any = False

            # Current transport renders three physical pixels per QR module into a
            # lossless PNG. ZXing is more reliable when the crop is optionally
            # expanded with nearest-neighbour sampling on unusual DPI/framebuffer
            # setups. Decode only the small top-left search area at 4x so a 4K
            # screenshot does not become a large temporary bitmap. Keep the raw and
            # full-image passes as backwards-compatible fallbacks for older JPG/TGA
            # bridge captures and for a QR that was moved outside the search crop.
            with image.crop((0, 0, crop_width, crop_height)) as crop:
                first_batch = decode_qr(crop)
                owned, consumed, snapshot = accept_batch(first_batch)
                owned_any = owned_any or owned
                consumed_any = consumed_any or consumed
                if snapshot is not None:
                    return owned_any, True, snapshot

                # A different/malformed QR in the crop must not suppress this pass:
                # the enlarged crop may be the only representation ZXing can decode
                # for the actual KeystoneLens QR on unusual framebuffer/DPI setups.
                enlarged = crop.resize(
                    (crop_width * 4, crop_height * 4),
                    resample=Image.Resampling.NEAREST,
                )
                try:
                    enlarged_batch = decode_qr(enlarged)
                finally:
                    enlarged.close()
                owned, consumed, snapshot = accept_batch(enlarged_batch)
                owned_any = owned_any or owned
                consumed_any = consumed_any or consumed
                if snapshot is not None:
                    return owned_any, True, snapshot

            # A random QR (or a malformed APS1-looking QR) in the crop must not stop
            # us from finding a valid KeystoneLens QR elsewhere in the screenshot.
            if (width, height) != (crop_width, crop_height):
                full_batch = decode_qr(image)
                owned, consumed, snapshot = accept_batch(full_batch)
                owned_any = owned_any or owned
                consumed_any = consumed_any or consumed
                if snapshot is not None:
                    return owned_any, True, snapshot

    return owned_any, consumed_any, None
