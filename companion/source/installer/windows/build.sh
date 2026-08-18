#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WIN="$ROOT/installer/windows"
BUILD="$WIN/build"
PAYLOAD="$BUILD/payload"
VERSION="$(tr -d '\r\n' < "$ROOT/VERSION")"
PE_VERSION="${VERSION}.0"

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid KeystoneLens VERSION: $VERSION" >&2
  exit 1
fi
grep -Fx "__version__ = \"$VERSION\"" "$ROOT/app/keystonelens_companion/__init__.py" >/dev/null
grep -Fx "## Version: $VERSION" "$ROOT/addon/KeystoneLensBridge/KeystoneLensBridge.toc" >/dev/null

rm -rf "$BUILD"
mkdir -p "$PAYLOAD/app"

export GOOS=windows
export GOARCH=amd64
export CGO_ENABLED=0
export GO111MODULE=off
GOFLAGS=(-trimpath -ldflags=-H=windowsgui\ -s\ -w\ -buildid=)

# installer.ps1 is embedded by the Go bootstrap. Inject the canonical release
# version into a temporary build copy and always restore the checked-in source.
INSTALLER_PS1="$WIN/bootstrap/installer.ps1"
INSTALLER_BACKUP="$(mktemp)"
cp "$INSTALLER_PS1" "$INSTALLER_BACKUP"
restore_installer_source() {
  cp "$INSTALLER_BACKUP" "$INSTALLER_PS1"
  rm -f "$INSTALLER_BACKUP"
}
trap restore_installer_source EXIT
python3 - "$INSTALLER_PS1" "$VERSION" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
version = sys.argv[2]
text = path.read_text(encoding="utf-8")
updated, count = re.subn(r"(?m)^\$Version = '[^']+'$", f"$Version = '{version}'", text, count=1)
if count != 1:
    raise SystemExit("installer.ps1 must contain exactly one $Version assignment")
path.write_text(updated, encoding="utf-8")
PY

# Vet the Windows entry points as part of the real build. The bootstrap is
# vetted later because its //go:embed payload.zip is generated below.
go vet "$WIN/launcher/main.go"
go vet "$WIN/uninstall/main.go"
go vet "$WIN/wowwatcher/main.go"

go build "${GOFLAGS[@]}" -o "$PAYLOAD/KeystoneLens.exe" "$WIN/launcher/main.go"
go build "${GOFLAGS[@]}" -o "$PAYLOAD/KeystoneLens-Uninstall.exe" "$WIN/uninstall/main.go"
go build "${GOFLAGS[@]}" -o "$PAYLOAD/KeystoneLens-WoW-Watcher.exe" "$WIN/wowwatcher/main.go"
python3 "$WIN/embed_pe_resources.py" --exe "$PAYLOAD/KeystoneLens.exe" --ico "$ROOT/app/KeystoneLens.ico" --version "$VERSION" --description "KeystoneLens Companion" --original-filename "KeystoneLens.exe"
python3 "$WIN/embed_pe_resources.py" --exe "$PAYLOAD/KeystoneLens-Uninstall.exe" --ico "$ROOT/app/KeystoneLens.ico" --version "$VERSION" --description "KeystoneLens Companion Uninstaller" --original-filename "KeystoneLens-Uninstall.exe"
python3 "$WIN/embed_pe_resources.py" --exe "$PAYLOAD/KeystoneLens-WoW-Watcher.exe" --ico "$ROOT/app/KeystoneLens.ico" --version "$VERSION" --description "KeystoneLens WoW Launch Watcher" --original-filename "KeystoneLens-WoW-Watcher.exe"

cp "$ROOT/app/KeystoneLens.ico" "$PAYLOAD/KeystoneLens.ico"
cp "$WIN/requirements-runtime.txt" "$PAYLOAD/requirements-runtime.txt"
cp "$WIN/requirements-runtime.lock" "$PAYLOAD/requirements-runtime.lock"
cp "$ROOT/README-NL.md" "$PAYLOAD/README.txt"
cp -R "$ROOT/app/keystonelens_companion" "$PAYLOAD/app/keystonelens_companion"
find "$PAYLOAD" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$PAYLOAD" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

python3 "$WIN/make_payload_zip.py" --root "$PAYLOAD" --out "$BUILD/payload.zip"

cp "$BUILD/payload.zip" "$WIN/bootstrap/payload.zip"
go vet "$WIN/bootstrap/main.go"
go build "${GOFLAGS[@]}" -o "$BUILD/KeystoneLens-Setup.exe" "$WIN/bootstrap/main.go"
python3 "$WIN/embed_pe_resources.py" --exe "$BUILD/KeystoneLens-Setup.exe" --ico "$ROOT/app/KeystoneLens.ico" --version "$VERSION" --description "KeystoneLens Companion Setup" --original-filename "KeystoneLens-Setup.exe"
python3 "$WIN/verify_pe_resources.py" --exe "$PAYLOAD/KeystoneLens.exe" --version "$PE_VERSION" --description "KeystoneLens Companion"
python3 "$WIN/verify_pe_resources.py" --exe "$PAYLOAD/KeystoneLens-Uninstall.exe" --version "$PE_VERSION" --description "KeystoneLens Companion Uninstaller"
python3 "$WIN/verify_pe_resources.py" --exe "$PAYLOAD/KeystoneLens-WoW-Watcher.exe" --version "$PE_VERSION" --description "KeystoneLens WoW Launch Watcher"
python3 "$WIN/verify_pe_resources.py" --exe "$BUILD/KeystoneLens-Setup.exe" --version "$PE_VERSION" --description "KeystoneLens Companion Setup"
cp "$BUILD/payload.zip" "$WIN/bootstrap/payload.zip"

file "$BUILD/KeystoneLens-Setup.exe" "$PAYLOAD/KeystoneLens.exe" "$PAYLOAD/KeystoneLens-Uninstall.exe" "$PAYLOAD/KeystoneLens-WoW-Watcher.exe"
sha256sum "$BUILD/KeystoneLens-Setup.exe" "$PAYLOAD/KeystoneLens.exe" "$PAYLOAD/KeystoneLens-Uninstall.exe" "$PAYLOAD/KeystoneLens-WoW-Watcher.exe"
