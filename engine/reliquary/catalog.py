"""The game's own catalog of cosmetics: every weapon skin and charm there is, not only the downloaded ones.

Siege keeps its shop list at download/shop/items/content (base64 of a gzipped JSON, refreshed by the game). Every
item has a type, a dev name ("weapon_charms_universal.Y1S3.Season_Rank_reward_Platinum_.DUST_LINE_PLATINUM"),
tags (season "Y1S3", "rarity_superrare", "type_weaponskin_universal"…) and the GameObjectID of its registry
record. From that record the registry leads to the item's own pictures, the ones the game shows: a charm's
268x220 icon, a weapon skin's 440x144 preview.

Only what the game has downloaded (its download cache, the ~9 GB of streamed content) can be exported. Nothing
links those documents to the catalog, so they are matched by their dev names (W_Charm_Y7S1_BP_ThemedContent_Flores
↔ weapon_charms_universal.Y7S1.BP_ThemedContent_Flores.KITSUNE_MASK).
"""
from __future__ import annotations

import base64
import functools
import gzip
import json
import re
import sys
from pathlib import Path

from . import operators
from .rpc import method

RANKS = ("copper", "bronze", "silver", "gold", "platinum", "emerald", "diamond", "champion")
FAMILIES = (  # a charm's kind, from its dev name and tags; the first that fits
    ("ranked", r"reward|ranked|seasonal_(?:rewards?_)?(?:" + "|".join(RANKS) + ")"),
    ("battlepass", r"battle_?pass|(?:^|[._])bp_|premium_?node|themedcontent"),
    ("esports", r"e_?sports?|pro_?league|pro_?teams?|major|invitational|(?:^|[._])si_|r6_?cup|go4r6"),
    ("chibi", r"chibi"),
    ("event", r"event|collection|halloween|christmas|snow|summer|lunar|new_?year|showdown|doktor|arcade|chroma"),
)
# words that say what an item is, not which one: left out when matching cache documents to catalog items
NOISE = {"w", "weapon", "weapons", "skin", "skins", "universal", "charm", "charms", "go", "uniskin", "unshared", "wss",
         "texture", "instanceof", "pc", "metal", "plastic", "body", "fabric", "brushed", "charm01"}


def _path() -> Path:
    return operators._game() / "download" / "shop" / "items" / "content"


@functools.lru_cache(maxsize=1)
def _read(path: str, modified: int) -> dict[int, dict]:
    try:
        doc = json.loads(gzip.decompress(base64.b64decode(Path(path).read_bytes())))
    except (OSError, ValueError, EOFError) as error:
        print(f"Shop catalog unreadable: {error}", file=sys.stderr)
        return {}
    return {int(i["obj"]["GameObjectID"], 16): i for i in doc.get("items", []) if (i.get("obj") or {}).get("GameObjectID")}


def items() -> dict[int, dict]:
    """The shop catalog by GameObjectID (empty until the game has opened its shop once)."""
    path = _path()
    return _read(str(path), path.stat().st_mtime_ns) if path.is_file() else {}


def season(item: dict) -> str:
    """Y3S2 from the item's tags, else from its dev name (Y1_MC → Y1)."""
    tag = next((t.upper() for t in item.get("tags", []) if re.fullmatch(r"[Yy]\d+[Ss]\d", t)), "")
    if tag:
        return tag
    found = re.match(r"Y(\d+)(?:S(\d))?", (item["nameId"].split(".") + [""])[1], re.I)
    return (f"Y{found[1]}S{found[2]}" if found[2] else f"Y{found[1]}") if found else ""


def name(item: dict) -> str:
    """LIBERTY_BELL → Liberty Bell; items without a display key get their dev name, tidied."""
    parts = item["nameId"].split(".")
    label = parts[-2] if len(parts) > 1 and re.fullmatch(r"0x[0-9a-f]+", parts[-1], re.I) else parts[-1]
    label = re.sub(r"_?0x[0-9a-f]{6,}$", "", label, flags=re.I)
    label = re.sub(r"_?Texture-.*$", "", label)
    for _ in range(3):  # Charm_Y5S1_GO_SeasonReward… carries several prefixes
        label = re.sub(r"^(?:WeaponSkin|Charm|GO|InstanceOf|Y\d+S\d)[_-]", "", label, flags=re.I)
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", label).replace("_", " ").replace("-", " ").split()
    words = [w for w in words if not re.fullmatch(r"(?i)y\d+s\d|wss", w)]
    return " ".join(w.capitalize() if w.isupper() or w.islower() else w for w in words) or label


def describe(item: dict) -> dict:
    tags = item.get("tags", [])
    return {"name": name(item), "season": season(item),
            "rarity": next((t[7:] for t in tags if t.startswith("rarity_")), "")}


