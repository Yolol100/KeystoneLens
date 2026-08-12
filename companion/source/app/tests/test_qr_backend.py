from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from keystonelens_companion import aps1


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
