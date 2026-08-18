from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_current_release_documents_follow_canonical_version():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert version and version.count(".") == 2

    current_docs = [
        ROOT / "README-NL.md",
        ROOT / "docs/CURSEFORGE-UPLOAD.md",
        ROOT / "docs/CURSEFORGE-BESCHRIJVING.md",
        ROOT / "docs/SIGNING-REQUIRED.md",
        ROOT / "docs/DEPENDENCIES.md",
        ROOT / "docs/LIVE-WOW-ACCEPTATIE.md",
        ROOT / "docs/SNELSTART.md",
        ROOT / "docs/TESTSCENARIOS.md",
        ROOT / "docs/UITGAVE-CHECKLIST.md",
        ROOT / "docs/TECHNIEK-EN-SCORE.md",
        ROOT / "docs/PROBLEMEN-OPLOSSEN.md",
    ]
    for path in current_docs:
        text = path.read_text(encoding="utf-8")
        assert version in text, f"{path} does not describe canonical release {version}"

    sbom = json.loads((ROOT / "docs/SBOM.cdx.json").read_text(encoding="utf-8"))
    assert sbom["metadata"]["component"]["version"] == version


def test_version_specific_release_evidence_exists():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert (ROOT / f"docs/RELEASE-NOTES-{version}.md").is_file()
    assert (ROOT / f"docs/AUDIT-REPORT-{version}.md").is_file()
