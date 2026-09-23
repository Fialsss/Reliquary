# Third-party code and tools

## R6-parser

- Source: https://github.com/TrueShadow01/R6-parser
- Vendored in `engine/r6parser/src`, unmodified, from commit `f9531de198b88d248171709a5f5740053e51bddd` (2026-09-20)
- License: GNU GPL-3.0. Reliquary as a whole is distributed under the same license (see `LICENSE`).

## DepotDownloader

- Source: https://github.com/SteamRE/DepotDownloader
- Not included in this repository. Reliquary downloads the official `DepotDownloader_3.4.0` Windows x64 release on first use and runs it as a separate program.
- License: GNU GPL-2.0.

## Fonts and libraries

Inter and JetBrains Mono (SIL Open Font License 1.1, via Fontsource), React (MIT), Lucide icons (ISC), Electron (MIT). Versions are listed in `package.json`.

## Not included

- The Oodle runtime (`oo2core_*_win64.dll`) is proprietary software by RAD Game Tools / Epic Games. It is never bundled; users point Reliquary to a copy they are licensed to use.
- No Rainbow Six Siege game files, textures or models are part of this repository. Season covers in the app are generated at runtime.
