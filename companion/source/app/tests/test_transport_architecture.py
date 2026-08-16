from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def test_transport_state_is_split_and_loaded_before_transport():
    root = _repo_root()
    toc = (root / "addon/KeystoneLensBridge/KeystoneLensBridge.toc").read_text(encoding="utf-8")
    transport = (root / "addon/KeystoneLensBridge/Core/Transport.lua").read_text(encoding="utf-8")
    state = (root / "addon/KeystoneLensBridge/Core/TransportState.lua").read_text(encoding="utf-8")
    assert toc.index("Core\\TransportState.lua") < toc.index("Core\\Transport.lua")
    assert "local qrFrame =" not in transport
    assert "local qrTexturePool =" not in transport
    assert "State.New" in state
    assert "qrTexturePool = {}" in state
