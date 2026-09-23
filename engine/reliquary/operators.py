"""Operators: the roster from the installed game, and Blender packs of them with the skins you pick.

Everything goes through the vendored R6-parser: its registry reader lists the
operators and their cosmetics, its asset index (SQLite, built once and refreshed
after game updates) finds every mesh and texture, and its exporter writes each
model. Blender then assembles a .blend with the parser's add-on, which rebuilds
the Siege materials: one collection per uniform and per headgear, ready to switch.

Uniforms and headgears are the registry's body (69EE9B83) and head (A2929EB6)
items: each names its operator at +105, its appearance (the models) at +8 and
its UI record (label and icon) at +53.
"""
from __future__ import annotations

import base64
import functools
import io
import json
import os
import queue
import re
import struct
import subprocess
import sys
import threading
from collections import Counter
from pathlib import Path

from . import env, settings
from .rpc import Failure, emit, method

ENGINE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
PARSER = ENGINE / "r6parser"
sys.path.insert(0, str(PARSER))

TEXTURE_MAP_SPEC = 0x4F09331E
ICON_BOX = (300, 600)  # portraits are 436x736, cosmetic icons 252x212, sight icons 488x280
_busy = threading.Lock()  # indexing and exporting both read the whole game: one at a time
_types_lock = threading.Lock()  # guards the parser's module-level KEEP_TYPES while a reader uses it


def _game() -> Path:
    game = env.find_game()
    if game is None:
        raise Failure("Game folder not found. Set it in Settings.")
    oodle = env.find_oodle()
    if oodle:
        os.environ["R6_OODLE_DLL"] = str(oodle)
    return game


def _database() -> Path:
    return settings.HOME / "r6-assets.sqlite"


def _u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0] if offset + 8 <= len(data) else 0


@functools.lru_cache(maxsize=1)
def _read_roster(archive: str, modified: int) -> tuple:
    from src.decompress import OodleUnavailableError
    from src.operator_registry import read_operator_registry

    try:
        with _types_lock:
            return read_operator_registry(archive)
    except OodleUnavailableError as error:
        raise Failure("Oodle runtime not found. Point Reliquary to an oo2core_*_win64.dll in Settings.") from error
    except ValueError as error:
        # the registry layout moves with game updates; say so instead of a stack trace
        raise Failure(f"This game build isn't supported by the operator reader yet ({error})") from error


@functools.lru_cache(maxsize=1)
def _read_records(archive: str, modified: int) -> dict:
    """The registry's records the parser keeps (operators, bodies, heads, appearances, UI): ~6 MB, 2 s."""
    from src.operator_registry import _read_records as read

    with _types_lock:
        return read(Path(archive))


def _roster() -> tuple:
    archive = _game() / "datapc64.forge"
    return _read_roster(str(archive), archive.stat().st_mtime_ns)  # cached until the game updates


def _records() -> dict:
    archive = _game() / "datapc64.forge"
    return _read_records(str(archive), archive.stat().st_mtime_ns)


def _operator(uid: str):
    operator = next((o for o in _roster() if f"{o.uid:016X}" == uid), None)
    if operator is None:
        raise Failure(f"Unknown operator {uid}")
    return operator


def _folder_name(name: str) -> str:
    return "".join("_" if c in '<>:"/\\|?*' or ord(c) < 32 else c for c in name).strip().rstrip(".") or "operator"


def _pack_folder(name: str) -> Path:
    return Path(settings.load()["exports"]) / _folder_name(name)


def _blend(name: str) -> Path:
    return _pack_folder(name) / f"{_folder_name(name)}.blend"


SIDE_LIST, SIDE_NEXT = bytes.fromhex("0d8152e3"), bytes.fromhex("2f73b62b")


def _side(data: bytes) -> str:
    """Attack or defense. The operator record has a list property (tag 0d8152e3, u32 count, u64 uids) right
    before property 2f73b62b: one entry for every defender, none for attackers (39/39 on the 2026-09-22 build)."""
    for match in re.finditer(re.escape(SIDE_LIST), data):
        count = struct.unpack_from("<I", data, match.start() + 4)[0] if match.start() + 8 <= len(data) else 0
        end = match.start() + 8 + count * 8
        if data[end:end + 4] == SIDE_NEXT:
            return "defense" if count else "attack"
    return ""


@method("operators.list")
def list_operators() -> list[dict]:
    records = _records()
    return sorted(({"uid": f"{o.uid:016X}", "name": o.name,
                    "side": _side(records[o.uid][0].data) if o.uid in records else "",
                    "blend": str(_blend(o.name)) if _blend(o.name).is_file() else ""}
                   for o in _roster()), key=lambda o: o["name"])


