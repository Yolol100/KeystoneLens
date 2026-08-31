# Third-party notices — KeystoneLens Companion

KeystoneLens Companion uses the following third-party runtime components from their official distributions:

- CPython 3.13.15 — Python Software Foundation License Version 2.
- Requests 2.34.2 — Apache-2.0.
- Pillow 12.3.0 — MIT-CMU.
- zxing-cpp 3.1.1 — Apache-2.0.
- charset-normalizer 3.4.9 — MIT.
- idna 3.18 — BSD-3-Clause.
- urllib3 2.7.0 — MIT.
- certifi 2026.7.22 — MPL-2.0.

The package versions and accepted wheel hashes are locked in `installer/windows/requirements-runtime.lock`. Package metadata remains alongside each Python distribution/package and is the authoritative source for its full license text and notices.

The install-free portable ZIP also carries this notice. Its private CPython runtime is staged from the same SHA-256-verified official Python distribution used by the installer, and its Python packages are installed from the same hash-locked runtime dependency set.
