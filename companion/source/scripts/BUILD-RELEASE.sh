#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '\r\n' < "$ROOT/VERSION")"
OUT="$ROOT/release"
STAGE="$OUT/master"
ADDON_ZIP="$OUT/KeystoneLensBridge-${VERSION}-CurseForge.zip"
SETUP_SRC="$ROOT/installer/windows/build/KeystoneLens-Setup.exe"
SETUP_OUT="$OUT/KeystoneLens-Setup-${VERSION}.exe"
MASTER_ZIP="$OUT/KeystoneLens-Release-${VERSION}.zip"
SOURCE_ZIP="$OUT/KeystoneLens-Source-${VERSION}.zip"
RELEASE_NOTES="$ROOT/docs/RELEASE-NOTES-${VERSION}.md"
AUDIT_REPORT="$ROOT/docs/AUDIT-REPORT-${VERSION}.md"

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "ERROR: invalid VERSION '$VERSION'" >&2
  exit 1
fi
[[ -f "$RELEASE_NOTES" ]] || { echo "ERROR: missing release notes for $VERSION" >&2; exit 1; }
[[ -f "$AUDIT_REPORT" ]] || { echo "ERROR: missing audit report for $VERSION" >&2; exit 1; }
grep -Fx "__version__ = \"$VERSION\"" "$ROOT/app/keystonelens_companion/__init__.py" >/dev/null
grep -Fx "## Version: $VERSION" "$ROOT/addon/KeystoneLensBridge/KeystoneLensBridge.toc" >/dev/null

rm -rf "$OUT"
mkdir -p "$OUT" "$STAGE/CurseForge-Upload" "$STAGE/Companion" "$STAGE/Documentation" "$STAGE/Source" "$STAGE/checksums"

if [[ "${KEYSTONELENS_SKIP_WINDOWS_BUILD:-0}" != "1" ]]; then
  "$ROOT/installer/windows/build.sh" >/dev/null
fi

cd "$ROOT"
pytest >/dev/null
python3 -m compileall -q app/keystonelens_companion
python3 "$ROOT/installer/windows/verify_pe_resources.py" --exe "$ROOT/installer/windows/build/payload/KeystoneLens.exe" --version "${VERSION}.0" --description "KeystoneLens Companion" >/dev/null
python3 "$ROOT/installer/windows/verify_pe_resources.py" --exe "$ROOT/installer/windows/build/payload/KeystoneLens-Uninstall.exe" --version "${VERSION}.0" --description "KeystoneLens Companion Uninstaller" >/dev/null
python3 "$ROOT/installer/windows/verify_pe_resources.py" --exe "$ROOT/installer/windows/build/payload/KeystoneLens-WoW-Watcher.exe" --version "${VERSION}.0" --description "KeystoneLens WoW Launch Watcher" >/dev/null
python3 "$ROOT/installer/windows/verify_pe_resources.py" --exe "$SETUP_SRC" --version "${VERSION}.0" --description "KeystoneLens Companion Setup" >/dev/null
if grep -Rqi 'pyzbar' "$ROOT/app/keystonelens_companion" "$ROOT/app/requirements.txt" "$ROOT/installer/windows/requirements-runtime.txt" "$ROOT/installer/windows/requirements-runtime.lock"; then
  echo "ERROR: obsolete pyzbar runtime reference remains" >&2
  exit 1
fi

python3 - "$ROOT/addon/KeystoneLensBridge" "$ADDON_ZIP" <<'PY'
from pathlib import Path
import stat
import sys
import zipfile

source = Path(sys.argv[1])
out = Path(sys.argv[2])
fixed = (1980, 1, 1, 0, 0, 0)
root_name = source.name
with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for path in sorted(p for p in source.rglob('*') if p.is_file()):
        rel = Path(root_name) / path.relative_to(source)
        info = zipfile.ZipInfo(rel.as_posix(), fixed)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        zf.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
PY

python3 - "$ROOT" "$SOURCE_ZIP" "$VERSION" <<'PY'
from pathlib import Path
import re
import stat
import sys
import zipfile

root = Path(sys.argv[1])
out = Path(sys.argv[2])
version = sys.argv[3]
fixed = (1980, 1, 1, 0, 0, 0)
selected = [root / 'VERSION', root / 'README-NL.md', root / 'pytest.ini', root / 'conftest.py']
for base in [root / 'app', root / 'addon', root / 'data-addon', root / 'docs', root / 'installer' / 'windows', root / 'scripts']:
    for path in base.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if '/build/' in '/' + rel or rel.endswith('bootstrap/payload.zip'):
            continue
        if '__pycache__' in path.parts or path.suffix in {'.pyc', '.pyo', '.exe', '.zip'}:
            continue
        selected.append(path)
selected = sorted(set(p for p in selected if p.exists()))
with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for path in selected:
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        # The bootstrap script is a source template. Put the canonical release
        # version into the distributed source archive as well as the built PE.
        if rel == 'installer/windows/bootstrap/installer.ps1':
            text = data.decode('utf-8')
            text, count = re.subn(r"(?m)^\$Version = '[^']+'$", f"$Version = '{version}'", text, count=1)
            if count != 1:
                raise SystemExit('installer.ps1 version assignment missing')
            data = text.encode('utf-8')
        info = zipfile.ZipInfo(rel, fixed)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        mode = 0o755 if path.suffix in {'.sh', '.py'} or path.name in {'BUILD-RELEASE.sh'} else 0o644
        info.external_attr = (stat.S_IFREG | mode) << 16
        zf.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
PY