@method("operators.status")
def status() -> dict:
    database = _database()
    return {"indexed": database.is_file(), "bytes": database.stat().st_size if database.is_file() else 0,
            "exports": settings.load()["exports"], "busy": _busy.locked()}


@method("operators.index")
def build_index() -> dict:
    """Index every archive of the game (only the changed ones on later runs): a few minutes the first time."""
    from src.database import index_archive

    game = _game()
    if not _busy.acquire(blocking=False):
        raise Failure("error.opBusy")
    try:
        archives = sorted(game.glob("*.forge"))
        failed = []
        for done, archive in enumerate(archives):
            emit("operators.progress", {"step": "index", "done": done, "total": len(archives), "file": archive.name})
            try:
                index_archive(archive, _database())
            except Exception as error:  # one unreadable archive shouldn't cost the whole index
                print(f"Index failed for {archive.name}: {error}", file=sys.stderr)
                failed.append(archive.name)
        emit("operators.progress", {"step": "index", "done": len(archives), "total": len(archives), "file": ""})
    finally:
        _busy.release()
    return {**status(), "failed": failed}


# ------------------------------------------------------------- cosmetics

def _is_cosmetic(record) -> bool:
    from src.operator_registry import BODY_TYPE, HEAD_TYPE

    return record.file_type in (BODY_TYPE, HEAD_TYPE)


def _describe(uid: int, record, records: dict) -> dict:
    from src.operator_registry import BODY_TYPE, DEFAULT_NAME_KEY, _localized_text

    label, key = "", 0
    ui = records.get(_u64(record.data, 53))
    if ui:
        try:
            label, key = _localized_text(ui[0].data)
        except ValueError:
            pass
    label = label.lstrip("!")
    return {"uid": f"{uid:016X}", "kind": "uniform" if record.file_type == BODY_TYPE else "headgear",
            "default": key == DEFAULT_NAME_KEY,
            # template labels (_TPL__UNF_2D…) aren't names; the real ones live in the localization tables
            "label": "" if "TPL" in label.upper() or label.upper() == "NONE" else label}


@method("operators.cosmetics")
def cosmetics(uid: str) -> dict:
    """An operator's uniforms and headgears: the default first, then newest first."""
    owner = int(uid, 16)
    records = _records()
    items = [_describe(u, v[0], records) for u, v in records.items()
             if _is_cosmetic(v[0]) and _u64(v[0].data, 105) == owner]
    items.sort(key=lambda i: (not i["default"], -int(i["uid"], 16)))
    return {kind: [i for i in items if i["kind"] == kind] for kind in ("uniform", "headgear")}


def _gui_image(payload: bytes):
    """The largest mip of a texture of any size (GUI icons are 252x212 and such, which the parser skips).

    The stored top level is the biggest one the data holds: the trailer's shift field isn't reliable across
    texture versions (attachment icons keep full-size data with shift 1, their low-res twins the reverse)."""
    from PIL import Image
    from src import texture

    formats = {**texture.FORMATS, 16: (98, 16)}  # 16: BC7 (sRGB), used by attachment icons
    start = payload.find(texture.TEXMAPDATA_MAGIC) + 12
    for trailer in range(len(payload) - 48, start, -1):
        w, h, _, _, shift = struct.unpack_from("<5I", payload, trailer)
        fmt = struct.unpack_from("<I", payload, trailer + 32)[0]
        if not (4 <= w <= 8192 and 4 <= h <= 8192 and shift < 8) or fmt not in formats:
            continue
        dxgi, block = formats[fmt]
        for level in range(4):
            lw, lh = max(1, w >> level), max(1, h >> level)
            top = ((lw + 3) // 4) * ((lh + 3) // 4) * block
            if top <= trailer - start:
                break
        else:
            continue
        with Image.open(io.BytesIO(texture._dds_dx10(lw, lh, payload[start:start + top], dxgi))) as source:
            return source.convert("RGBA").transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    raise ValueError("no readable surface")


def _first_asset(data: bytes, types: set[int], skip: int = 0):
    """The first uid inside `data` that the asset index knows with one of `types`."""
    from src.database import load_asset_index

    candidates = [u for u in dict.fromkeys(_u64(data, o) for o in range(len(data) - 7)) if u > 0xFFFFFFFF and u != skip]
    index = load_asset_index(_database(), set(candidates))
    for uid in candidates:
        record = index.primary(uid)
        if record is not None and record.file_type in types:
            return record
    return None


def _picture_record(uid: int, records: dict, emblem: bool = False) -> bytes:
    """The record whose texture map spec is an item's picture: a uniform's or headgear's UI record (+53), an
    operator's card (665 bytes past the loadout table: the portrait) or badge (its appearance: the emblem),
    a sight's UI record."""
    from src.operator_registry import OPERATOR_TYPE

    more = _more_records()
    if uid in records:
        record = records[uid][0]
        if record.file_type == OPERATOR_TYPE:
            base = 8 + struct.unpack_from("<I", record.data, 4)[0] * 8
            if emblem:
                badge = next(more[u][0].data for o in range(base, len(record.data) - 7)
                             if (u := _u64(record.data, o)) in more and more[u][0].file_type == BADGE)
                return more[_u64(badge, 8)][0].data
            return more[_u64(record.data, base + 665)][0].data
        return records[_u64(record.data, 53)][0].data
    sight = more[uid][0].data
    return next(more[u][0].data for o in range(len(sight) - 7) if (u := _u64(sight, o)) in more and more[u][0].file_type == SIGHT_UI)


def _make_icon(uid: int, records: dict, path: Path, emblem: bool = False) -> None:
    """Item → picture record → texture map spec → GUI texture → a WebP that keeps the transparency."""
    from src.model import TEXTURE_TYPES, load_asset_payload

    spec = _first_asset(_picture_record(uid, records, emblem), {TEXTURE_MAP_SPEC})
    if spec is None:
        raise ValueError("no icon")
    spec_data = load_asset_payload(spec)
    # 05A61FAD: the full-size GUI map, when there is one; 9468B9E2: its low-res twin
    texture = _first_asset(spec_data, {0x05A61FAD}, skip=spec.uid) or _first_asset(spec_data, {0x9468B9E2, *TEXTURE_TYPES}, skip=spec.uid)
    if texture is None:
        raise ValueError("no icon texture")
    image = _gui_image(load_asset_payload(texture))
    image.thumbnail(ICON_BOX)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, quality=88)


