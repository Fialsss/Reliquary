"""The Vault: past Siege builds from Steam's depots, one archive at a time.

Steam still serves every manifest ever published for depot 359551. With the
manifest ID of a season, DepotDownloader can list that build's files and fetch
only the archives you pick, instead of a 60+ GB game. The account signing in
must own Rainbow Six Siege on Steam.
"""
from __future__ import annotations

import io
import json
import os
import queue
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
LICENSES = re.compile(r"Got \d+ licenses for account")  # logged on: the rest of the run is the actual job
MANIFEST_ROW = re.compile(r"^\s*(\d+)\s+(\d+)\s+([0-9a-f]{40})\s+(\d+)\s+(.+?)\s*$")
AUTH_TROUBLE = re.compile(r"(?i)password|logon|login|access ?denied|expired|two-factor|auth code")
QR_DARK = set("█▀▄")

_job_lock = threading.Lock()
_tool_lock = threading.Lock()
_active: subprocess.Popen | None = None
_cancelled = False
_codes: queue.Queue[str] = queue.Queue()  # Steam Guard codes typed in the window, handed to DepotDownloader


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

def _ensure_tool(announce: bool = True) -> Path:
    tool = env.depot_tool()
    if announce and not tool.is_file():
        emit("steam.status", {"key": "tool"})
    with _tool_lock:  # a sign-in started during the startup prefetch waits for that same download
        if tool.is_file():
            return tool
        part = tool.parent / "download.part"  # unpacked aside first: a cut download never looks installed
        shutil.rmtree(part, ignore_errors=True)
        with urllib.request.urlopen(TOOL_URL, timeout=120) as response:
            zipfile.ZipFile(io.BytesIO(response.read())).extractall(part)
        for item in part.iterdir():
            os.replace(item, tool.parent / item.name)
        part.rmdir()
    if not tool.is_file():
        raise Failure("DepotDownloader.exe is missing from the downloaded release")
    return tool


def prefetch_tool() -> None:
    """Fetch DepotDownloader (33 MB) in the background at startup, so signing in never waits for it."""
    try:
        _ensure_tool(announce=False)
    except (OSError, Failure, zipfile.BadZipFile):
        pass  # offline: the first Steam job tries again and reports it


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


def prompt_kind(text: str) -> str | None:
    """Which question DepotDownloader is asking, if the unfinished line is one (they end without a newline)."""
    lower = text.lower()
    if "enter account password" in lower:
        return "password"
    if "auth code from your authenticator app" in lower:
        return "code_app"
    if "code sent to the email" in lower or "code sent to your email" in lower:
        return "code_email"
    return None


def provide_code(code: str) -> None:
    _codes.put(code.strip())


def _await_code(process: subprocess.Popen) -> str | None:
    while process.poll() is None and not _cancelled:
        try:
            return _codes.get(timeout=0.5)
        except queue.Empty:
            continue
    return None


