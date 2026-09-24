<div align="center">
  <img src="resources/icon.png" width="112" alt="Reliquary" />
  <h1>Reliquary</h1>
  <p>
    <b>Rainbow Six Siege, straight into Blender.</b><br />
    Every operator, weapon skin and charm in the game, with its own pictures, packed into one ready-to-use .blend. Retired seasons from Steam, one archive at a time.
  </p>
  <p>
    <img src="https://img.shields.io/badge/Windows-0b0b0d?style=for-the-badge&logo=windows&logoColor=white" alt="Windows" />
    <img src="https://img.shields.io/badge/early%20preview-ffb347?style=for-the-badge" alt="Early preview" />
    <img src="https://img.shields.io/badge/GPL--3.0%20%2B%20attribution-3ddc97?style=for-the-badge" alt="GPL-3.0 with attribution" />
    <a href="https://ko-fi.com/fialss"><img src="https://img.shields.io/badge/Ko--fi-support-ff5e5b?style=for-the-badge&logo=kofi&logoColor=white" alt="Support on Ko-fi" /></a>
  </p>
  <p><a href="README.it.md">Leggi in italiano</a></p>
  <img src="docs/reliquary.gif" width="820" alt="Reliquary: operators, weapon skins and charms" />
</div>

> [!WARNING]
> Reliquary is still in development: expect rough edges. The Vault and Operators work end to end; the Armory page is being built. It is a fan project, not affiliated with, endorsed by or sponsored by Ubisoft or Valve.

## A look around

<table>
  <tr>
    <td width="50%"><img src="docs/operators.png" alt="Operators" /></td>
    <td width="50%"><img src="docs/skins.png" alt="Weapon skins" /></td>
  </tr>
  <tr>
    <td><b>Operators.</b> The game's own portraits and emblems, attackers and defenders apart.</td>
    <td><b>Every weapon skin.</b> The whole catalog for each weapon, with the game's previews: universal skins and the weapon's own.</td>
  </tr>
  <tr>
    <td><img src="docs/charms.png" alt="Charms" /></td>
    <td><img src="docs/ranked.png" alt="Ranked charms" /></td>
  </tr>
  <tr>
    <td><b>All 2,489 charms,</b> season by season, with their icons, rarity and a search.</td>
    <td><b>Filters.</b> By season, kind (ranked, battle pass, esports, chibi, events) and rank, from Copper to Champion.</td>
  </tr>
  <tr>
    <td><img src="docs/vault.png" alt="The Vault" /></td>
    <td><img src="docs/home.png" alt="Home" /></td>
  </tr>
  <tr>
    <td><b>The Vault.</b> All 43 seasons still on Steam, downloaded one archive at a time.</td>
    <td><b>Home.</b> Your workspace at a glance: Steam, the game, Blender, Oodle.</td>
  </tr>
</table>

## Download

