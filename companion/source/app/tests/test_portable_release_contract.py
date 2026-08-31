from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_source_release_contains_portable_build_tooling():
    build = (ROOT / "scripts/BUILD-RELEASE.sh").read_text(encoding="utf-8")

    assert "root / 'portable'" in build
    for relative in (
        "portable/build-portable.ps1",
        "portable/START-COMPANION.cmd",
        "portable/portable_launcher.py",
        "portable/LEESMIJ.txt",
        "docs/THIRD-PARTY-NOTICES.md",
    ):
        assert (ROOT / relative).is_file(), relative


def test_portable_build_uses_canonical_runtime_and_verifies_extracted_zip():
    portable = (ROOT / "portable/build-portable.ps1").read_text(encoding="utf-8")

    assert "installer\\windows\\bootstrap\\installer.ps1" in portable
    assert "requirements-runtime.lock" in portable
    assert "Get-FileHash -Algorithm SHA256" in portable
    assert "--require-hashes" in portable
    assert "verify-extracted" in portable
    assert "docs\\THIRD-PARTY-NOTICES.md" in portable
    assert "Portable package is missing third-party notices." in portable
    assert "Portable package must not contain KeystoneLens-Setup.exe." in portable
