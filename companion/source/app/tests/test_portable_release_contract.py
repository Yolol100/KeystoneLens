from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_source_release_contains_portable_build_tooling():
    build = (ROOT / "scripts/BUILD-RELEASE.sh").read_text(encoding="utf-8")

    assert "root / 'portable'" in build
    assert "root / 'runtime'" in build
    for relative in (
        "portable/build-portable.ps1",
        "portable/START-COMPANION.cmd",
        "portable/portable_launcher.py",
        "portable/LEESMIJ.txt",
        "runtime/windows-x64.json",
        "runtime/requirements-runtime.lock",
        "docs/THIRD-PARTY-NOTICES.md",
    ):
        assert (ROOT / relative).is_file(), relative


def test_portable_build_uses_neutral_runtime_contract_and_verifies_extracted_zip():
    portable = (ROOT / "portable/build-portable.ps1").read_text(encoding="utf-8")

    assert "runtime\\windows-x64.json" in portable
    assert "runtime\\requirements-runtime.lock" in portable
    assert "installer\\windows" not in portable
    assert "Get-FileHash -Algorithm SHA256" in portable
    assert "--require-hashes" in portable
    assert "verify-extracted" in portable
    assert "docs\\THIRD-PARTY-NOTICES.md" in portable
    assert "Portable package is missing third-party notices." in portable
    assert "KeystoneLens-Setup.exe" in portable
    assert "Remove-GeneratedPythonArtifacts -Root $Stage" in portable
    assert "Remove-Item -LiteralPath (Join-Path $Packages 'bin')" in portable
    assert "Remove-Item -LiteralPath (Join-Path $Runtime 'Lib\\idlelib\\idle_test')" in portable
    assert "Remove-Item -LiteralPath (Join-Path $Packages 'certifi\\tests')" in portable
    assert "Portable package contains upstream test-only data" in portable