@method("operators.icons")
def icons(uids: list[str]) -> dict[str, str]:
    """The game's own pictures of operators (portraits; "<uid>.emblem" for their badge), uniforms, headgear and
    sights, as data URIs, decoded once and kept in the app folder."""
    if not _database().is_file():
        return {}
    records, folder, out = _records(), settings.HOME / "icons", {}
    for text in uids:
        path = folder / f"{text}.webp"
        if not path.is_file():
            try:
                uid, _, variant = text.partition(".")
                _make_icon(int(uid, 16), records, path, variant == "emblem")
            except (ValueError, KeyError, OSError, StopIteration, struct.error) as error:
                print(f"No icon for {text}: {error}", file=sys.stderr)
                continue
        out[text] = "data:image/webp;base64," + base64.b64encode(path.read_bytes()).decode()
    return out


# ------------------------------------------------------------------ packs

def _export_model(uid: int, children: dict, database: Path, output: Path) -> None:
    """The parser CLI's `model --depgraph --database` path, without its console output."""
    from src.cli import _load_database_model_index
    from src.database import load_asset_index
    from src.depgraph import load_depgraph
    from src.model import export_model

    try:
        export_model(uid, children, _load_database_model_index(database, uid, children), output)
        return
    except ValueError:  # no meshes under it here: some models (sights…) have them in their own bundle's graph
        record = load_asset_index(database, {uid}).primary(uid)
        own = record.archive.with_suffix(".depgraphbin") if record is not None else None
        if own is None or not own.is_file():
            raise
    children = load_depgraph(own)
    export_model(uid, children, _load_database_model_index(database, uid, children), output)


def _primary_models(appearance: bytes) -> list[int]:
    """Group 0 of an appearance: the models worn by default (7 groups of u32 count + u64 uids from +79)."""
    cursor, groups = 79, []
    for _ in range(7):
        count = struct.unpack_from("<I", appearance, cursor)[0]
        groups.append(struct.unpack_from(f"<{count}Q", appearance, cursor + 4))
        cursor += 4 + count * 8
    return list(dict.fromkeys(groups[0]))


def _item_name(item: dict, number: int) -> str:
    kind = "Uniform" if item["kind"] == "uniform" else "Headgear"
    return f"{kind} {number:02d}" + (" · default" if item["default"] else f" · {item['label']}" if item["label"] else "")


# ---------------------------------------------------------------- weapons
# Record types of the 2026-09-22 build, found by hand (the parser doesn't cover weapons): a weapon, its name
# record (+423), its skin entries and the skin definitions behind them. Game updates rename these hashes.
WEAPON, WEAPON_NAME, SKIN_ENTRY, SKIN_DEF = 0x9622A2AB, 0x62709064, 0x32EFC7DC, 0x7E3B0D27
# an operator's card (portrait spec at +109) and badge (appearance at +8: the emblem), a sight (appearance at +8)
# and its UI record (name, icon specs)
PORTRAIT, BADGE, SIGHT, SIGHT_UI = 0xE592C2BB, 0x2A58CB6D, 0x7083B532, 0xBF157A00
MAGAZINE = 0xD6767312  # a weapon's magazine (default one first, variants after): appearance at +8 → a model
MODEL_TYPES = (0xADE00798, 0x1D2E4B8F)
# names the registry and the cache spell too differently to meet on their own
ALIASES = {"remingtonr4": ("r4c", "m4", "m4a1"), "serbu": ("supershorty",), "57usg": ("usg57",)}


