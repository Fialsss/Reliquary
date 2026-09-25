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
from collections import Counter, defaultdict
from pathlib import Path

from . import operators
from .rpc import method

RANKS = ("copper", "bronze", "silver", "gold", "platinum", "emerald", "diamond", "champion")
FAMILIES = (  # a charm's kind, from its dev name and tags; the first that fits
    ("ranked", r"reward|ranked|legacy_go_rank|seasonal_(?:rewards?_)?(?:" + "|".join(RANKS) + ")"),
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
    if re.match(r"charm_legacy_go_rank_", item["nameId"], re.I):
        # Black Ice's ranked charms: "Unscheduled" in the shop, plain Rank-Copper… Rank-Diamond tokens in 2017's
        # builds, where every later season's ranked charms carry the season's name (Dust Line, Skull Rain…)
        return "Y1S1"
    tag = next((t.upper() for t in item.get("tags", []) if re.fullmatch(r"[Yy]\d+[Ss]\d", t)), "")
    if tag:
        return tag
    # Y1_MC → Y1 from the second part; Charm_Y4S3_GO_SeasonReward_Gold ("Unscheduled" in the shop) → Y4S3
    found = re.match(r"Y(\d+)(?:S(\d))?", (item["nameId"].split(".") + [""])[1], re.I) or re.search(r"(?:^|_)Y(\d+)S(\d)(?=_)", item["nameId"])
    return (f"Y{found[1]}S{found[2]}" if found[2] else f"Y{found[1]}") if found else ""


# ponytail: the game's own names are in its localization tables, which Reliquary doesn't read yet (a skin definition
# names its string, 65000000_0003134C for the MP5's). Until then, dev names that are plainly wrong get the game's:
# 2016's Pro League Season 1 camos are "GOLD_DUST" in the shop, the real Gold Dust's name (the grades as the
# game shows them on the 556xi and the MP5; the 591A1 is the third)
PRO_LEAGUE_S1 = {"W_SG_591A1": 1, "W_SMG_MP5MLI": 2, "W_AR_Sig556": 3}


def name(item: dict) -> str:
    """LIBERTY_BELL → Liberty Bell; items without a display key get their dev name, tidied."""
    if "R6Unique-SPECIAL.GOLD_DUST" in item["nameId"]:
        grade = next((PRO_LEAGUE_S1[t] for t in item.get("tags", []) if t in PRO_LEAGUE_S1), 0)
        return f"Pro League S1 Grade {grade}" if grade else "Pro League S1"
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
    if family(item) == "ranked" and "newrank" in item["nameId"].lower():
        return "champion"  # Y4S3's SeasonReward_NewRank_TBD: Ember Rise brought the Champion rank
    found = re.search("|".join(RANKS).replace("platinum", "platini?um"), item["nameId"].lower())  # Ubisoft's "Platinium" too
    return found[0].replace("platinium", "platinum") if found and family(item) == "ranked" else ""


def _title_ranked(charms: list[dict]) -> None:
    """Ranked charms the shop names only "Season Reward Gold" or "Reward Gold" take the name their season's others
    carry (Blood Orchid, Ember Rise, Shifting Tides, Void Edge); a season with none or two (Y4S2) keeps them as is."""
    titles = defaultdict(set)
    for c in charms:
        if c["rank"] and not re.match(r"(?i)(?:season )?reward\b", c["name"]) and c["name"].lower().endswith(c["rank"]):
            titles[c["season"]].add(c["name"][:-len(c["rank"])].strip())
    for c in charms:
        if c["rank"] and re.match(r"(?i)(?:season )?reward\b", c["name"]) and len(titles[c["season"]]) == 1:
            c["name"] = f"{next(iter(titles[c['season']]))} {c['rank'].capitalize()}"


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


def _uids(data: bytes) -> list[int]:
    return [u for u in dict.fromkeys(operators._u64(data, o) for o in range(len(data) - 7)) if u > 0xFFFFFFFF]


def installed(candidates: dict[int, list[int]], types: set[int]) -> dict[int, str]:
    """Which items the game installed with itself (datapc64_mtx, _dmtx…): the first of each item's candidate uids
    the asset index knows with one of `types`, as a `file` ("game:<uid>"). Those export without the download cache."""
    from src.database import load_asset_index

    index = load_asset_index(operators._database(), {u for uids in candidates.values() for u in uids})
    found = {key: next((u for u in uids if (r := index.primary(u)) is not None and r.file_type in types), 0)
             for key, uids in candidates.items()}
    return {key: f"{operators.INSTALLED}{uid:016X}" for key, uid in found.items() if uid}


def join_old(skins: list[dict], shows: dict[str, set[int]], old: list[tuple[set[int], str, str, str]]) -> None:
    """Give the skins nothing else can export the retired look that shows the same icon: an old look (its icon uids,
    file, season label, look: colour sheet and tint) goes to the one catalog skin whose definition names one of its
    icons (shows: skin id → the uids its definition names); when two skins would fit, neither gets it. Two skins
    landing on the very same look would come out the same, so one of them would be wrong: neither gets it."""
    given: dict[str, tuple[str, str, str]] = {}
    for icons, file, label, sheet in old:
        fits = [s for s in skins if shows.get(s["id"], set()) & icons]
        if len(fits) == 1 and not fits[0]["file"] and fits[0]["id"] not in given:
            given[fits[0]["id"]] = (file, label, sheet)
    skins_per_sheet = Counter(sheet for _, _, sheet in given.values())
    for skin in skins:
        if skin["id"] in given and skins_per_sheet[given[skin["id"]][2]] == 1:
            skin["file"], skin["source"] = given[skin["id"]][:2]


def weapon_skins(weapon: bytes, records: dict, docs: list[dict], old: list | None = None) -> list[dict]:
    """Every skin of a weapon (its skin entries → catalog item + skin definition with the preview); `file` for the
    ones that can be exported: in the download cache (docs: the cache documents already matched to this weapon),
    installed with the game (the entry's appearance names a material or a model of the game's mtx archives), or
    retired but still in an old build set in Settings (old: from retired.for_weapon, met through the skin's icons)."""
    from src.material import CURRENT_MATERIAL
    from src.operator_registry import APPEARANCE_TYPE

    shop, out, looks = items(), [], {}
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
        looks[entry] = [u for a in _uids(data) if a in records and records[a][0].file_type == APPEARANCE_TYPE for u in _uids(records[a][0].data)]
        out.append({"id": f"{entry:016X}", "icon": f"{refs[operators.SKIN_DEF]:016X}" if operators.SKIN_DEF in refs else "",
                    **describe(item), "universal": any("universal" in t for t in item.get("tags", [])) or item["nameId"].startswith("weapon_skins_universal"),
                    "_words": _words(item)})
    # a camo pattern's document is named after the weapon's material: its pattern is in the name (Aloha B)
    attach(out, docs, lambda d: _tokens(d["material"], d["name"] if d.get("pattern") else "") - _tokens(d["class"], d["code"]))
    game = installed(looks, {CURRENT_MATERIAL, *operators.MODEL_TYPES})
    for skin in out:
        skin["file"] = skin.get("file") or game.get(int(skin["id"], 16), "")
    if old:
        join_old(out, {s["id"]: set(_uids(records[int(s["icon"], 16)][0].data)) for s in out if s["icon"]}, old)
    return sorted(({k: v for k, v in s.items() if k != "_words"} for s in out), key=lambda s: s["name"].lower())


@method("catalog.charms")
def charms() -> list[dict]:
    """Every charm, as `operators.index` got them ready; worked out now when it hasn't."""
    return operators._prepared().get("charms") or find_charms()


def find_charms(cached: list[dict] | None = None, loaded: list | None = None) -> list[dict]:
    """Every charm in the game, with its picture (icon: the registry charm), season, rarity, kind and rank;
    `file` when it can go in a pack: downloaded by the game, installed with it (a model the charm names), or kept by
    an old build set in Settings (Year 1's: met through the icons the charm's UI record, +62, still names).
    cached: the download cache's documents, loaded: the old builds, when the caller has read them already."""
    from . import dcache, retired

    docs = [e for e in (dcache.catalog() if cached is None else cached) if e["kind"] == "charm"]
    if not items():  # no catalog yet: the downloaded ones
        return sorted(({"id": d["file"], "icon": "", "name": d["name"], "season": "", "rarity": "", "family": "other",
                        "rank": "", "file": d["file"]} for d in {d["material"]: d for d in docs}.values()), key=lambda c: c["name"].lower())
    more = operators._more_records()
    by_item = {operators._u64(v[0].data, 98): u for u, v in more.items() if v[0].file_type == operators.CHARM}
    out = [{"id": f"{goid:016X}", "icon": f"{by_item[goid]:016X}" if goid in by_item else "", **describe(item),
            "family": family(item), "rank": rank(item), "_words": _words(item)}
           for goid, item in items().items() if item.get("type") == "Charm"]
    attach(out, docs, lambda d: _tokens(d["material"]))
    game = installed({u: _uids(more[u][0].data) for u in by_item.values()}, set(operators.MODEL_TYPES))
    old = retired.charms(retired.loaded() if loaded is None else loaded)
    for charm in out:
        charm["file"] = charm.get("file") or game.get(int(charm["icon"] or "0", 16), "")
        ui = more.get(operators._u64(more[int(charm["icon"], 16)][0].data, 62)) if charm["icon"] and old else None
        found = next((old[i] for i in _uids(ui[0].data) if i in old), None) if ui else None
        if not charm["file"] and found:
            charm["file"], charm["source"] = found
    _title_ranked(out)
    return sorted(({k: v for k, v in c.items() if k != "_words"} for c in out), key=lambda c: c["name"].lower())