Grab the latest build from **[Releases](https://github.com/Fialsss/Reliquary/releases/latest)**:

- `Reliquary-Setup-x.y.z.exe`: installer with Start menu and desktop shortcuts
- `Reliquary-x.y.z-portable.exe`: a single file, no installation

Both include everything they need, so you don't have to install Python or Node. Windows 10/11 64-bit.

The builds are not code-signed yet, so Windows SmartScreen may show *"Windows protected your PC"* the first time. Click **More info → Run anyway**. The source of every build is this repository.

## Getting started

The app opens with a guided tour the first time, and the **?** button in the top bar brings it back whenever you need it. In short:

1. **Sign in with Steam.** Press *Sign in* at the top right, then either scan the QR code with the Steam app on your phone (shield icon → *Scan a QR code*) or switch to *Password* and type your account name and password; Steam Guard codes and phone approvals are asked right in the window. The account must own Rainbow Six Siege on Steam. Your Steam name and picture then appear in the top bar.
2. **Open the Vault** and pick a season. Every card is the original build released at that time.
3. **Load the file list.** Reliquary asks Steam which archives that build contains, with their sizes.
4. **Tick what you need.** *Data* archives are small (tables, materials, references), *Textures* are 2 to 9 GB each, *Meshes* are the 3D models. For a first test, pick a small file.
5. **Download.** It runs in the background, with its progress in the top bar. Files land in your Library folder, which you can open from the account menu.

Then **Open this build** on the same page: Reliquary reads a downloaded texture archive and saves its textures as PNG, filtered by size and kind (color, normal, specular, masks), with the disk space shown before anything is written. Checked on a full Y2S3 Blood Orchid build: retired weapon skins and uniforms come out intact. This works for builds in the older Forge format (Zstandard, v29 and nearby); meshes and the current format are next.

## What it does

**The Vault: retired content, one archive at a time.** Steam still serves every Siege build published since 2015. Reliquary lists all 43 seasons, from Y1S0 Vanilla to Y11S2, asks Steam for the file list of the build you pick, and downloads only the archives you tick. You don't need the whole 60+ GB game. You sign in once by scanning a QR code with the Steam mobile app, right inside the window, and your Steam profile shows up in the top bar. Downloads keep running while you use the rest of the app.

This is how the original **Glacier for the 552 Commando (Y5S4)** was recovered. It no longer exists in the live game. Its textures sat in a single 9 GB archive of the Neon Dawn build.

**Workspace detection.** Reliquary finds the game through Ubisoft Connect or your Steam libraries, finds Blender, and tells you what is missing.

**Operators → Blender pack.** The roster comes with the game's own portraits and emblems, split into attackers and defenders. Pick an operator, then what goes in the pack: uniforms and headgear (with their names and seasons; Elite sets have the gold background), the operator's weapons with their magazine and **every skin the game has for them**, universal and weapon-only, camo patterns included, the sights, and **every charm in the game**, grouped by season and filterable by kind and rank. It all comes from the game itself: its shop catalog (names, seasons, rarity) and its own pictures (the 440x144 skin previews and the charm icons you see in the game). **Create Blender pack** exports everything and has Blender build one `.blend`: a collection per uniform, headgear, weapon skin and sight, ready to switch on and off, with weapons, sights and charms next to the operator. Uniforms, headgear and weapons come from your install (the bundled [R6-parser](https://github.com/TrueShadow01/R6-parser) reads them; its add-on rebuilds the Siege materials). Weapon skins and charms come from two places: the ones the game installed with itself (Black Ice and the other skins in its mtx archives) and the ones it streamed to your PC. Both can go in a pack; the others are marked *To download* until you look at them once in the game (Armory or Shop). The first time, **Prepare** gets everything ready under one progress bar: the asset index, the game's downloads, every weapon and every picture (several minutes, about 550 MB). After that every page opens at once, and after a game update it redoes only what changed.

**Armory (in development).** This is the weapon → skin → Blender pipeline. Skins are resolved through the game's own references (cosmetic record → material selection → material bundle → texture UIDs), never guessed from how they look. Every skin will carry that chain as proof.

## Status

| Area | State |
| --- | --- |
| Vault: season list, Steam QR sign-in, file list, selective download, cancel, resume | Working |
| Workspace detection (Ubisoft Connect, Steam libraries, Blender) | Working |
| Operator Blender pack: uniforms and headgear, weapons with magazine, weapon skins (camo patterns too), sights and charms in one `.blend` | Working (78 operators on the current build; checked in Blender 5.2). A few sights (Holo A) can't be exported yet |
| The game's whole catalog with its own pictures: every weapon skin (4,765) and charm (2,489), with seasons, rarity and ranks | Working. Exporting needs the item installed or downloaded by the game; the rest is marked *To download* |
| Weapons, attachments, skins, charms, Blender scene with skin switcher | Method proven by hand on the 552 Commando; app integration next |
| Installer and portable build, no dependencies | Working |
| Steam sign-in: QR code, or account name and password with Steam Guard | Working |
| Reading current game files without Oodle (bundled open-source ooz) | Working |
| Disk space: see and delete downloaded archives and caches | Working |
| Old builds: textures of downloaded archives to PNG (Forge v29, Zstandard) | Working (checked on Y2S3); meshes next |

## Requirements

- Windows 10 or 11, 64-bit
- **For the Vault:** a Steam account that owns Rainbow Six Siege
- [Blender](https://www.blender.org) for exports

## Run from source

You need [Node.js](https://nodejs.org) 20+ and [Python](https://www.python.org) 3.10+.

```powershell
git clone https://github.com/Fialsss/Reliquary.git
cd Reliquary
npm install
py -3 -m pip install -r engine/requirements.txt
npm run dev
```

To use a Python that is not on `PATH`, set `RELIQUARY_PYTHON` to its full path.

To build the installer and the portable exe into `dist/`, run `py -3 -m pip install pyinstaller`, then `npm run dist`. Building needs the Visual Studio C++ tools, which compile the bundled ooz decoder (`engine/native/ooz`).

<details>
<summary>Troubleshooting</summary>

- **The app starts as plain Node and fails with `Cannot read properties of undefined (reading 'handle')`.** Something set `ELECTRON_RUN_AS_NODE=1` in your environment (some editor extensions do). Clear it: `Remove-Item Env:ELECTRON_RUN_AS_NODE`.
- **"This Steam account doesn't own Rainbow Six Siege".** Steam only serves depots to accounts that own the app. Owning Siege on Ubisoft Connect alone is not enough for the Vault.
- **The saved Steam login expired.** Reliquary notices, forgets it and shows a fresh QR code.

</details>

## How it works

```text
Electron + React (src/)  ── JSON lines over stdio ──  Python engine (engine/reliquary)
                                                        ├─ vault.py      DepotDownloader: QR, manifests, downloads
                                                        ├─ env.py        game / Blender / Oodle detection
                                                        ├─ operators.py  roster, pictures and packs via the vendored R6-parser
                                                        ├─ catalog.py    the game's shop catalog: every skin and charm
                                                        ├─ dcache.py     the game's download cache (streamed skins and charms)
                                                        └─ r6parser/     Forge archives, meshes, textures (GPL-3.0)
```

The window never talks to the network or the disk directly. Every action is a request to the engine, and long jobs stream their progress back as events. The Vault drives [DepotDownloader](https://github.com/SteamRE/DepotDownloader) with the manifest ID of each season (`engine/reliquary/data/seasons.json`). DepotDownloader is fetched from its official release on first use.

## What Reliquary does not do

- It ships **no game files**. Everything is read from your install, or downloaded from Steam with your own account.
- It does not bundle Oodle, which is proprietary. It ships **ooz** instead, an open-source decoder for the same compression, checked to give identical output on the current game files.
- It doesn't ship season artwork: the app loads it at runtime from the Rainbow Six Fandom wiki. The screenshots in this README show that artwork, © Ubisoft.
- Extracted assets belong to Ubisoft. Use them for personal renders and fan art, and don't redistribute them.

## Support

Reliquary is free and always will be. If it brought back some good memories, you can buy me a coffee:

<a href="https://ko-fi.com/fialss"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support me on Ko-fi" /></a>

## Credits

- [R6-parser](https://github.com/TrueShadow01/R6-parser) by TrueShadow01: the Forge reader in `engine/r6parser` (GPL-3.0)
- [DepotDownloader](https://github.com/SteamRE/DepotDownloader) by SteamRE (GPL-2.0), downloaded at runtime
- [RainbowForge](https://github.com/parzivail/RainbowForge) by parzivail, whose format research made all of this possible

See [THIRD_PARTY.md](THIRD_PARTY.md) for details.

## License and credits

Reliquary is Copyright (C) 2026 **Fialsss**, released under [GPL-3.0](LICENSE) with one additional term (section 7(b)): copies and derivative works must keep the notice **"Based on Reliquary by Fialsss — https://github.com/Fialsss/Reliquary"** in their documentation and in their credits or about screen. Details in [NOTICE.md](NOTICE.md).

 Rainbow Six Siege is a trademark of Ubisoft Entertainment. This project is not affiliated with or endorsed by Ubisoft or Valve.