def family(item: dict) -> str:
    text = f"{item['nameId']} {' '.join(item.get('tags', []))}".lower()
    if "esport" in item.get("tags", []) and not re.search(FAMILIES[0][1], text):
        return "esports"
    return next((kind for kind, test in FAMILIES if re.search(test, text)), "other")


def rank(item: dict) -> str:
    found = re.search("|".join(RANKS).replace("platinum", "platini?um"), item["nameId"].lower())  # Ubisoft's "Platinium" too
    return found[0].replace("platinium", "platinum") if found and family(item) == "ranked" else ""


def _tokens(*texts: str) -> set[str]:
    words = set()
    for text in texts:
        text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
        words |= {w for w in re.split(r"[^a-z0-9]+", text.lower()) if w}
    return words - NOISE


def _words(item: dict) -> set[str]:
    return _tokens(*item["nameId"].split(".")[1:], season(item))


def attach(entries: list[dict], docs: list[dict], doc_words) -> None:
    """Give catalog entries (each with "_words") the cache document they are, when the names say so: all of a
    document's words are in the entry's dev name, and no other entry fits it as tightly (then it's left alone)."""
    for doc in docs:
        words = doc_words(doc)
        if not words:
            continue
        fits = sorted(((len(e["_words"] - words), n) for n, e in enumerate(entries) if words <= e["_words"]))
        if fits and (len(fits) == 1 or fits[0][0] < fits[1][0]):
            entries[fits[0][1]].setdefault("file", doc["file"])


def weapon_skins(weapon: bytes, records: dict, docs: list[dict]) -> list[dict]:
    """Every skin of a weapon (its skin entries → catalog item + skin definition with the preview); `file` for the
    ones in the download cache (docs: the cache documents already matched to this weapon)."""
    shop, out = items(), []
    if not shop:  # no catalog yet (the game hasn't opened its shop): what the game has downloaded
        return [{"id": d["file"], "icon": "", "name": d["name"], "season": "", "rarity": "", "file": d["file"],
                 "universal": bool(d.get("pattern")) or "UNISKIN" in d["material"].upper()} for d in docs]
    for entry in dict.fromkeys(operators._u64(weapon, o) for o in range(len(weapon) - 7)):
        record = records.get(entry)
        if not record or record[0].file_type != operators.SKIN_ENTRY:
            continue
        data = record[0].data
        refs = {records[u][0].file_type: u for u in (operators._u64(data, o) for o in range(len(data) - 7))
                if u in records and records[u][0].file_type in (operators.ITEM, operators.SKIN_DEF)}
        item = shop.get(refs.get(operators.ITEM, -1))
        if not item or item.get("type") != "WeaponSkin":
            continue
        out.append({"id": f"{entry:016X}", "icon": f"{refs[operators.SKIN_DEF]:016X}" if operators.SKIN_DEF in refs else "",
                    **describe(item), "universal": any("universal" in t for t in item.get("tags", [])) or item["nameId"].startswith("weapon_skins_universal"),
                    "_words": _words(item)})
    # a camo pattern's document is named after the weapon's material: its pattern is in the name (Aloha B)
    attach(out, docs, lambda d: _tokens(d["material"], d["name"] if d.get("pattern") else "") - _tokens(d["class"], d["code"]))
    return sorted(({k: v for k, v in s.items() if k != "_words"} | {"file": s.get("file", "")} for s in out),
                  key=lambda s: s["name"].lower())


@method("catalog.charms")
def charms() -> list[dict]:
    """Every charm in the game, with its picture (icon: the registry charm), season, rarity, kind and rank;
    `file` when the game has downloaded it, so it can go in a pack."""
    from . import dcache

    docs = [e for e in dcache.catalog() if e["kind"] == "charm"]
    if not items():  # no catalog yet: the downloaded ones
        return sorted(({"id": d["file"], "icon": "", "name": d["name"], "season": "", "rarity": "", "family": "other",
                        "rank": "", "file": d["file"]} for d in {d["material"]: d for d in docs}.values()), key=lambda c: c["name"].lower())
    more = operators._more_records()
    by_item = {operators._u64(v[0].data, 98): u for u, v in more.items() if v[0].file_type == operators.CHARM}
    out = [{"id": f"{goid:016X}", "icon": f"{by_item[goid]:016X}" if goid in by_item else "", **describe(item),
            "family": family(item), "rank": rank(item), "_words": _words(item)}
           for goid, item in items().items() if item.get("type") == "Charm"]
    attach(out, docs, lambda d: _tokens(d["material"]))
    return sorted(({k: v for k, v in c.items() if k != "_words"} | {"file": c.get("file", "")} for c in out),
                  key=lambda c: c["name"].lower())
