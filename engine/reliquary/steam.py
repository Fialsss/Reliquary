"""The Steam session: sign-in, and the profile shown in the account menu.

Signing in is DepotDownloader's own QR flow. It keeps a refresh token in .NET
IsolatedStorage; Reliquary reads only the SteamID claim from it (the token
itself never leaves this module) and asks the public Steam Community profile
for the display name and avatar. No API key, nothing sent anywhere else.
"""
from __future__ import annotations

import base64
import json
import re
import shutil
import urllib.request
import zlib
from pathlib import Path

from . import env, settings, vault
from .rpc import Failure, method

PROFILE_FILE = settings.HOME / "steam.json"
JWT = re.compile(rb"ey[\w-]+\.([\w-]+)\.[\w-]+")


def _storage_dirs() -> list[Path]:
    """The IsolatedStorage folder our DepotDownloader wrote its login to (noted during the run)."""
    try:
        name = env.STORE_NOTE.read_text(encoding="utf-8").strip()
    except OSError:
        return []
    return list(env.ISOLATED.glob(f"*/*/{name}")) if name.startswith("Url.") else []


def _configs() -> list[Path]:
    """Our login file first; without a note, every saved login, newest first (matched by account name later)."""
    ours = [d / "AssemFiles" / "account.config" for d in _storage_dirs()]
    ours = [c for c in ours if c.is_file()]
    return ours or sorted(env.saved_logins(), key=lambda c: c.stat().st_mtime, reverse=True)


def _inflate(raw: bytes) -> bytes:
    try:
        return zlib.decompress(raw, -15)  # DepotDownloader writes a raw DeflateStream
    except zlib.error:
        return b""


def accounts_in_config(raw: bytes) -> list[str]:
    """Account names that have a saved login token (protobuf map keys followed by a JWT)."""
    data = _inflate(raw)
    names = []
    for match in re.finditer(rb"\x0a([\x02-\x40])([\w.-]+)\x12..ey", data, re.S):
        if match[1][0] == len(match[2]):
            names.append(match[2].decode())
    return list(dict.fromkeys(names))


def steamid_from_config(raw: bytes, user: str) -> str | None:
    """SteamID64 from the `sub` claim of the token saved for `user` in account.config."""
    data = _inflate(raw)
    at = data.find(user.encode())
    match = JWT.search(data, at) if at >= 0 else None
    if not match:
        return None
    try:
        claims = json.loads(base64.urlsafe_b64decode(match[1] + b"=" * (-len(match[1]) % 4)))
    except ValueError:
        return None
    sub = str(claims.get("sub", ""))
    return sub if sub.isdigit() and len(sub) == 17 else None


def _steamid(user: str) -> str | None:
    for config in _configs():
        if sid := steamid_from_config(config.read_bytes(), user):
            return sid
    return None


def _tag(xml: str, tag: str) -> str:
    match = re.search(rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", xml, re.S)
    return match[1].strip() if match else ""


def fetch_profile(steamid: str) -> dict:
    """Display name and avatar (as a data URI, so the window needs no remote images)."""
    with urllib.request.urlopen(f"https://steamcommunity.com/profiles/{steamid}/?xml=1", timeout=15) as r:
        xml = r.read().decode("utf-8", "replace")
    name, avatar_url = _tag(xml, "steamID"), _tag(xml, "avatarFull")
    avatar = ""
    if avatar_url.startswith("https://"):
        with urllib.request.urlopen(avatar_url, timeout=15) as r:
            avatar = "data:image/jpeg;base64," + base64.b64encode(r.read()).decode()
    return {"steamid": steamid, "name": name, "avatar": avatar}


@method("steam.profile")
def profile(refresh: bool = False) -> dict | None:
    user = settings.load()["steam_user"]
    if not user:
        return None
    try:
        cached = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
        if cached.get("user") == user and not refresh:
            return cached
    except (OSError, ValueError):
        pass
    result = {"user": user, "steamid": "", "name": user, "avatar": ""}
    steamid = _steamid(user)
    if steamid:
        try:
            result.update(fetch_profile(steamid))
        except OSError:
            result["steamid"] = steamid  # offline: keep the login name, try again next time
        else:
            PROFILE_FILE.write_text(json.dumps(result), encoding="utf-8")
    return result


@method("steam.login")
def login() -> dict | None:
    """Sign in by asking Steam for the latest season's file list: it proves ownership too."""
    latest = vault.seasons()[-1]
    vault.files(latest["id"], latest["patches"][-1]["manifest"], refresh=True)
    if not settings.load()["steam_user"]:
        # DepotDownloader didn't print the account name: take it from the login it just saved
        names = accounts_in_config(_configs()[0].read_bytes()) if _configs() else []
        if len(names) != 1:
            raise Failure("Signed in, but the Steam account name couldn't be determined")
        settings.update(steam_user=names[0])
    return profile(refresh=True)


@method("steam.signout")
def signout() -> dict:
    for folder in _storage_dirs():  # only our own login: other DepotDownloader copies keep theirs
        shutil.rmtree(folder, ignore_errors=True)
    env.STORE_NOTE.unlink(missing_ok=True)
    PROFILE_FILE.unlink(missing_ok=True)
    return settings.update(steam_user="")
