Portable CI contract:
- build on windows-2025;
- read one canonical Python runtime manifest from runtime/windows/python-runtime.json;
- verify the downloaded runtime SHA-256 before staging;
- install only the hash-locked runtime packages into the portable folder;
- verify the staged runtime and the full Companion import;
- create and re-extract the deterministic ZIP;
- verify the extracted runtime again;
- require the portable single-instance guard and visible nonzero-startup failure path;
- fail if the package contains KeystoneLens Setup/installed launcher/uninstaller/watcher executables.