@functools.lru_cache(maxsize=1)
def _read_more_records(archive: str, modified: int) -> dict:
    """The registry records the parser doesn't keep: weapons, skins, sights, operator cards."""
    import src.operator_registry as registry

    with _types_lock:  # the parser's reader filters on its module-level KEEP_TYPES
        saved = registry.KEEP_TYPES
        registry.KEEP_TYPES = {WEAPON, WEAPON_NAME, SKIN_ENTRY, SKIN_DEF, PORTRAIT, BADGE, SIGHT, SIGHT_UI, MAGAZINE,
                               registry.APPEARANCE_TYPE}
        try:
            return registry._read_records(Path(archive))
        finally:
            registry.KEEP_TYPES = saved


def _more_records() -> dict:
    archive = _game() / "datapc64.forge"
    return _read_more_records(str(archive), archive.stat().st_mtime_ns)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower().replace("hardcoded", "").replace("name", ""))


def _close(a: str, b: str) -> bool:
    """One typo apart: an edit, or two neighbours swapped (C8FSW / C8SFW)."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return len(diff) <= 1 or (len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    short, long_ = sorted((a, b), key=len)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def match_skins(label: str, bones: list[int], names: list[str], skins: list[dict]) -> list[dict]:
    """The cached skins of one installed weapon. Their skeleton must hold every bone of the weapon's mesh; then
    the weapon's name picks the code (FAMAS G2 → FAMAS, FAMASG2, FamasG2…). Weapons whose name lives only in the
    localization tables fall back on their skins' names: the code they appear with most, if it clearly wins."""
    candidates = [s for s in skins if set(bones) <= set(s["bones"])] if bones else list(skins)
    codes = {_norm(s["code"]) for s in candidates}
    key = _norm(label)
    chosen: set[str] = set()
    if len(key) >= 3:
        for k in {key, *ALIASES.get(key, ())}:
            found = {c for c in codes if c == k or (min(len(c), len(k)) >= 3 and (k in c or c in k))}
            chosen |= found or {c for c in codes if min(len(c), len(k)) >= 4 and _close(k, c)}
    else:
        tally: Counter = Counter()
        for name in names:
            n = _norm(name)
            hit = {_norm(s["code"]) for s in candidates if n in _norm(s["material"])}
            for code in hit:
                tally[code] += 1 / len(hit)
        ranked = tally.most_common(2)
        if ranked and ranked[0][1] >= 2 and (len(ranked) == 1 or ranked[0][1] >= 2 * ranked[1][1]):
            chosen = {ranked[0][0]}
    return [s for s in candidates if _norm(s["code"]) in chosen]


def _text(data: bytes) -> str:
    from src.operator_registry import _localized_text

    try:
        return _localized_text(data)[0].lstrip("!")
    except ValueError:
        return ""


def _skin_names(weapon: bytes, records: dict) -> list[str]:
    """Labels and internal names of the skins a weapon record lists (for the vote above)."""
    from src.operator_registry import TEXT_TAG

    out = []
    for entry in dict.fromkeys(_u64(weapon, o) for o in range(len(weapon) - 8)):
        if entry not in records or records[entry][0].file_type != SKIN_ENTRY:
            continue
        item = records[entry][0].data
        for o in range(len(item) - 8):
            skin = records.get(_u64(item, o))
            if not skin or skin[0].file_type != SKIN_DEF:
                continue
            d, at = skin[0].data, 0
            while (at := d.find(TEXT_TAG, at)) >= 0:
                n = struct.unpack_from("<I", d, at + 4)[0]
                if 0 < n < 200:
                    out.append(d[at + 8:at + 8 + n].decode("utf-8", "replace").lstrip("!"))
                at += 4
            out += [m.group(1).decode() for m in re.finditer(rb"[\x05-\x60]\x00\x00\x00([A-Za-z0-9_\-]{5,96})\x00", d)]
    return [n for n in dict.fromkeys(out) if len(_norm(n)) >= 6 and _norm(n) not in ("placeholder", "remove")]


def _weapon_model(weapon: bytes, records: dict):
    """The installed model of a weapon: a model uid inside the appearance at +8."""
    from src.database import load_asset_index

    appearance = records.get(_u64(weapon, 8))
    if not appearance:
        return None
    data = appearance[0].data
    candidates = {_u64(data, o) for o in range(len(data) - 7)}
    index = load_asset_index(_database(), candidates)
    return next((r for u in dict.fromkeys(_u64(data, o) for o in range(len(data) - 7))
                 if (r := index.primary(u)) is not None and r.file_type in MODEL_TYPES), None)


