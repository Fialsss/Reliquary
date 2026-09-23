# Third-party code and tools

## R6-parser

- Source: https://github.com/TrueShadow01/R6-parser
- Vendored in `engine/r6parser/src`, unmodified, from commit `20b4cae8fc4d3c3e65d0c6f0fb52a605bae795ca` (2026-09-22)
- License: GNU GPL-3.0. Reliquary as a whole is distributed under the same license (see `LICENSE`).

## ooz (Kraken / Leviathan decoder)

- Source: https://github.com/powzix/ooz, commit `05038060aa68f9187ae9923b2388ca8db40e58d1`
- Vendored in `engine/native/ooz`: `kraken.cpp` (GPL-3.0-or-later, Copyright (C) 2016 Powzix) with its `stdafx.h` and `targetver.h`.
- Modified for Reliquary: two stack arrays in `Kraken_DecodeMultiArray` enlarged from 32 to 64 entries (current Oodle Leviathan streams use more than 32 arrays and overflowed them). Reliquary adds `ooz_export.cpp`, which exports the decoder under Oodle's `OodleLZ_Decompress` signature.
- The LZNA and Bitknit decoders of ooz are not included (their files carry no license, and Siege archives don't use them).
- Built into `ooz.dll` by `engine/native/ooz/build.bat` and shipped in the release builds. Checked against Oodle on 3,490 chunks (411 MB) of the current game: identical output.

## DepotDownloader

- Source: https://github.com/SteamRE/DepotDownloader
- Not included in this repository. Reliquary downloads the official `DepotDownloader_3.4.0` Windows x64 release on first use and runs it as a separate program.
- License: GNU GPL-2.0.

## Bundled in the release builds

The installer and the portable exe carry the engine frozen with [PyInstaller](https://pyinstaller.org) (GPL-2.0 with the bootloader exception), which includes the Python runtime (PSF License) and [Pillow](https://python-pillow.org) (MIT-CMU). Electron and Chromium ship with their own license files inside the app folder.

## Fonts and libraries

Inter and JetBrains Mono (SIL Open Font License 1.1, via Fontsource), React (MIT), Lucide icons (ISC), Electron (MIT). Versions are listed in `package.json`.

## Season artwork

Season covers and galleries are looked up at runtime on the [Rainbow Six Fandom wiki](https://rainbowsix.fandom.com) and loaded by the window like any web page would. The images belong to Ubisoft. The release builds don't include them; the screenshots in the README show them for illustration. Offline, the app shows generated covers instead.

## Not included

- The Oodle runtime (`oo2core_*_win64.dll`) is proprietary software by RAD Game Tools / Epic Games. It is never bundled: Reliquary uses ooz instead, and users who own a copy of Oodle can still choose it in Settings.
- No Rainbow Six Siege game files, textures or models are part of this repository. Season covers in the app are generated at runtime.
