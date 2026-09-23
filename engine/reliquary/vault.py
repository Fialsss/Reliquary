"""The Vault: past Siege builds from Steam's depots, one archive at a time.

Steam still serves every manifest ever published for depot 359551. With the
manifest ID of a season, DepotDownloader can list that build's files and fetch
only the archives you pick, instead of a 60+ GB game. The account signing in
must own Rainbow Six Siege on Steam.
"""
from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path

from . import env, settings
from .rpc import Failure, emit, method

APP, DEPOT = 359550, 359551
TOOL_URL = ("https://github.com/SteamRE/DepotDownloader/releases/download/"
            "DepotDownloader_3.4.0/DepotDownloader-windows-x64.zip")
SEASONS = json.loads((Path(__file__).parent / "data" / "seasons.json").read_text(encoding="utf-8"))
MARKER = ".reliquary.json"

PROGRESS = re.compile(r"^\s*(\d{1,3}(?:\.\d+)?)%\s+(.+)$")
REMEMBER = re.compile(r"-username (\S+) -remember-password")
MANIFEST_ROW = re.compile(r"^\s*(\d+)\s+(\d+)\s+([0-9a-f]{40})\s+(\d+)\s+(.+?)\s*$")
AUTH_TROUBLE = re.compile(r"(?i)password|logon|login|access ?denied|expired|two-factor|auth code")
QR_DARK = set("█▀▄")

_job_lock = threading.Lock()
_active: subprocess.Popen | None = None
_cancelled = False


# ------------------------------------------------------------------ seasons

def _seasons() -> list[dict]:
    out = []
    for year, entries in SEASONS.items():
        for key, entry in entries.items():
            if entry["name"] == "T.B.A":
                continue
            patches = [
                {"patch": p, "date": v["date"], "manifest": str(v[str(DEPOT)])}
                for p, v in entry.items() if p != "name" and str(DEPOT) in v
            ]
            if patches:
                out.append({"id": f"{year}{key}", "year": int(year[1:]), "season": int(key[1:]),
                            "name": entry["name"], "patches": patches})
    return out


def _library(season: str, manifest: str) -> Path:
    return Path(settings.load()["library"]) / season / manifest


def _completed(folder: Path) -> set[str]:
    try:
        return set(json.loads((folder / MARKER).read_text(encoding="utf-8"))["files"])
    except (OSError, ValueError, KeyError):
        return set()


@method("vault.seasons")
def seasons() -> list[dict]:
    result = []
    for season in _seasons():
        local = sum(len(_completed(_library(season["id"], p["manifest"]))) for p in season["patches"])
        result.append({**season, "local": local})
    return result


# --------------------------------------------------------------- the tool

def _ensure_tool() -> Path:
    tool = env.depot_tool()
    if tool.is_file():
        return tool
    emit("vault.status", {"key": "tool"})
    tool.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(TOOL_URL, timeout=120) as response:
        zipfile.ZipFile(io.BytesIO(response.read())).extractall(tool.parent)
    if not tool.is_file():
        raise Failure("DepotDownloader.exe is missing from the downloaded release")
    return tool


@contextmanager
def _job():
    if not _job_lock.acquire(blocking=False):
        raise Failure("Another Steam job is already running")
    try:
        yield
    finally:
        _job_lock.release()


def _decode(raw: bytes) -> str:
    # .NET writes UTF-8 or the OEM code page depending on the console; the QR
    # blocks (█ ▀ ▄) exist in both.
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp437", errors="replace")


def qr_matrix(lines: list[str]) -> list[str]:
    """Turn DepotDownloader's text QR into rows of '0'/'1' modules."""
    rows = [line.rstrip() for line in lines if set(line) & QR_DARK]
    if not rows:
        return []
    left = min(len(r) - len(r.lstrip(" ")) for r in rows)
    rows = [r[left:] for r in rows]
    if any(c in "▀▄" for r in rows for c in r):
        # half blocks: one character per module, two module rows per line
        width = max(len(r) for r in rows)
        rows = [r.ljust(width) for r in rows]
        matrix = []
        for r in rows:
            matrix.append("".join("1" if c in "█▀" else "0" for c in r))
            matrix.append("".join("1" if c in "█▄" else "0" for c in r))
        while matrix and "1" not in matrix[-1]:
            matrix.pop()
        return matrix
    # full blocks: two characters per module, one module row per line
    width = max(len(r) for r in rows)
    width += width % 2
    return ["".join("1" if r.ljust(width)[i] == "█" else "0" for i in range(0, width, 2)) for r in rows]


