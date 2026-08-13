from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from keystonelens_companion import aps1


REPO = Path(__file__).resolve().parents[4]
BRIDGE = REPO / "addon" / "KeystoneLensBridge"


def test_zxing_qr_backend_accepts_keystonelens_payload(tmp_path):
    raw = b"APS1\x01fixture"
    expected = object()
    calls = []

    fake_zxing = SimpleNamespace(
        BarcodeFormat=SimpleNamespace(QRCode="QR"),
        read_barcodes=lambda image, formats=None: (
            calls.append((image.size, formats)) or [SimpleNamespace(bytes=raw)]
        ),
    )
    image_path = tmp_path / "capture.png"
    Image.new("RGB", (64, 64), "white").save(image_path)

    with patch.dict(sys.modules, {"zxingcpp": fake_zxing}), patch.object(
        aps1, "parse_snapshot", return_value=expected
    ):
        owned, consumed, snapshot = aps1.decode_image_result(image_path, aps1.FragmentAssembler())

    assert owned is True
    assert consumed is True
    assert snapshot is expected
    assert calls and calls[0][1] == "QR"


def test_bridge_toc_has_one_explicit_runtime_order():
    toc = (BRIDGE / "KeystoneLensBridge.toc").read_text(encoding="utf-8")
    runtime = [line.strip() for line in toc.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    assert runtime == [
        r"Libs\qrencode.lua",
        r"Core\CapturePolicy.lua",
        r"Core\ScreenshotController.lua",
        r"Core\Transport.lua",
        r"Core\Tooltip.lua",
    ]


def test_bridge_capture_policy_stays_pure_and_listing_gated():
    source = (BRIDGE / "Core" / "CapturePolicy.lua").read_text(encoding="utf-8")
    assert "CreateFrame" not in source
    assert "C_LFGList" not in source
    assert "SetCVar" not in source
    assert "if lfgReadsAllowed then" in source
    assert "return hosting" in source
    assert "return sessionActive and hasRoster" in source


def test_bridge_transport_keeps_secret_safe_optional_numbers():
    source = (BRIDGE / "Core" / "Transport.lua").read_text(encoding="utf-8")
    assert "local function SafeOptionalNumber(v)" in source
    assert "if IsSecretValue(v) or v == nil then return nil end" in source
    assert source.count("SafeOptionalNumber(") >= 5
    assert "expectedGroups = countOK and SafeOptionalNumber(rawCount) or nil" in source
    assert "physicalHeight = screenOK and SafeOptionalNumber(physicalHeight) or nil" in source
    assert "effectiveScale = scaleOK and SafeOptionalNumber(effectiveScale) or nil" in source


def test_screenshot_controller_keeps_generation_and_phase_guards():
    source = (BRIDGE / "Core" / "ScreenshotController.lua").read_text(encoding="utf-8")
    for phase in ("PHASE_IDLE", "PHASE_BUILDING", "PHASE_SETTLING", "PHASE_WAITING"):
        assert phase in source
    assert "if self.jobGen ~= jobGen then return false end" in source
    assert "if self.state.screenshotCVarLeaseGeneration ~= leaseGeneration then" in source
    assert "self.phase ~= PHASE_WAITING" in source