def _sight_name(text: str) -> str:
    """RedDot → Red Dot, IRON SIGHT [PLACEHOLDER] → Iron Sight, EosHolo → Holo (the game's own words)."""
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", re.sub(r"\[.*?\]", "", text)).split()
    name = " ".join(w.capitalize() if w.isupper() and len(w) > 1 else w for w in words)
    return {"Eos Holo": "Holo"}.get(name, name)


def _has_meshes(model) -> bool:
    """Whether a model's meshes can be found: in the game's graph or its own bundle's. A few (Holo A, some iron
    sights, in the playgo archive) are in neither, so they can't be exported and aren't offered."""
    own = model.archive.with_suffix(".depgraphbin")
    return bool(_children().get(model.uid)) or (own.is_file() and bool(_read_children(str(own), own.stat().st_mtime_ns).get(model.uid)))


def _sights(weapon: bytes, records: dict) -> list[dict]:
    """A weapon's sights, one per model. Variants of one sight (three red dots…) get A, B, C as in the game."""
    out, models = [], set()
    for uid in dict.fromkeys(_u64(weapon, o) for o in range(len(weapon) - 7)):
        sight = records.get(uid)
        if not sight or sight[0].file_type != SIGHT:
            continue
        model = _weapon_model(sight[0].data, records)
        if model is None or model.uid in models:
            continue
        models.add(model.uid)
        data = sight[0].data
        ui = next((records[u][0].data for o in range(len(data) - 7) if (u := _u64(data, o)) in records and records[u][0].file_type == SIGHT_UI), b"")
        out.append({"uid": f"{uid:016X}", "name": _sight_name(_text(ui)), "model": f"{model.uid:016X}", "meshes": _has_meshes(model)})
    names = Counter(s["name"] for s in out)
    seen: Counter = Counter()
    for sight in out:
        if sight["name"] and names[sight["name"]] > 1:
            seen[sight["name"]] += 1
            sight["name"] += f" {chr(64 + seen[sight['name']])}"
    # lettered first, so Holo B stays Holo B when Holo A (no exportable mesh) isn't offered
    return sorted(({k: v for k, v in s.items() if k != "meshes"} for s in out if s["meshes"]), key=lambda s: (not s["name"], s["name"]))


def _mesh_parts(model):
    """The weapon's mesh parts, read through the dependency graph of the model's own bundle."""
    from src.cli import _load_database_model_index
    from src.depgraph import load_depgraph
    from src.model import decode_mesh_parts, resolve_geometry_records

    children = load_depgraph(model.archive.with_suffix(".depgraphbin"))
    index = _load_database_model_index(_database(), model.uid, children)
    return decode_mesh_parts(resolve_geometry_records(model.uid, children, index), {})


@functools.lru_cache(maxsize=16)
def _weapon_parts(model: str) -> tuple:
    """_mesh_parts by model uid, kept: every skin of a weapon goes on the same mesh."""
    from src.database import load_asset_index

    return tuple(_mesh_parts(load_asset_index(_database(), {int(model, 16)}).primary(int(model, 16))))


@functools.lru_cache(maxsize=8)  # the game's graph and the bundles' own ones
def _read_children(graph: str, modified: int) -> dict:
    from src.depgraph import load_depgraph

    return load_depgraph(Path(graph))


def _children() -> dict:
    """The installed game's dependency graph (models → meshes, materials…), read once."""
    graph = _game() / "datapc64_ondemand.depgraphbin"
    return _read_children(str(graph), graph.stat().st_mtime_ns)


def _magazine(weapon: bytes, records: dict) -> str:
    """The weapon's default magazine: a model of its own, since the body's magwell is empty."""
    for offset in range(len(weapon) - 7):
        part = records.get(_u64(weapon, offset))
        if part and part[0].file_type == MAGAZINE:
            model = _weapon_model(part[0].data, records)
            return f"{model.uid:016X}" if model else ""
    return ""