def _run(args: list[str]) -> list[str]:
    """Run DepotDownloader, streaming QR, progress and log lines as events."""
    global _active, _cancelled
    user = settings.load()["steam_user"]
    auth = ["-username", user, "-remember-password"] if user else ["-qr", "-remember-password"]
    tool = _ensure_tool()
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    _cancelled = False
    process = subprocess.Popen(
        [str(tool), "-app", str(APP), "-depot", str(DEPOT), *auth, *args],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        cwd=tool.parent, creationflags=flags,
    )
    _active = process
    log: list[str] = []
    qr: list[str] | None = None
    emit("vault.status", {"key": "connecting"})
    for raw in process.stdout:
        line = _decode(raw).rstrip("\r\n")
        log.append(line)
        if qr is not None:
            if set(line) & QR_DARK:
                qr.append(line)
                continue
            if qr:  # the first quiet line after the code closes it
                emit("vault.qr", {"matrix": qr_matrix(qr)})
                qr = None
            continue
        if "QR code" in line:
            qr = []
            emit("vault.status", {"key": "scan"})
            continue
        if match := PROGRESS.match(line):
            emit("vault.progress", {"percent": float(match[1]), "file": Path(match[2]).name})
            continue
        if match := REMEMBER.search(line):
            settings.update(steam_user=match[1])
            emit("vault.signed_in", {"user": match[1]})
        if line.strip():
            emit("vault.log", line.strip())
    code = process.wait()
    _active = None
    if _cancelled:
        raise Failure("Cancelled")
    if code != 0:
        text = "\n".join(log)
        if "is not available from this account" in text:
            raise Failure("This Steam account doesn't own Rainbow Six Siege")
        if user and AUTH_TROUBLE.search(text):
            # the remembered login went stale: forget it and sign in again by QR
            settings.update(steam_user="")
            emit("vault.status", {"key": "relogin"})
            return _run(args)
        last = next((l.strip() for l in reversed(log) if l.strip()), f"exit code {code}")
        raise Failure(f"DepotDownloader failed: {last}")
    return log


# ------------------------------------------------------------------ methods

def _category(name: str) -> str:
    lower = name.lower()
    if "bnk_textures" in lower:
        return "textures"
    if "bnk_mesh" in lower:
        return "meshes"
    return "other" if "_bnk_" in lower else "data"


def parse_manifest(text: str) -> list[dict]:
    files = []
    for line in text.splitlines():
        match = MANIFEST_ROW.match(line)
        if not match or int(match[4]) & 0x40:  # 0x40 = directory
            continue
        name = match[5]
        if name.endswith((".forge", ".depgraphbin")):
            files.append({"name": name, "size": int(match[1]), "category": _category(name)})
    return sorted(files, key=lambda f: f["name"])


@method("vault.files")
def files(season: str, manifest: str) -> list[dict]:
    folder = settings.HOME / "manifests"
    cache = folder / f"manifest_{DEPOT}_{manifest}.txt"
    if not cache.is_file():
        with _job():
            scratch = folder / f"tmp-{manifest}"
            _run(["-manifest", manifest, "-manifest-only", "-dir", str(scratch)])
            produced = next(scratch.rglob(f"manifest_{DEPOT}_*.txt"), None)
            if produced is None:
                raise Failure("DepotDownloader finished without writing the manifest")
            produced.replace(cache)
            shutil.rmtree(scratch, ignore_errors=True)
    local = _completed(_library(season, manifest))
    return [{**f, "local": f["name"] in local} for f in parse_manifest(cache.read_text(encoding="utf-8"))]


@method("vault.download")
def download(season: str, manifest: str, files: list[str]) -> dict:
    if not files:
        raise Failure("Pick at least one archive")
    target = _library(season, manifest)
    target.mkdir(parents=True, exist_ok=True)
    with _job():
        filelist = settings.HOME / "manifests" / f"filelist-{manifest}.txt"
        filelist.parent.mkdir(parents=True, exist_ok=True)
        filelist.write_text("\n".join(files), encoding="utf-8")
        _run(["-manifest", manifest, "-filelist", str(filelist), "-validate", "-dir", str(target)])
    done = sorted(_completed(target) | set(files))
    (target / MARKER).write_text(json.dumps({"season": season, "manifest": manifest, "files": done}, indent=1),
                                 encoding="utf-8")
    emit("vault.done", {"season": season, "manifest": manifest})
    return {"dir": str(target), "files": done}


@method("vault.cancel")
def cancel() -> bool:
    global _cancelled
    if _active is not None and _active.poll() is None:
        _cancelled = True
        _active.kill()
        return True
    return False


@method("vault.signout")
def signout() -> dict:
    # DepotDownloader keeps the refresh token in IsolatedStorage next to the exe
    shutil.rmtree(env.depot_tool().parent / "IsolatedStorage", ignore_errors=True)
    return settings.update(steam_user="")


@method("vault.folder")
def folder(season: str, manifest: str) -> str:
    return str(_library(season, manifest))
