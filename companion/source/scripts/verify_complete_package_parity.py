#!/usr/bin/env python3
"""Verify exact source-to-package parity for KeystoneLens release-owned files."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys


def git_blob_sha(data: bytes) -> str:
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data).hexdigest()


def tracked_blob_sha(repo_root: Path, source_rel: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", f"HEAD:{source_rel}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def add_tree(
    mapping: dict[str, str],
    repo_root: Path,
    source_root: str,
    package_root: str,
) -> None:
    source_dir = repo_root / source_root
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(source_dir).as_posix()
        mapping[f"{package_root}/{rel}"] = f"{source_root}/{rel}"


def build_mapping(repo_root: Path) -> dict[str, str]:
    mapping: dict[str, str] = {
        "Windows-Companion/app/KeystoneLens.ico":
            "companion/source/app/KeystoneLens.ico",
        "Windows-Companion/START-COMPANION.cmd":
            "companion/source/portable/START-COMPANION.cmd",
        "Windows-Companion/portable_launcher.py":
            "companion/source/portable/portable_launcher.py",
        "Windows-Companion/LEESMIJ.txt":
            "companion/source/portable/LEESMIJ.txt",
        "Windows-Companion/VERSION":
            "companion/source/VERSION",
        "Windows-Companion/RUNTIME.json":
            "companion/source/runtime/windows-x64.json",
        "Windows-Companion/THIRD-PARTY-NOTICES.md":
            "companion/source/docs/THIRD-PARTY-NOTICES.md",
    }
    add_tree(
        mapping,
        repo_root,
        "companion/source/app/keystonelens_companion",
        "Windows-Companion/app/keystonelens_companion",
    )
    add_tree(
        mapping,
        repo_root,
        "addon/KeystoneLensBridge",
        "WoW-AddOns/KeystoneLensBridge",
    )
    add_tree(
        mapping,
        repo_root,
        "companion/source/data-addon/KeystoneLensCompanionData",
        "WoW-AddOns/KeystoneLensCompanionData",
    )
    return mapping


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_complete_package_parity.py <extracted-package-root>")

    repo_root = Path(__file__).resolve().parents[3]
    package_root = Path(sys.argv[1]).resolve()
    if not package_root.is_dir():
        raise SystemExit(f"package root does not exist: {package_root}")

    mapping = build_mapping(repo_root)
    failures: list[str] = []

    for package_rel, source_rel in sorted(mapping.items()):
        source = repo_root / source_rel
        packaged = package_root / package_rel
        if not packaged.is_file():
            failures.append(f"missing packaged file: {package_rel}")
            continue

        source_bytes = source.read_bytes()
        package_bytes = packaged.read_bytes()
        source_blob = git_blob_sha(source_bytes)
        tracked_blob = tracked_blob_sha(repo_root, source_rel)

        if source_blob != tracked_blob:
            failures.append(
                f"checkout bytes differ from HEAD blob: {source_rel} "
                f"(working={source_blob}, head={tracked_blob})"
            )
        if package_bytes != source_bytes:
            failures.append(f"package bytes differ from tested source: {package_rel}")

    installer = package_root / "INSTALLEREN.txt"
    if not installer.is_file():
        failures.append("missing generated INSTALLEREN.txt")
    else:
        text = installer.read_text(encoding="utf-8-sig")
        version = (repo_root / "companion/source/VERSION").read_text(encoding="utf-8").strip()
        for required in (
            f"KeystoneLens {version} - Complete pakket",
            "Nieuwe applicants verschijnen automatisch in de Windows-lijst.",
            "Warcraft Logs: DPS xx% of Healing xx%",
            "Rank: S/A/B/C/D/E/F",
        ):
            if required not in text:
                failures.append(f"INSTALLEREN.txt missing contract text: {required}")

    if failures:
        print("KeystoneLens complete-package parity FAILED:")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print(
        "KeystoneLens complete-package parity passed: "
        f"{len(mapping)} source-owned files match HEAD and package bytes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