def _add_magazine(folder: Path, magazine: str, roles: dict) -> None:
    """Put the magazine next to the weapon's body (it hangs from a bone of its own glTF), in the skin's textures
    when there is a skin: the skins' sheets cover the magazine too."""
    if not magazine:
        return
    out = folder / "magazine"
    _export_model(int(magazine, 16), _children(), _database(), out)
    if not roles:
        return
    for gltf in out.rglob("*.gltf"):
        doc = json.loads(gltf.read_text(encoding="utf-8"))
        up = "../" * (len(gltf.relative_to(folder).parts) - 1)
        doc["images"] = [{"uri": up + roles[role]} for role in ("diffuse", "normal") if role in roles]
        doc["textures"] = [{"source": n} for n in range(len(doc["images"]))]
        for material in doc.get("materials", []):
            for slot in ("normalTexture", "occlusionTexture", "emissiveTexture"):  # they'd point at textures gone now
                material.pop(slot, None)
            material.setdefault("pbrMetallicRoughness", {}).pop("metallicRoughnessTexture", None)
            material["pbrMetallicRoughness"]["baseColorTexture"] = {"index": 0}
            if "normal" in roles:
                material["normalTexture"] = {"index": 1}
            if "specular" in roles:
                material.setdefault("extras", {})["siegePackedMaterialTexture"] = up + roles["specular"]
        gltf.write_text(json.dumps(doc), encoding="utf-8")


def _weapon_gltf(model: str, magazine: str, skin: str, folder: Path, low: bool = False) -> None:
    """A weapon as glTF: its installed mesh and magazine, in a skin from the download cache ("" = none)."""
    from src.gltf import write_gltf
    from . import dcache

    roles = dcache.textures(skin, folder, low) if skin else {}
    write_gltf(int(model, 16), _weapon_parts(model), folder, **roles)
    _add_magazine(folder, magazine, roles)


@method("operators.weapons")
def weapons(uid: str) -> list[dict]:
    """The operator's weapons (loadout slots), each with the skins of it the game has downloaded."""
    from src.model import load_asset_payload, read_mesh_bindings
    from . import dcache

    operator = _records().get(int(uid, 16))
    if not operator or not _database().is_file():
        return []
    records = _more_records()
    skins = [e for e in dcache.catalog() if e["kind"] == "skin"]
    data = operator[0].data
    base = 8 + struct.unpack_from("<I", data, 4)[0] * 8
    out, seen = [], set()
    for slot in range(2, 23):
        weapon_uid = _u64(data, base + 32 + slot * 37 + 4)
        weapon = records.get(weapon_uid)
        if weapon_uid in seen or not weapon or weapon[0].file_type != WEAPON:
            continue
        seen.add(weapon_uid)
        model = _weapon_model(weapon[0].data, records)
        if model is None:
            continue
        name_record = records.get(_u64(weapon[0].data, 423))
        label = _text(name_record[0].data) if name_record else ""
        bones = sorted({b for binding in read_mesh_bindings(load_asset_payload(model)).values() for b in binding.bone_ids})
        matched = match_skins(label, bones, _skin_names(weapon[0].data, records), skins)
        unique = {s["material"] + s["name"]: s for s in matched}.values()
        out.append({"uid": f"{weapon_uid:016X}", "name": label.replace("Name", "").strip(), "model": f"{model.uid:016X}",
                    "magazine": _magazine(weapon[0].data, records),
                    "code": next(iter(unique))["code"] if unique else "",
                    # universal: the same look on every weapon (UNISKIN sheets, camo patterns); the rest are this weapon's own
                    "skins": sorted(({"id": s["file"], "name": s["name"], "universal": bool(s.get("pattern")) or "UNISKIN" in s["material"].upper()}
                                     for s in unique), key=lambda s: s["name"].lower()),
                    "sights": _sights(weapon[0].data, records)})
    return out


_list_weapons = weapons  # `pack` takes a `weapons` argument, which hides the function there


# --------------------------------------------------------------- previews
# Blender renders a preview of every skin (on its weapon) and charm, once. A few Blenders stay open and take
# jobs as JSON lines, so a preview costs its export and ~0.2 s of rendering, not a Blender start.
PREVIEW_WORKERS = 2
_preview_jobs: queue.LifoQueue = queue.LifoQueue()  # newest first: the tab someone just opened
_preview_pending: set[str] = set()
_preview_workers: list[threading.Thread] = []
_preview_lock = threading.Lock()


def _preview_path(item: str, model: str) -> Path:
    return settings.HOME / "previews" / (re.sub(r"[^0-9a-zA-Z]", "", f"{model}{item or 'base'}") + ".webp")


def _data_uri(path: Path) -> str:
    return "data:image/webp;base64," + base64.b64encode(path.read_bytes()).decode()


def _richer(*renders: Path) -> Path:
    """Of a charm seen from both faces, the one with more going on: the front has the art, the back is plain."""
    from PIL import Image, ImageStat

    def detail(path: Path) -> float:
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            return ImageStat.Stat(rgba.convert("L"), mask=rgba.getchannel("A").point(lambda a: 255 if a > 128 else 0)).stddev[0]

    return max((r for r in renders if r.is_file()), key=detail)


