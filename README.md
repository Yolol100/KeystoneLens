# KeystoneLens

KeystoneLens combines a World of Warcraft Retail bridge add-on with a local Windows Companion for Mythic+ recruitment analysis.

## Required components

- `addon/KeystoneLensBridge/` — WoW add-on. It captures/encodes local data and adds Companion information to supported tooltips.
- `companion/source/` — Windows Companion source and the files required to build the portable Companion package.

Both components are part of the product and are intentionally kept.

## Bridge installation

Place `addon/KeystoneLensBridge/` in `World of Warcraft/_retail_/Interface/AddOns/` as `KeystoneLensBridge`.

Optional integrations include Raider.IO, KeystoneLens Companion Data and LibKeystone.

## Windows Companion

The Companion source is in `companion/source/app/`. The portable package is assembled with `companion/source/portable/build-portable.ps1`, which uses the pinned runtime contract and `scripts/make_deterministic_zip.py`.

The resulting portable package starts with `START-COMPANION.cmd`.

## Repository structure

This repository intentionally keeps only product runtime/source files, the small amount of build logic required for the portable Companion, required third-party notices, licensing information and this README.

- `addon/KeystoneLensBridge/` — Bridge runtime
- `companion/source/app/` — Companion runtime source
- `companion/source/data-addon/` — generated Companion Data add-on source
- `companion/source/portable/` — portable launcher and required builder
- `companion/source/runtime/` — pinned Windows runtime/dependency contract
- `companion/source/scripts/make_deterministic_zip.py` — required portable ZIP builder helper
- `companion/source/docs/THIRD-PARTY-NOTICES.md` — required third-party notices

## License

See `LICENSE-SCOPE.md` and the license/notice files inside the individual components.
