#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
import unicodedata
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]
VERSION_FILE = ROOT / "companion/source/VERSION"
MAX_TEXT_BYTES = 2 * 1024 * 1024
BINARY_SOURCE_SUFFIXES = {".ico", ".tga", ".png", ".jpg", ".jpeg", ".gif"}
FORBIDDEN_TRACKED_SUFFIXES = {".zip", ".exe", ".pfx", ".p12", ".pem", ".key", ".pyc", ".pyo", ".log", ".tmp", ".bak", ".orig", ".rej"}
FORBIDDEN_PATH_PARTS = {"__pycache__", ".pytest_cache", ".venv", "venv", ".idea", ".vscode", "build", "release"}
REQUIRED_FILES = {
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    ".github/CODEOWNERS",
    ".github/dependabot.yml",
    "LICENSE-SCOPE.md",
    "README.md",
    "SECURITY.md",
    "companion/source/VERSION",
}
GENERATED_REPOSITORY_PATHS = {
    "SHA256SUMS.txt",
    "companion/source/installer/windows/bootstrap/payload.zip",
}
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b"),
    "OpenAI key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b"),
}


def fail(message: str) -> None:
    print(f"error - {message}", file=sys.stderr)
    raise SystemExit(1)


def git_files() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [item.decode("utf-8") for item in raw.split(b"\0") if item]


def read_text(rel: str) -> str:
    data = (ROOT / rel).read_bytes()
    if len(data) > MAX_TEXT_BYTES:
        fail(f"tracked text exceeds {MAX_TEXT_BYTES} bytes: {rel}")
    if b"\0" in data:
        fail(f"unexpected binary/NUL content in text file: {rel}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        fail(f"tracked text must be UTF-8: {rel}")
    if "\r" in text:
        fail(f"tracked text must use LF line endings: {rel}")
    if data and not data.endswith(b"\n"):
        fail(f"tracked text must end with a newline: {rel}")
    return text


def canonical_version() -> str:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        fail(f"invalid canonical VERSION: {version!r}")
    return version


def require_exact_line(rel: str, line: str) -> None:
    if line not in read_text(rel).splitlines():
        fail(f"release identity mismatch in {rel}: missing {line!r}")


def main() -> int:
    files = git_files()
    file_set = set(files)
    if not files:
        fail("repository contains no tracked files")

    missing = sorted(REQUIRED_FILES - file_set)
    if missing:
        fail("required repository metadata is missing: " + ", ".join(missing))

    forbidden_generated = sorted(GENERATED_REPOSITORY_PATHS & file_set)
    if forbidden_generated:
        fail("generated release output must not be tracked: " + ", ".join(forbidden_generated))

    seen: dict[str, str] = {}
    for rel in files:
        if unicodedata.normalize("NFC", rel) != rel:
            fail(f"path is not NFC-normalized: {rel}")
        path = PurePosixPath(rel)
        if path.is_absolute() or ".." in path.parts:
            fail(f"unsafe tracked path: {rel}")
        if any(part in FORBIDDEN_PATH_PARTS for part in path.parts):
            fail(f"generated/local directory must not be tracked: {rel}")
        if path.suffix.lower() in FORBIDDEN_TRACKED_SUFFIXES or rel.endswith("~"):
            fail(f"generated/sensitive file must not be tracked: {rel}")
        key = rel.casefold()
        if key in seen and seen[key] != rel:
            fail(f"case-colliding tracked paths: {seen[key]} / {rel}")
        seen[key] = rel
        if (ROOT / rel).is_symlink():
            fail(f"symlinks are not allowed: {rel}")
        if path.suffix.lower() in BINARY_SOURCE_SUFFIXES:
            continue
        text = read_text(rel)
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                fail(f"possible {label} committed in {rel}")

    version = canonical_version()
    require_exact_line("companion/source/app/keystonelens_companion/__init__.py", f'__version__ = "{version}"')
    require_exact_line("addon/KeystoneLensBridge/KeystoneLensBridge.toc", f"## Version: {version}")
    require_exact_line("companion/source/data-addon/KeystoneLensCompanionData/KeystoneLensCompanionData.toc", f"## Version: {version}")

    sign_source = read_text("companion/source/installer/windows/sign-release.ps1")
    if re.search(r"(?m)^\$Version\s*=\s*'\d+\.\d+\.\d+'\s*$", sign_source):
        fail("sign-release.ps1 must read the canonical VERSION instead of hard-coding a release")
    if "Get-Content -LiteralPath $VersionFile" not in sign_source:
        fail("sign-release.ps1 is not bound to the canonical VERSION file")

    workflow_paths = [rel for rel in files if rel.startswith(".github/workflows/") and rel.endswith((".yml", ".yaml"))]
    for rel in workflow_paths:
        text = read_text(rel)
        if "permissions:" not in text:
            fail(f"workflow must declare permissions explicitly: {rel}")
        for uses in re.findall(r"^\s*-?\s*uses:\s*([^\s#]+)", text, re.M):
            if uses.startswith(("./", "docker://")):
                continue
            if "@" not in uses or not re.fullmatch(r"[0-9a-f]{40}", uses.rsplit("@", 1)[1]):
                fail(f"workflow action must be pinned to a full commit SHA: {rel}: {uses}")
        if re.search(r"(?:curl|wget)[^\n|]*\|\s*(?:ba)?sh\b", text):
            fail(f"download-to-shell pattern detected: {rel}")

    release_workflow = read_text(".github/workflows/rebuild-keystonelens.yml")
    if "git push origin" in release_workflow or "git commit -m" in release_workflow:
        fail("release workflow must publish release assets instead of committing generated binaries to main")
    if "refs/tags/v" not in release_workflow:
        fail("release workflow must have an explicit tag-only public release gate")
    if "KEYSTONELENS_PFX_BASE64" not in release_workflow or "KEYSTONELENS_PFX_PASSWORD" not in release_workflow:
        fail("tag release must fail closed behind the configured signing secrets")

    print(f"ok - KeystoneLens repository audit passed ({len(files)} tracked files; version {version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