def _preview_worker(blender: Path) -> None:
    """One Blender kept open: export an item small, hand it over, turn its render into the cached WebP."""
    import shutil
    import tempfile

    from PIL import Image
    from . import dcache

    work = Path(tempfile.mkdtemp(dir=settings.HOME / "previews"))
    script = Path(__file__).resolve().parent / "blender_thumbs.py"
    process, number = None, 0
    while True:
        item, model, magazine = _preview_jobs.get()
        path, uri, folder = _preview_path(item, model), "", work / str(number := number + 1)
        try:
            if process is None or process.poll() is not None:
                process = subprocess.Popen([str(blender), "--background", "--factory-startup", "--python", str(script), "--", "-"],
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                           encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if model:
                _weapon_gltf(model, magazine, item, folder, low=True)
            else:
                dcache.charm_gltf(item, folder, low=True)
            render = folder / "preview.png"
            process.stdin.write(json.dumps({"folder": str(folder), "out": str(render), "kind": "weapon" if model else "charm"}) + "\n")
            process.stdin.flush()
            for line in process.stdout:
                if line.startswith("THUMB "):
                    break
            if render.is_file():
                with Image.open(_richer(render, Path(f"{render}.back.png"))) as image:
                    image.save(path, quality=86)
                uri = _data_uri(path)
        except (ValueError, KeyError, OSError, StopIteration, AttributeError, struct.error) as error:
            print(f"No preview for {item or model}: {error}", file=sys.stderr)
        finally:
            shutil.rmtree(folder, ignore_errors=True)
            with _preview_lock:
                _preview_pending.discard(f"{model}/{item}")
        emit("operators.preview", {"id": item, "model": model, "uri": uri})


@method("operators.thumbs")
def thumbs(ids: list[str], model: str = "", magazine: str = "") -> dict[str, str]:
    """Previews as data URIs: charms, or with `model` (and its `magazine`) the skins of that weapon ("" = none).
    The ones made before come back at once; Blender renders the others in the background and each one arrives
    as an operators.preview event. Without Blender, the item's texture stands in."""
    from . import dcache

    (settings.HOME / "previews").mkdir(parents=True, exist_ok=True)
    out, missing = {}, []
    for item in ids:
        path = _preview_path(item, model)
        (out.__setitem__(item, _data_uri(path)) if path.is_file() else missing.append(item))
    blender, _ = env.find_blender()
    if blender is None:
        for item in (i for i in missing if i):
            try:
                dcache.thumbnail(item, _preview_path(item, model))
                out[item] = _data_uri(_preview_path(item, model))
            except (ValueError, KeyError, OSError, StopIteration, struct.error) as error:
                print(f"No preview for {item}: {error}", file=sys.stderr)
        return out
    with _preview_lock:
        for item in reversed(missing):  # a LIFO queue: this way the first one asked comes out first
            if f"{model}/{item}" not in _preview_pending:
                _preview_pending.add(f"{model}/{item}")
                _preview_jobs.put((item, model, magazine))
        while missing and len(_preview_workers) < PREVIEW_WORKERS:
            worker = threading.Thread(target=_preview_worker, args=(blender,), daemon=True)
            worker.start()
            _preview_workers.append(worker)
    return out


# ------------------------------------------------------------------ packs

@method("operators.pack")
def pack(uid: str, items: list[str], weapons: list[dict] | None = None, charms: list[str] | None = None) -> dict:
    """Export what was picked for an operator, then have Blender build one .blend with all of it.

    items: uniform and headgear uids; weapons: [{"uid", "skins": [cache ids, "" = no skin], "sights": [sight uids]}];
    charms: cache ids.
    """
    from . import dcache

    _game()
    if not _database().is_file():
        raise Failure("error.noIndex")
    operator = _operator(uid)
    records = _records()
    everything = cosmetics(uid)
    numbered = {i["uid"]: (i, n) for kind in ("uniform", "headgear") for n, i in enumerate(everything[kind], 1)}
    picked = [numbered[i] for i in items if i in numbered]
    if not any(i["kind"] == "uniform" for i, _ in picked) or not any(i["kind"] == "headgear" for i, _ in picked):
        raise Failure("error.packNeedsBoth")
    target = _pack_folder(operator.name)
    jobs, manifest = [], {"name": operator.name, "items": []}
    for item, number in picked:
        appearance = records.get(_u64(records[int(item["uid"], 16)][0].data, 8))
        if not appearance:
            continue
        folder = target / ("uniforms" if item["kind"] == "uniform" else "headgear") / item["uid"]
        jobs += [("model", folder, model) for model in _primary_models(appearance[0].data)]
        manifest["items"].append({"kind": item["kind"], "name": _item_name(item, number), "folder": str(folder)})
    # weapons to the operator's right, one above the other; charms further right in a row
    known = {w["uid"]: w for w in (_list_weapons(uid) if weapons else [])}
    for row, choice in enumerate(w for w in weapons or [] if w.get("uid") in known):
        weapon = known[choice["uid"]]
        title = weapon["name"] or weapon["code"] or f"Weapon {row + 1}"
        names = {s["id"]: s["name"] for s in weapon["skins"]}
        for skin in choice.get("skins") or ([] if choice.get("sights") else [""]):
            # short, readable folders: Windows (and Blender with it) can't open paths past 260 characters
            folder = target / "weapons" / _folder_name(title)[:40] / (_folder_name(names.get(skin, ""))[:40] if skin else "base")
            jobs.append(("weapon", folder, (weapon["model"], weapon["magazine"], skin)))
            manifest["items"].append({"kind": "weapon", "group": title, "name": f"{title} · {names.get(skin, 'no skin')}",
                                      "folder": str(folder), "offset": [0.75, 0.0, 1.3 - row * 0.3]})
        sights = {s["uid"]: s for s in weapon["sights"]}
        # sights in the weapon's row, to its right, one after the other
        for column, sight in enumerate(sights[s] for s in choice.get("sights") or [] if s in sights):
            label = sight["name"] or sight["uid"]
            folder = target / "sights" / _folder_name(title)[:40] / _folder_name(label)[:40]
            jobs.append(("model", folder, int(sight["model"], 16)))
            manifest["items"].append({"kind": "sight", "group": title, "name": f"{title} · {label}", "folder": str(folder),
                                      "offset": [1.25 + column * 0.12, 0.0, 1.3 - row * 0.3]})
    charm_names = {c["id"]: c["name"] for c in dcache.charms()} if charms else {}
    for column, charm in enumerate(c for c in charms or [] if c in charm_names):
        folder = target / "charms" / _folder_name(charm_names[charm])
        jobs.append(("charm", folder, charm))
        manifest["items"].append({"kind": "charm", "name": charm_names[charm], "folder": str(folder),
                                  "offset": [2.4 + (column % 6) * 0.12, 0.0, 1.3 - (column // 6) * 0.15]})
    if not _busy.acquire(blocking=False):
        raise Failure("error.opBusy")
    try:
        children = _children()
        for done, (kind, folder, what) in enumerate(jobs):
            emit("operators.progress", {"step": "export", "uid": uid, "done": done, "total": len(jobs), "file": folder.name})
            if any(folder.rglob("*.gltf")):
                continue  # exported by an earlier pack
            try:
                if kind == "model":
                    _export_model(what, children, _database(), folder / f"{what:016X}")
                elif kind == "weapon":
                    _weapon_gltf(*what, folder)
                else:
                    dcache.charm_gltf(what, folder)
            except (FileNotFoundError, ValueError, KeyError, struct.error) as error:
                raise Failure(f"{operator.name}: {folder.name} failed ({error})") from error
        blend = _build_blend(uid, target, manifest)
    finally:
        _busy.release()
    emit("operators.progress", {"step": "done", "uid": uid, "done": 1, "total": 1, "file": ""})
    return {"folder": str(target), "blend": str(blend) if blend else "", "items": len(manifest["items"])}


def _build_blend(uid: str, target: Path, manifest: dict) -> Path | None:
    """Blender in the background: one collection per uniform and headgear, the first of each visible."""
    blender, _ = env.find_blender()
    if blender is None:
        return None  # the glTF files are there all the same
    blend = target / f"{_folder_name(manifest['name'])}.blend"
    spec = target / "pack.json"
    spec.write_text(json.dumps({**manifest, "blend": str(blend)}, indent=1), encoding="utf-8")
    script = Path(__file__).resolve().parent / "blender_pack.py"
    process = subprocess.Popen(
        [str(blender), "--background", "--factory-startup", "--python", str(script), "--", str(PARSER / "blender_addon"), str(spec)],
        # its own empty stdin: inheriting the engine's (the window's request pipe) stops Blender before the script
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    with open(target / "blender.log", "w", encoding="utf-8") as log:  # kept next to the pack, for when it fails
        for raw in process.stdout:
            line = raw.decode("utf-8", "replace").rstrip()
            log.write(line + "\n")
            if line.startswith("PACK "):
                done, total = (int(x) for x in line.split()[1].split("/"))
                emit("operators.progress", {"step": "blend", "uid": uid, "done": done, "total": total, "file": ""})
    if process.wait() != 0 or not blend.is_file():
        raise Failure("error.blendFailed")
    return blend


@method("operators.blender")
def open_in_blender(path: str) -> bool:
    """Open a pack's .blend in Blender."""
    blender, _ = env.find_blender()
    if blender is None:
        raise Failure("error.noBlender")
    if not Path(path).is_file():
        raise Failure("error.notExported")
    subprocess.Popen([str(blender), path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))  # not on the engine's pipes (see above)
    return True
