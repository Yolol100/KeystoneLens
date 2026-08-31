#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '\r\n' < "$ROOT/VERSION")"
OUT="$ROOT/release"
ADDON_ZIP="$OUT/KeystoneLensBridge-${VERSION}-CurseForge.zip"
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
mkdir -p "$OUT"

cd "$ROOT"
pytest -q >/dev/null
python3 -m compileall -q app/keystonelens_companion
if grep -Rqi 'pyzbar' "$ROOT/app/keystonelens_companion" "$ROOT/app/requirements.txt" "$ROOT/runtime/requirements-runtime.txt" "$ROOT/runtime/requirements-runtime.lock"; then
  echo "ERROR: obsolete pyzbar runtime reference remains" >&2
  exit 1
fi

python3 - "$ROOT/addon/KeystoneLensBridge" "$ADDON_ZIP" <<'PY'
from pathlib import Path
import stat
import sys
import zipfile
source = Path(sys.argv[1]); out = Path(sys.argv[2]); fixed = (1980, 1, 1, 0, 0, 0)
with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for path in sorted(p for p in source.rglob('*') if p.is_file()):
        rel = Path(source.name) / path.relative_to(source)
        info = zipfile.ZipInfo(rel.as_posix(), fixed)
        info.compress_type = zipfile.ZIP_DEFLATED; info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        zf.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
PY

python3 - "$ROOT" "$SOURCE_ZIP" <<'PY'
from pathlib import Path
import stat
import sys
import zipfile
root = Path(sys.argv[1]); out = Path(sys.argv[2]); fixed = (1980, 1, 1, 0, 0, 0)
selected = [root / 'VERSION', root / 'README-NL.md', root / 'pytest.ini', root / 'conftest.py']
for base in [root / 'app', root / 'addon', root / 'data-addon', root / 'docs', root / 'portable', root / 'runtime', root / 'scripts']:
    for path in base.rglob('*'):
        if not path.is_file():
            continue
        if '__pycache__' in path.parts or path.suffix.lower() in {'.pyc', '.pyo', '.exe', '.zip', '.log'}:
            continue
        selected.append(path)
selected = sorted(set(p for p in selected if p.exists()))
with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for path in selected:
        rel = path.relative_to(root).as_posix()
        info = zipfile.ZipInfo(rel, fixed)
        info.compress_type = zipfile.ZIP_DEFLATED; info.create_system = 3
        mode = 0o755 if path.suffix in {'.sh', '.py'} or path.name == 'BUILD-RELEASE.sh' else 0o644
        info.external_attr = (stat.S_IFREG | mode) << 16
        zf.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
PY

unzip -t "$ADDON_ZIP" >/dev/null
unzip -t "$SOURCE_ZIP" >/dev/null
VERIFY_DIR="$(mktemp -d)"
trap 'rm -rf "$VERIFY_DIR"' EXIT
unzip -q "$SOURCE_ZIP" -d "$VERIFY_DIR"
( cd "$VERIFY_DIR" && pytest -q >/dev/null && python3 -m compileall -q app/keystonelens_companion )
grep -Fx "$VERSION" "$VERIFY_DIR/VERSION" >/dev/null
grep -Fx "__version__ = \"$VERSION\"" "$VERIFY_DIR/app/keystonelens_companion/__init__.py" >/dev/null
grep -Fx "## Version: $VERSION" "$VERIFY_DIR/addon/KeystoneLensBridge/KeystoneLensBridge.toc" >/dev/null
test -f "$VERIFY_DIR/runtime/windows-x64.json"
test -f "$VERIFY_DIR/portable/build-portable.ps1"
test ! -e "$VERIFY_DIR/installer"
rm -rf "$VERIFY_DIR"; trap - EXIT

python3 - "$ADDON_ZIP" <<'PY'
import sys, zipfile
from pathlib import PurePosixPath
with zipfile.ZipFile(sys.argv[1]) as zf:
    names=[n for n in zf.namelist() if not n.endswith('/')]
assert names
assert all(PurePosixPath(n).parts[0] == 'KeystoneLensBridge' for n in names)
assert 'KeystoneLensBridge/KeystoneLensBridge.toc' in names
assert not any(n.lower().endswith('.exe') for n in names)
PY
printf '%s\n' "$ADDON_ZIP" "$SOURCE_ZIP"
