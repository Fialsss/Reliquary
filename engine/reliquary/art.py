"""Season artwork, looked up at runtime on the Rainbow Six Fandom wiki.

The images belong to Ubisoft and are never part of this repository: the app
asks the wiki for their addresses and the window loads them like a browser
would. Answers are cached for a week; without a connection the pages fall back
to generated covers.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
import urllib.request

from . import settings, vault
from .rpc import method

API = "https://rainbowsix.fandom.com/api.php"
AGENT = "Reliquary/0.2 (+https://github.com/Fialsss/Reliquary)"
CACHE = settings.HOME / "art.json"
WEEK = 7 * 24 * 3600

# page images that are not season artwork: item icons, flags, portraits and the like
NOT_ART = re.compile(r"(?i)\.(png|gif)$|\.svg|skin|charm|uniform|headgear|portrait|booster|credit|flag|icon|"
                     r"attachment|card|logo|badge|bundle|pack|chibi|sticker|seasonal|elite|renown|alpha|r6s?_?y\d")
_lock = threading.Lock()


def _query(**params) -> dict:
    params.update(format="json", formatversion=2)
    request = urllib.request.Request(f"{API}?{urllib.parse.urlencode(params)}", headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def _title(season: dict) -> str:
    return "Tom Clancy's Rainbow Six Siege" if season["id"] == "Y1S0" else f"Operation {season['name']}"


def _load() -> dict:
    try:
        cached = json.loads(CACHE.read_text(encoding="utf-8"))
        return cached if time.time() - cached.get("at", 0) < WEEK else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({**data, "at": time.time()}), encoding="utf-8")


def _resolve_pages() -> dict[str, dict]:
    """Season id → {title, cover} with one batched request, plus a search for names the wiki spells differently."""
    seasons = vault.seasons()
    wanted = {s["id"]: _title(s) for s in seasons}
    reply = _query(action="query", titles="|".join(wanted.values()), prop="pageimages", pithumbsize=1280, redirects=1)["query"]
    renamed = {n["from"]: n["to"] for n in reply.get("normalized", []) + reply.get("redirects", [])}
    pages = {p["title"]: p for p in reply["pages"]}
    found = {}
    for season in seasons:
        title = wanted[season["id"]]
        page = pages.get(renamed.get(renamed.get(title, title), renamed.get(title, title)), {})
        if page.get("missing") or not page.get("thumbnail"):
            page = _find(season["name"])
        if page.get("thumbnail"):
            found[season["id"]] = {"title": page["title"], "cover": page["thumbnail"]["source"]}
    return found


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _find(name: str) -> dict:
    """A page for a season the wiki spells differently ("Day Break" → "Daybreak"), never another season's."""
    for title in (f"Operation {name.replace(' ', '')}", f"Operation {name.replace(' ', '').capitalize()}", name):
        page = _query(action="query", titles=title, prop="pageimages", pithumbsize=1280, redirects=1)["query"]["pages"][0]
        if not page.get("missing") and page.get("thumbnail"):
            return page
    for hit in _query(action="query", list="search", srsearch=name, srlimit=5)["query"]["search"]:
        if _squash(name) in _squash(hit["title"]):
            page = _query(action="query", titles=hit["title"], prop="pageimages", pithumbsize=1280)["query"]["pages"][0]
            if page.get("thumbnail"):
                return page
    return {}


@method("art.seasons")
def seasons() -> dict:
    """Cover address for every season (empty when offline)."""
    with _lock:
        cached = _load()
        if not cached.get("pages"):
            try:
                cached = {"pages": _resolve_pages(), "galleries": cached.get("galleries", {})}
                _save(cached)
            except OSError:
                return {}
    return {sid: page["cover"] for sid, page in cached["pages"].items()}


@method("art.gallery")
def gallery(season: str) -> list[str]:
    """Up to twelve images from the season's wiki page: key art, teasers, lobby and loading screens."""
    seasons()
    with _lock:
        cached = _load()
        if season in cached.get("galleries", {}):
            return cached["galleries"][season]
        page = cached.get("pages", {}).get(season)
    if not page:
        return []
    try:
        names = [i["title"] for i in _query(action="query", titles=page["title"], prop="images", imlimit=500)["query"]["pages"][0].get("images", [])]
        names = [n for n in names if not NOT_ART.search(n)][:12]
        cover = page["cover"].split("/revision")[0].rsplit("/", 1)[-1]
        urls = []
        if names:
            info = _query(action="query", titles="|".join(names), prop="imageinfo", iiprop="url", iiurlwidth=1280)["query"]["pages"]
            urls = [p["imageinfo"][0].get("thumburl") or p["imageinfo"][0]["url"] for p in info if p.get("imageinfo")]
            # the key art first, then the rest
            urls.sort(key=lambda u: cover not in u)
    except OSError:
        return []
    with _lock:
        cached = _load() or {"pages": {}, "galleries": {}}
        cached.setdefault("galleries", {})[season] = urls
        _save(cached)
    return urls
