"""Find the game, Blender, Oodle and the Steam depot tool on this machine."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from . import settings
from .rpc import method

GAME_FOLDER = "Tom Clancy's Rainbow Six Siege"


def _is_game(path: Path) -> bool:
    return (path / "datapc64.forge").is_file()


def _ubisoft_installs() -> list[Path]:
    if sys.platform != "win32":
        return []
    import winreg
    found = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs")
    except OSError:
        return []
    index = 0
    while True:
        try:
            name = winreg.EnumKey(root, index)
        except OSError:
            break
        index += 1
        try:
            with winreg.OpenKey(root, name) as key:
                found.append(Path(winreg.QueryValueEx(key, "InstallDir")[0]))
        except OSError:
            pass
    return found


def _steam_libraries() -> list[Path]:
    steam = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam"
    libraries = [steam]
    try:
        vdf = (steam / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
        libraries += [Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', vdf)]
    except OSError:
        pass
    return [lib / "steamapps" / "common" / GAME_FOLDER for lib in libraries]


def find_game() -> Path | None:
    configured = settings.load()["game_dir"]
    candidates = ([Path(configured)] if configured else []) + _ubisoft_installs() + _steam_libraries()
    return next((c for c in candidates if _is_game(c)), None)


def find_blender() -> tuple[Path | None, str]:
    configured = settings.load()["blender"]
    if configured and Path(configured).is_file():
        return Path(configured), _blender_version(Path(configured))
    root = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Blender Foundation"
    found = sorted(root.glob("*/blender.exe"), key=lambda p: _version_key(_blender_version(p)), reverse=True)
    return (found[0], _blender_version(found[0])) if found else (None, "")


def _blender_version(exe: Path) -> str:
    match = re.search(r"(\d+\.\d+)", exe.parent.name)
    return match.group(1) if match else ""


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version.split(".") if x.isdigit())


def find_oodle() -> Path | None:
    for value in (settings.load()["oodle"], os.environ.get("R6_OODLE_DLL", "")):
        if value and Path(value).is_file():
            return Path(value)
    return None


def depot_tool() -> Path:
    return settings.HOME / "tools" / "DepotDownloader" / "DepotDownloader.exe"


# DepotDownloader keeps its Steam login in .NET IsolatedStorage, one Url.<hash> folder per exe location.
ISOLATED = Path(os.environ.get("LOCALAPPDATA", "")) / "IsolatedStorage"
STORE_NOTE = settings.HOME / "steam-store.txt"


def saved_logins() -> dict[Path, float]:
    return {p: p.stat().st_mtime for p in ISOLATED.glob("*/*/Url.*/AssemFiles/account.config")}


@method("env.status")
def status() -> dict:
    game = find_game()
    blender, version = find_blender()
    oodle = find_oodle()
    tool = depot_tool()
    return {
        "game": {"ok": bool(game), "path": str(game or "")},
        "blender": {"ok": bool(blender), "path": str(blender or ""), "version": version},
        "oodle": {"ok": bool(oodle), "path": str(oodle or "")},
        "depot": {"ok": tool.is_file(), "path": str(tool)},
        "home": str(settings.HOME),
    }