cp "$SETUP_SRC" "$SETUP_OUT"
cp "$ADDON_ZIP" "$STAGE/CurseForge-Upload/$(basename "$ADDON_ZIP")"
cp "$SETUP_OUT" "$STAGE/Companion/KeystoneLens-Setup.exe"
cp "$SOURCE_ZIP" "$STAGE/Source/$(basename "$SOURCE_ZIP")"
cp "$ROOT/README-NL.md" "$STAGE/Documentation/README-NL.md"
# The release package's CHANGELOG must describe the current artifact. Keep the
# full historical changelog alongside it under an explicit HISTORY name.
cp "$RELEASE_NOTES" "$STAGE/Documentation/CHANGELOG.md"
cp "$ROOT/docs/HISTORY.md" "$STAGE/Documentation/HISTORY.md"
cp "$RELEASE_NOTES" "$STAGE/Documentation/RELEASE-NOTES.md"
cp "$AUDIT_REPORT" "$STAGE/Documentation/AUDIT-REPORT.md"
cp "$ROOT/docs/CURSEFORGE-UPLOAD.md" "$STAGE/Documentation/CURSEFORGE-UPLOAD.md"
cp "$ROOT/docs/CURSEFORGE-BESCHRIJVING.md" "$STAGE/Documentation/CURSEFORGE-PROJECT-COPY.md"
cp "$ROOT/docs/SIGNING-REQUIRED.md" "$STAGE/Documentation/SIGNING-REQUIRED.md"
cp "$ROOT/docs/DEPENDENCIES.md" "$STAGE/Documentation/DEPENDENCIES.md"
cp "$ROOT/docs/OFFICIAL-RELEASE-SOURCES.md" "$STAGE/Documentation/OFFICIAL-RELEASE-SOURCES.md"
cp "$ROOT/docs/SBOM.cdx.json" "$STAGE/Documentation/SBOM.cdx.json"
cp "$ROOT/docs/THIRD-PARTY-NOTICES.md" "$STAGE/Documentation/THIRD-PARTY-NOTICES.md"

(
  cd "$STAGE"
  sha256sum \
    "CurseForge-Upload/$(basename "$ADDON_ZIP")" \
    "Companion/KeystoneLens-Setup.exe" \
    "Source/$(basename "$SOURCE_ZIP")" \
    Documentation/* > checksums/SHA256SUMS.txt
)

python3 - "$STAGE" "$MASTER_ZIP" <<'PY'
from pathlib import Path
import stat
import sys
import zipfile

root = Path(sys.argv[1])
out = Path(sys.argv[2])
fixed = (1980, 1, 1, 0, 0, 0)
with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for path in sorted(p for p in root.rglob('*') if p.is_file()):
        rel = path.relative_to(root).as_posix()
        info = zipfile.ZipInfo(rel, fixed)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | (0o755 if path.suffix.lower() == '.exe' else 0o644)) << 16
        zf.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
PY

unzip -t "$ADDON_ZIP" >/dev/null
unzip -t "$SOURCE_ZIP" >/dev/null
unzip -t "$MASTER_ZIP" >/dev/null
( cd "$STAGE" && sha256sum -c checksums/SHA256SUMS.txt >/dev/null )

VERIFY_DIR="$(mktemp -d)"
trap 'rm -rf "$VERIFY_DIR"' EXIT
mkdir -p "$VERIFY_DIR/source" "$VERIFY_DIR/master"
unzip -q "$SOURCE_ZIP" -d "$VERIFY_DIR/source"
( cd "$VERIFY_DIR/source" && pytest -q >/dev/null && python3 -m compileall -q app/keystonelens_companion )
unzip -q "$MASTER_ZIP" -d "$VERIFY_DIR/master"
( cd "$VERIFY_DIR/master" && sha256sum -c checksums/SHA256SUMS.txt >/dev/null )
cmp -s "$SETUP_OUT" "$VERIFY_DIR/master/Companion/KeystoneLens-Setup.exe"
cmp -s "$ADDON_ZIP" "$VERIFY_DIR/master/CurseForge-Upload/$(basename "$ADDON_ZIP")"
cmp -s "$SOURCE_ZIP" "$VERIFY_DIR/master/Source/$(basename "$SOURCE_ZIP")"

grep -Fx "$VERSION" "$VERIFY_DIR/source/VERSION" >/dev/null
grep -Fx "__version__ = \"$VERSION\"" "$VERIFY_DIR/source/app/keystonelens_companion/__init__.py" >/dev/null
grep -Fx "## Version: $VERSION" "$VERIFY_DIR/source/addon/KeystoneLensBridge/KeystoneLensBridge.toc" >/dev/null
grep -Fx "\$Version = '$VERSION'" "$VERIFY_DIR/source/installer/windows/bootstrap/installer.ps1" >/dev/null

grep -F "# KeystoneLens $VERSION" "$VERIFY_DIR/master/Documentation/CHANGELOG.md" >/dev/null
grep -F "# KeystoneLens $VERSION" "$VERIFY_DIR/master/Documentation/RELEASE-NOTES.md" >/dev/null

python3 - "$ADDON_ZIP" <<'PY'
import sys, zipfile
from pathlib import PurePosixPath
with zipfile.ZipFile(sys.argv[1]) as zf:
    names=[n for n in zf.namelist() if not n.endswith('/')]
assert names, 'CurseForge ZIP is empty'
assert all(PurePosixPath(n).parts[0] == 'KeystoneLensBridge' for n in names), 'CurseForge ZIP must have exactly one addon root'
assert 'KeystoneLensBridge/KeystoneLensBridge.toc' in names, 'matching TOC missing'
assert not any(n.lower().endswith('.exe') for n in names), 'EXE must not be in CurseForge addon ZIP'
PY
rm -rf "$VERIFY_DIR"
trap - EXIT
printf '%s\n' "$MASTER_ZIP" "$ADDON_ZIP" "$SETUP_OUT" "$SOURCE_ZIP"
