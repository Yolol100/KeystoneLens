from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def _pull_request_block(path: str) -> list[str]:
    lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index("  pull_request:")
    except ValueError as exc:
        raise AssertionError(f"{path} must define an explicit pull_request trigger") from exc

    body: list[str] = []
    for line in lines[start + 1 :]:
        if line and not line.startswith(" "):
            break
        if line.startswith("  ") and not line.startswith("    ") and line.strip():
            break
        body.append(line)
    return body


def _assert_no_path_filter(path: str) -> None:
    body = _pull_request_block(path)
    forbidden = [
        line.strip()
        for line in body
        if line.strip().startswith(("paths:", "paths-ignore:"))
    ]
    assert not forbidden, (
        f"{path} owns a merge-blocking PR check and must run for every PR; "
        f"path filters found: {forbidden}"
    )


def test_required_validate_check_cannot_be_skipped_by_path_filtering():
    path = ".github/workflows/rebuild-keystonelens.yml"
    text = (ROOT / path).read_text(encoding="utf-8")
    assert "\n  validate:\n" in text
    _assert_no_path_filter(path)


def test_pr_release_gate_remains_an_always_on_main_pr_gate():
    path = ".github/workflows/pr-release-gate.yml"
    body = _pull_request_block(path)
    assert any(line.strip() == "- main" for line in body)
    _assert_no_path_filter(path)
