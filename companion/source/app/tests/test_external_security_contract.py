from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_external_security_contract() -> None:
    source_root = Path(__file__).resolve().parents[2]
    script = source_root / "scripts" / "audit_external_security.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=source_root,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "external Companion, dependency, API, SBOM, signing and addon-wire security gates passed" in result.stdout
