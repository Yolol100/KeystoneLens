#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WIN="$ROOT/installer/windows"
BUILD="$WIN/build"
PAYLOAD="$BUILD/payload"

rm -rf "$BUILD"
mkdir -p "$PAYLOAD/app"

export GOOS=windows
export GOARCH=amd64
export CGO_ENABLED=0
export GO111MODULE=off
GOFLAGS=(-trimpath -ldflags=-H=windowsgui\ -s\ -w\ -buildid=)

# Vet the Windows entry points as part of the real build. The bootstrap is
# vetted later because its //go:embed payload.zip is generated below.
go vet "$WIN/launcher/main.go"
go vet "$WIN/uninstall/main.go"
go vet "$WIN/wowwatcher/main.go"

go build "${GOFLAGS[@]}" -o "$PAYLOAD/KeystoneLens.exe" "$WIN/launcher/main.go"
go build "${GOFLAGS[@]}" -o "$PAYLOAD/KeystoneLens-Uninstall.exe" "$WIN/uninstall/main.go"
go build "${GOFLAGS[@]}" -o "$PAYLOAD/KeystoneLens-WoW-Watcher.exe" "$WIN/wowwatcher/main.go"
python3 "$WIN/embed_pe_resources.py" --exe "$PAYLOAD/KeystoneLens.exe" --ico "$ROOT/app/KeystoneLens.ico" --version 0.12.7 --description "KeystoneLens Companion" --original-filename "KeystoneLens.exe"
python3 "$WIN/embed_pe_resources.py" --exe "$PAYLOAD/KeystoneLens-Uninstall.exe" --ico "$ROOT/app/KeystoneLens.ico" --version 0.12.7 --description "KeystoneLens Companion Uninstaller" --original-filename "KeystoneLens-Uninstall.exe"
python3 "$WIN/embed_pe_resources.py" --exe "$PAYLOAD/KeystoneLens-WoW-Watcher.exe" --ico "$ROOT/app/KeystoneLens.ico" --version 0.12.7 --description "KeystoneLens WoW Launch Watcher" --original-filename "KeystoneLens-WoW-Watcher.exe"

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
python3 "$WIN/embed_pe_resources.py" --exe "$BUILD/KeystoneLens-Setup.exe" --ico "$ROOT/app/KeystoneLens.ico" --version 0.12.7 --description "KeystoneLens Companion Setup" --original-filename "KeystoneLens-Setup.exe"
python3 "$WIN/verify_pe_resources.py" --exe "$PAYLOAD/KeystoneLens.exe" --version 0.12.7.0 --description "KeystoneLens Companion"
python3 "$WIN/verify_pe_resources.py" --exe "$PAYLOAD/KeystoneLens-Uninstall.exe" --version 0.12.7.0 --description "KeystoneLens Companion Uninstaller"
python3 "$WIN/verify_pe_resources.py" --exe "$PAYLOAD/KeystoneLens-WoW-Watcher.exe" --version 0.12.7.0 --description "KeystoneLens WoW Launch Watcher"
python3 "$WIN/verify_pe_resources.py" --exe "$BUILD/KeystoneLens-Setup.exe" --version 0.12.7.0 --description "KeystoneLens Companion Setup"
cp "$BUILD/payload.zip" "$WIN/bootstrap/payload.zip"

file "$BUILD/KeystoneLens-Setup.exe" "$PAYLOAD/KeystoneLens.exe" "$PAYLOAD/KeystoneLens-Uninstall.exe" "$PAYLOAD/KeystoneLens-WoW-Watcher.exe"
sha256sum "$BUILD/KeystoneLens-Setup.exe" "$PAYLOAD/KeystoneLens.exe" "$PAYLOAD/KeystoneLens-Uninstall.exe" "$PAYLOAD/KeystoneLens-WoW-Watcher.exe"
