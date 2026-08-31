Portable CI contract:
- build on windows-2025;
- stage the canonical Python 3.13.15 runtime locally;
- install the hash-locked runtime packages into the portable folder;
- verify the staged runtime;
- create and re-extract the ZIP;
- verify the extracted runtime again;
- fail if the package contains KeystoneLens Setup/installed launcher executables.