def _run(args: list[str], login: dict | None = None) -> list[str]:
    """Run DepotDownloader, streaming QR, progress and log lines as events and answering its questions.

    `login` = {"username", "password"} signs in with credentials; the password only ever goes to the
    tool's standard input, never to its command line (other programs can read those) or to disk.
    """
    global _active, _cancelled
    user = login["username"] if login else settings.load()["steam_user"]
    auth = ["-username", user, "-remember-password"] if user else ["-qr", "-remember-password"]
    tool = _ensure_tool()
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    _cancelled = False
    while not _codes.empty():
        _codes.get_nowait()
    saved_logins = env.saved_logins()
    process = subprocess.Popen(
        [str(tool), "-app", str(APP), "-depot", str(DEPOT), *auth, *args],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        cwd=tool.parent, creationflags=flags,
    )
    _active = process
    log: list[str] = []
    qr: list[str] | None = None
    asked_password = False
    wrong_code = False
    stale_login = False
    remembered = ""
    announced = False

    def ours() -> list[Path]:
        # whichever login file this run wrote is ours: remember it for the profile and for signing out
        changed = [p for p, t in env.saved_logins().items() if saved_logins.get(p) != t]
        if changed:
            env.STORE_NOTE.write_text(changed[0].parent.parent.name, encoding="utf-8")
        return changed

    def signed_in() -> None:
        # a new sign-in (QR or password), not a remembered one: tell the window now, while the job goes on
        nonlocal announced
        announced = True
        changed = ours()
        names = env.accounts_in_config(changed[0].read_bytes()) if changed else []
        name = login["username"] if login else remembered or (names[0] if len(names) == 1 else "")
        if name:
            settings.update(steam_user=name)
            emit("steam.signed_in", {"user": name})

    def answer(text: str) -> None:
        process.stdin.write((text + "\n").encode())
        process.stdin.flush()

    def on_line(line: str) -> None:
        nonlocal qr, wrong_code, remembered
        log.append(line)
        if qr is not None:
            if set(line) & QR_DARK:
                qr.append(line)
                return
            if qr:  # the first quiet line after the code closes it
                emit("steam.qr", {"matrix": qr_matrix(qr)})
                qr = None
            return
        if "QR code" in line:
            qr = []
            emit("steam.status", {"key": "scan"})
            return
        if match := PROGRESS.match(line):
            emit("vault.progress", {"percent": float(match[1]), "file": Path(match[2]).name})
            return
        if "confirm your sign in" in line:
            emit("steam.status", {"key": "confirm"})
        if "code you have provided is incorrect" in line:
            wrong_code = True
        if match := REMEMBER.search(line):
            remembered = match[1]
        if LICENSES.search(line) and not announced and (login or not user):
            signed_in()
        if line.strip():
            emit("vault.log", line.strip())

    def on_prompt(kind: str, text: str) -> None:
        nonlocal asked_password, wrong_code, stale_login
        log.append(text)
        if kind == "password":
            if not login or asked_password:
                # a remembered login went stale, or the password was refused: stop here
                stale_login = not login
                process.kill()
                return
            asked_password = True
            answer(login["password"])
            return
        emit("steam.code", {"kind": "app" if kind == "code_app" else "email", "retry": wrong_code})
        wrong_code = False
        code = _await_code(process)
        if code is None:
            process.kill()
        else:
            answer(code)

    emit("steam.status", {"key": "connecting"})
    pending = b""
    while chunk := os.read(process.stdout.fileno(), 4096):
        pending += chunk
        *lines, pending = pending.split(b"\n")
        for raw in lines:
            on_line(_decode(raw).rstrip("\r"))
        if kind := prompt_kind(_decode(pending)):
            on_prompt(kind, _decode(pending))
            pending = b""
    if pending:
        on_line(_decode(pending).rstrip("\r"))
    code = process.wait()
    process.stdout.close()
    try:
        process.stdin.close()
    except OSError:
        pass  # the tool already went away
    _active = None
    ours()
    if _cancelled:
        raise Failure("Cancelled")
    text = "\n".join(log)
    if code != 0 or stale_login:
        if "is not available from this account" in text:
            raise Failure("error.notOwned")
        if login:
            if "RateLimit" in text:
                raise Failure("error.rateLimit")
            if asked_password and ("InvalidPassword" in text or process.returncode != 0 and "Failed to authenticate" in text):
                raise Failure("error.wrongPassword")
        if user and not login and (stale_login or AUTH_TROUBLE.search(text)):
            # the remembered login went stale: forget it and sign in again by QR
            settings.update(steam_user="")
            emit("steam.status", {"key": "relogin"})
            return _run(args)
        last = next((l.strip() for l in reversed(log) if l.strip()), f"exit code {code}")
        raise Failure(f"DepotDownloader failed: {last}")
    if not announced and (login or not user):
        signed_in()
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
def files(season: str, manifest: str, refresh: bool = False, login: dict | None = None) -> list[dict]:
    folder = settings.HOME / "manifests"
    cache = folder / f"manifest_{DEPOT}_{manifest}.txt"
    if refresh or not cache.is_file():
        with _job():
            scratch = folder / f"tmp-{manifest}"
            _run(["-manifest", manifest, "-manifest-only", "-dir", str(scratch)], login)
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
    job = {"season": season, "manifest": manifest, "files": len(files)}
    with _job():
        emit("vault.started", job)
        ok = False
        try:
            filelist = settings.HOME / "manifests" / f"filelist-{manifest}.txt"
            filelist.parent.mkdir(parents=True, exist_ok=True)
            filelist.write_text("\n".join(files), encoding="utf-8")
            _run(["-manifest", manifest, "-filelist", str(filelist), "-validate", "-dir", str(target)])
            done = sorted(_completed(target) | set(files))
            (target / MARKER).write_text(json.dumps({"season": season, "manifest": manifest, "files": done}, indent=1),
                                         encoding="utf-8")
            ok = True
        finally:
            # the window may have left the season page: it follows the job through these events
            emit("vault.ended", {**job, "ok": ok, "cancelled": _cancelled})
    return {"dir": str(target), "files": done}


@method("vault.cancel")
def cancel() -> bool:
    global _cancelled
    if _active is not None and _active.poll() is None:
        _cancelled = True
        _active.kill()
        return True
    return False


@method("vault.folder")
def folder(season: str, manifest: str) -> str:
    return str(_library(season, manifest))


# ------------------------------------------------------------ disk space

def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() else 0


def _cache_paths() -> list[Path]:
    """Things Reliquary fetches again by itself: manifests, artwork addresses, the DepotDownloader tool."""
    return [settings.HOME / "manifests", settings.HOME / "art.json", env.depot_tool().parent]


@method("vault.library")
def library() -> dict:
    """What the Vault keeps on disk, per season and build, so it can be cleaned up."""
    items = []
    for season in _seasons():
        for patch in season["patches"]:
            size = _size(_library(season["id"], patch["manifest"]))
            if size:
                items.append({"season": season["id"], "name": season["name"], "manifest": patch["manifest"],
                              "date": patch["date"], "bytes": size,
                              "files": len(_completed(_library(season["id"], patch["manifest"])))})
    return {"root": settings.load()["library"], "total": sum(i["bytes"] for i in items), "items": items,
            "cache": sum(_size(p) for p in _cache_paths())}


def _remove_inside_library(target: Path) -> None:
    root = Path(settings.load()["library"]).resolve()
    target = target.resolve()
    if target == root or root not in target.parents:
        raise Failure("Refusing to delete outside the library folder")  # never follow odd input elsewhere
    shutil.rmtree(target, ignore_errors=True)


@method("vault.delete")
def delete(season: str = "", manifest: str = "") -> dict:
    """Delete downloaded archives: one build, one season, or (no arguments) the whole library."""
    if _job_lock.locked():
        raise Failure("error.busy")
    known = {s["id"]: s for s in _seasons()}
    if season and season not in known:
        raise Failure(f"Unknown season {season!r}")
    for sid in [season] if season else list(known):
        manifests = [manifest] if manifest else [p["manifest"] for p in known[sid]["patches"]]
        for m in manifests:
            if _library(sid, m).exists():
                _remove_inside_library(_library(sid, m))
        season_dir = Path(settings.load()["library"]) / sid
        if season_dir.is_dir() and not any(season_dir.iterdir()):
            season_dir.rmdir()
    return library()


@method("vault.clear_cache")
def clear_cache() -> dict:
    if _job_lock.locked():
        raise Failure("error.busy")
    for path in _cache_paths():
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    return library()
