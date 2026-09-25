"""Retired weapon skins, charms and sights from old builds: Glacier, Year 1's charms, the Holo A and the rest today's
game neither installs nor streams.

An old build (Forge v29, e.g. Y2S3 Blood Orchid) still has them installed, and asset uids haven't changed since:
many weapons keep the very same body mesh, so the old textures fit today's mesh as they are. Everything comes from
the old build's own registry (datapc64.forge, entry 0x800), nothing is guessed from pictures:

- objects: [u32 type][u32 size][u32 0][u64 uid][u32 type] + properties; a link is [u64 id][u32 7855A3D0][u32 1][u64 target]
- weapon names: [u64 id][u32 6C7B8D30][u64 weapon key][u32 len][name]            W_AR_RemingtonR4C
- set names: [u32 7855A3D0][u32 1][u64 set][u64 id][u32 7855A3D0][u32 0][u32 len][name]   R6Unique_Esports1 = Glacier
- a weapon's skins (328A37EF): 1st link = the weapon key, then [7855A3D0][0][u32 n][n x u64 entry]
- a skin entry (8D1D966B): 1st link = its set; its body names the skin's texture node (22ECBE63), or, for the default
  look, the 971A842E prefabs, whose depgraph children include the weapon's body mesh: that ties the old weapon to
  today's (same mesh uid), and the mesh is compared vertex by vertex before any old skin is offered.
- a texture node's file embeds its objects one after the other: for each mesh, a mesh object (415D9568) naming the mesh
  and then one material (85C817C3) per slot, in slot order; a material starts with its tint (4 floats, RGBA: the colour
  the game multiplies its colour sheet by) and names texture specs (989DC6B2) whose sets (A2B7E917) name the maps.

An old skin meets today's catalog through its icons: the old build's UI objects name a skin's token with its GUI texture
specs, and today's skin definitions still carry those very uids, renamed skins included (Masonry Amber is Ruby now).
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
import threading
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from . import legacy, operators, settings
from .rpc import emit, method

LINK, NAME, SKIN_LIST, SKIN_ENTRY = 0x7855A3D0, 0x6C7B8D30, 0x328A37EF, 0x8D1D966B
MESH, SKIN_NODE, PREFAB = 0xABEB2DFB, 0x22ECBE63, 0x971A842E
UI, ICON = 0x51066FDD, 0x989DC6B2  # a skin's UI object and its icons (GUI texture specs, 4F09331E today)
QUALITY = {0xD7B5C478: 0, 0xF9C80707: 1, 0x59CE4D13: 2, 0x9F492D22: 3}  # low, medium, high, ultra
MESH_OBJECT, MATERIAL, TEXTURE_SET = 0x415D9568, 0x85C817C3, 0xA2B7E917  # what a texture node embeds (above)
OLD = "old:"  # a skin's `file` when its textures come from an old build: old:<build key>:<texture node uid>
OWN_MESH = ":mesh"  # …ending so when they go on the old build's own weapon mesh (today's was redone since)
OLD_CHARM = "oldcharm:"  # a charm's, from an old build: oldcharm:<build key>:<icon uid>
OLD_SIGHT = "oldsight:"  # a sight's, from an old build: oldsight:<build key>:<today's model uid>
VERSION = 12  # of the cache below (7: charms, 8: sights, 9: a charm's own parts, 12: materials and tints)


# ------------------------------------------------------------------ format

def _index(folder: Path) -> dict[int, tuple[str, int, int, int]]:
    """uid → (archive, offset, size, file type) of every v29 archive of a build (types from its meta table)."""
    out = {}
    for path in sorted(folder.glob("*.forge")):
        with open(path, "rb") as f:
            head = f.read(0x60)
            if head[:9] != b"scimitar\x00" or struct.unpack_from("<I", head, 9)[0] >= 34:
                continue  # not a Forge archive, or today's format
            tables, position = struct.unpack_from("<IQ", head, 0x3E)
            for _ in range(tables):
                f.seek(position)
                header = f.read(0x28)
                count, _, fat, following = struct.unpack_from("<iiqq", header)
                meta = struct.unpack_from("<q", header, 0x20)[0]
                f.seek(fat)
                table = f.read(20 * count)
                f.seek(meta)
                metas = f.read(0x140 * count)
                for i in range(count):
                    offset, uid, size = struct.unpack_from("<QQI", table, 20 * i)
                    out.setdefault(uid, (path.name, offset, size, struct.unpack_from("<I", metas, 0x140 * i + 0x10)[0]))
                if following == -1:
                    break
                position = following
    return out


def _depgraph(folder: Path) -> dict[int, list[int]]:
    """Children by parent from every v29 depgraphbin: one Zstandard block, a flag byte, then (parent, child, _)."""
    children = defaultdict(list)
    for path in folder.glob("*.depgraphbin"):
        blob = path.read_bytes()
        chunks, _ = legacy._block_chunks(blob, 0)
        body = b"".join(legacy._inflate(blob, c) for c in chunks)[1:]
        for parent, child, _ in struct.iter_unpack("<QQQ", body[:len(body) // 24 * 24]):
            children[parent].append(child)
    return children


def _links(body: bytes) -> list[int]:
    return [struct.unpack_from("<Q", body, m.end())[0] for m in re.finditer(re.escape(struct.pack("<II", LINK, 1)), body)
            if m.end() + 8 <= len(body)]


def _objects(registry: bytes, kind: int, limit: int = 1 << 24) -> dict[int, bytes]:
    tag, out = struct.pack("<I", kind), {}
    for m in re.finditer(re.escape(tag), registry):
        p = m.start()
        size = struct.unpack_from("<I", registry, p + 4)[0] if p + 8 <= len(registry) else 0
        if registry[p + 20:p + 24] == tag and registry[p + 8:p + 12] == b"\0\0\0\0" and size <= limit:
            out[struct.unpack_from("<Q", registry, p + 12)[0]] = registry[p + 24:p + 12 + size]
    return out


def _names(registry: bytes, pattern: bytes, key_at: int, len_at: int) -> dict[int, str]:
    out = {}
    for m in re.finditer(re.escape(pattern), registry):
        p = m.start()
        if p + len_at + 4 > len(registry):
            continue
        n = struct.unpack_from("<I", registry, p + len_at)[0]
        if not 0 < n < 120:  # before slicing: most matches aren't names, and a stray length would copy megabytes
            continue
        text = registry[p + len_at + 4:p + len_at + 4 + n]
        if all(32 <= c < 127 for c in text):
            out.setdefault(struct.unpack_from("<Q", registry, p + key_at)[0], text.decode())
    return out


def _u64s(data: bytes) -> set[int]:
    return {struct.unpack_from("<Q", data, i)[0] for i in range(len(data) - 7)}


def _items(body: bytes) -> list[int]:
    """The uids a list (328A37EF) holds: [7855A3D0][0][u32 n][n x u64] after its links."""
    start = body.find(struct.pack("<II", LINK, 0), body.find(struct.pack("<II", LINK, 1)) + 16)
    if start < 0 or start + 12 > len(body):
        return []
    count = min(struct.unpack_from("<I", body, start + 8)[0], (len(body) - start - 12) // 8)
    return list(struct.unpack_from(f"<{count}Q", body, start + 12))


def _body(folder: Path, files: dict, uid: int) -> bytes:
    archive, offset, size, _ = files[uid]
    with open(folder / archive, "rb") as f:
        f.seek(offset)
        return legacy.asset_data(f.read(size))


_OBJECT = re.compile(rb"(?=(.{4})(.{4})\x00\x00\x00\x00(.{8})\1)", re.S)  # [type][size][0][uid][type]


def _embedded(body: bytes) -> dict[int, tuple[int, int, int]]:
    """The objects a file embeds one after the other: {uid: (start, end, type)}."""
    out = {}
    for m in _OBJECT.finditer(body):
        kind, size = struct.unpack("<II", m.group(1) + m.group(2))
        if kind and 12 <= size <= len(body) - m.start() - 12:
            out.setdefault(int.from_bytes(m.group(3), "little"), (m.start(), m.start() + 12 + size, kind))
    return out


def _named(body: bytes, start: int, end: int) -> list[int]:
    """Every u64 an object's properties hold, in order (the uids it names are among them)."""
    return [struct.unpack_from("<Q", body, at)[0] for at in range(start + 24, end - 7)]


def _tint(body: bytes, start: int) -> list[float]:
    return [round(x, 4) for x in struct.unpack_from("<4f", body, start + 24)]


def _slots(folder: Path, files: dict, node: int, meshes: list[int], listed_by: dict) -> dict | None:
    """A charm's materials slot by slot for each of its meshes, from its texture node: {mesh: [{"textures": maps,
    "tint": RGBA}]}; None when the node doesn't hold them all. The tint is the colour the game multiplies the colour
    sheet by: gold for the gold chibis, the metals of the ranked charms, Velvet Shell's purple plume."""
    body = _body(folder, files, node)
    objects = _embedded(body)
    kind = lambda uid: objects[uid][2] if uid in objects else None  # noqa: E731
    named = lambda uid: _named(body, *objects[uid][:2])  # noqa: E731
    out = {}
    for uid, (_, _, what) in objects.items():
        mesh = next((u for u in named(uid) if u in meshes), None) if what == MESH_OBJECT else None
        materials = [u for u in named(uid) if kind(u) == MATERIAL] if mesh is not None else []
        if materials:
            out[f"{mesh:016X}"] = [
                {"textures": _maps(folder, files, {u for spec in named(material) if kind(spec) == ICON for s in named(spec)
                                                    if kind(s) == TEXTURE_SET for u in named(s) if u in files and files[u][3] in QUALITY}, listed_by),
                 "tint": _tint(body, objects[material][0])}
                for material in materials]
    return out if len(out) == len(meshes) else None


def _skin_tint(folder: Path, files: dict, node: int) -> list[float] | None:
    """The tint a weapon skin's texture node gives its colour sheet (Masonry Ruby's red, Topaz's orange): the one its
    materials share; None when it's white or they differ (which part of today's mesh wears which isn't known)."""
    body = _body(folder, files, node)
    tints = {tuple(_tint(body, start)) for start, _, kind in _embedded(body).values() if kind == MATERIAL}
    return list(next(iter(tints))) if len(tints) == 1 and tints != {(1.0, 1.0, 1.0, 1.0)} else None


def _maps(folder: Path, files: dict, children, listed_by: dict) -> dict:
    """A texture node's colour, normal and specular maps by quality (from its children). A node can list two maps of
    one role and quality: its own, and a small detail map every node of that skin shares (Onami's normal): the one
    fewest nodes list is the node's, the larger one if that doesn't decide. "several": it has more than one colour
    sheet (a charm whose parts are painted from different sheets)."""
    found: dict[tuple[str, int], list[tuple[int, int, int]]] = defaultdict(list)
    for child in children:
        if child in files and files[child][3] in QUALITY:
            archive, offset, size, kind = files[child]
            with open(folder / archive, "rb") as f:
                info = legacy.texture_info(f, offset, size)
            if info and info["kind"] in ("color", "normal", "specular"):
                found[(info["kind"], QUALITY[kind])].append((listed_by[child], -info["width"] * info["height"], child))
    roles: dict = defaultdict(dict)
    for (role, quality), options in found.items():
        roles[role][quality] = f"{min(options)[2]:016X}"
        if role == "color" and len(options) > 1:
            roles["several"] = True
    return dict(roles)


def _read(folder: Path) -> dict:
    """What an old build has that today's game lacks: every weapon with the meshes of its default look and its
    skins (each with its texture nodes and icons), the texture maps of those nodes, and every charm by its icons
    with its meshes and maps."""
    files, graph = _index(folder), _depgraph(folder)
    kind = lambda uid: files[uid][3] if uid in files else None  # noqa: E731
    archive, offset, size, _ = files[0x800]
    with open(folder / archive, "rb") as f:
        f.seek(offset)
        registry = legacy.asset_data(f.read(size))
    weapons = _names(registry, struct.pack("<I", NAME), 4, 12)
    entries, lists = _objects(registry, SKIN_ENTRY), _objects(registry, SKIN_LIST)
    ui_bodies = list(_objects(registry, UI, limit=8192).values())
    ui = [_u64s(body) for body in ui_bodies]
    token = {uid: links[0] for uid, body in entries.items() if (links := _links(body))}
    # A skin's icons: UI objects name its token (and often its weapon) together with its GUI texture specs, and
    # those uids are still today's (a skin definition names them): the one thing old and new builds share for a
    # skin, renamed or not. The (weapon, token) pair decides; the token alone is the fallback (a few are shared).
    pair, alone, tokens = defaultdict(set), defaultdict(set), set(token.values())
    for refs in ui:
        shown = {u for u in refs if kind(u) == ICON}
        for t in refs & tokens:
            alone[t] |= shown
            for w in refs & weapons.keys():
                pair[(w, t)] |= shown
    out, nodes = [], set()
    for body in lists.values():
        links = _links(body)
        if not links or links[0] not in weapons:
            continue
        listed = [u for u in _items(body) if u in entries]
        refs = {u: _u64s(entries[u]) for u in listed}
        prefabs = {u for r in refs.values() for u in r if kind(u) == PREFAB}
        meshes = sorted({c for p in prefabs for c in graph.get(p, ()) if kind(c) == MESH})
        looks = []
        for entry in listed:
            # every texture node the entry names, in its own order (a few name a shared, empty one first)
            candidates = sorted((u for u in refs[entry] if kind(u) == SKIN_NODE), key=lambda u: entries[entry].find(struct.pack("<Q", u)))
            icons = pair.get((links[0], token.get(entry))) or alone.get(token.get(entry)) or set()
            if candidates and icons:
                looks.append({"nodes": [f"{u:016X}" for u in candidates], "icons": sorted(f"{i:016X}" for i in icons)})
                nodes.update(candidates)
        if meshes and looks:
            out.append({"name": weapons[links[0]], "meshes": [f"{m:016X}" for m in meshes], "looks": looks})
    listed_by = defaultdict(int)
    for node in nodes:
        for child in graph.get(node, ()):
            listed_by[child] += 1
    textures = {f"{node:016X}": roles for node in nodes if (roles := _maps(folder, files, graph.get(node, ()), listed_by)).get("color")}
    for node, roles in textures.items():
        if tint := _skin_tint(folder, files, int(node, 16)):
            roles["tint"] = tint
    sights = {model: list(meshes) for model, meshes in EOTECH.items() if all(kind(int(m, 16)) == MESH for m in meshes)}
    return {"weapons": out, "textures": textures, "charms": _charms(folder, files, graph, entries, lists, ui_bodies, ui, weapons),
            "sights": sights}


def _charms(folder: Path, files: dict, graph: dict, entries: dict, lists: dict, ui_bodies: list[bytes], ui: list[set[int]],
            weapons: dict) -> dict:
    """The charms of an old build (Year 1's and every other it installed), by icon: {icon: {"meshes", "textures"}}.
    A charm is registered like a skin, keyed by its own token instead of a weapon: a UI object links the token and
    names the icons (the uids today's charm UI record, CHARM +62, still names); a list whose first link is the token
    holds the charm's entry, nested one or two lists deeper for the chibis; the entry's texture node lists the
    mesh (two for a few: Amaebi, the Platinum ones) and the maps. Headgear and uniforms of the time are registered
    the same way and come out too: only icons today's charms name are ever used."""
    kind = lambda uid: files[uid][3] if uid in files else None  # noqa: E731
    icons_of = defaultdict(set)
    for body, refs in zip(ui_bodies, ui):
        shown = {u for u in refs if kind(u) == ICON}
        for t in _links(body):
            icons_of[t] |= shown
    found = {}
    for body in lists.values():
        links = _links(body)
        if not links or links[0] in weapons or not icons_of.get(links[0]):
            continue
        held, frontier = [], _items(body)
        for _ in range(3):
            held += [u for u in frontier if u in entries]
            frontier = [i for u in frontier if u in lists for i in _items(lists[u])]
        for entry in held:
            for node in (u for u in _u64s(entries[entry]) if kind(u) == SKIN_NODE):
                meshes = sorted(c for c in graph.get(node, ()) if kind(c) == MESH)
                if meshes:
                    found[links[0]] = (node, meshes)
    # A few charms' nodes list another charm's whole node before their own parts (Dust Line Platinum holds Zombie
    # Bunny's, Amaebi Kabuto's): what a node lists that a smaller node lists too isn't its own.
    kids = {token: set(graph.get(node, ())) for token, (node, _) in found.items()}
    own = {token: mine - set().union(*(k for other, k in kids.items() if other != token and k < mine)) for token, mine in kids.items()}
    listed_by = defaultdict(int)
    for children in own.values():
        for child in children:
            listed_by[child] += 1
    out = {}
    for token, children in own.items():
        meshes = sorted(c for c in children if kind(c) == MESH)
        roles = _maps(folder, files, children, listed_by)
        if meshes and roles.get("color"):
            charm = {"meshes": [f"{m:016X}" for m in meshes], "textures": roles}
            if slots := _slots(folder, files, found[token][0], meshes, listed_by):
                charm["slots"] = slots
            for icon in icons_of[token]:
                out[f"{icon:016X}"] = charm
    return out


# ------------------------------------------------------------------ builds

_lock = threading.Lock()  # one reader per build at a time; the cache file is written under it too
_failed: dict[tuple[str, str], str] = {}  # (folder, stamp) → why it couldn't be read: not tried again until it changes


def label(folder: Path) -> str:
    """The season an old build is (Y2S3), from its folder or a parent (the Vault keeps library/<season>/<manifest>)."""
    found = next((m for part in reversed(folder.parts) if (m := re.search(r"Y\d+S\d", part, re.I))), None)
    return found[0].upper() if found else folder.name


def _key(folder: Path) -> str:
    return hashlib.sha1(str(folder).lower().encode()).hexdigest()[:16]


def _cache(folder: Path) -> Path:
    return settings.HOME / "retired" / f"{_key(folder)}.json"


def stamp(folder: Path) -> str:
    """Every archive and graph of the build, by name, size and time: a Vault download that grows is read again."""
    files = sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in [*folder.glob("*.forge"), *folder.glob("*.depgraphbin")])
    return f"{VERSION}:" + hashlib.sha1(json.dumps(files).encode()).hexdigest()


def _old_registry(folder: Path) -> bool:
    """A registry (datapc64.forge) in the old format (Forge before v34: today's game folder won't do)."""
    try:
        with open(folder / "datapc64.forge", "rb") as f:
            head = f.read(13)
    except OSError:
        return False
    return head[:9] == b"scimitar\x00" and struct.unpack_from("<I", head, 9)[0] < 34


def builds() -> list[Path]:
    """The old builds set in Settings that are there and have an old-format registry."""
    return [Path(p) for p in settings.load()["old_builds"] if _old_registry(Path(p))]


@method("retired.builds")
def usable() -> list[str]:
    """The old builds Reliquary can use, so Settings can mark the others."""
    return [str(p) for p in builds()]


def load(folder: Path) -> dict:
    """What an old build holds, read once and kept in Reliquary's folder (the build itself is never written to)."""
    with _lock:
        path, now = _cache(folder), stamp(folder)
        if (str(folder), now) in _failed:
            raise ValueError(_failed[(str(folder), now)])
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("stamp") == now:
                return saved
        except (OSError, ValueError):
            pass
        try:
            data = {"folder": str(folder), "stamp": now, **_read(folder), "same": {}}
        except Exception as error:  # a partial or foreign build: say why once, don't read it again for every weapon
            _failed[(str(folder), now)] = f"{type(error).__name__}: {error}"
            raise
        _save(path, data)
        return data


def _save(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + ".part")
        part.write_text(json.dumps(data), encoding="utf-8")
        part.replace(path)
    except OSError as error:  # only a cache: the next run works it out again
        print(f"Old build cache {path.name}: {error}", file=sys.stderr)


def _same_mesh(folder: Path, mesh: int) -> bool:
    """Whether the old build's mesh is today's, vertex for vertex (positions and UVs): only then do its skins fit."""
    from src.database import load_asset_index
    from src.mesh import read_mesh_with_islands
    from src.model import decode_mesh_parts

    files = _index(folder)
    if mesh not in files:
        return False
    archive, offset, size, _ = files[mesh]
    with open(folder / archive, "rb") as f:
        f.seek(offset)
        data = legacy.asset_data(f.read(size))
    at = data.find(struct.pack("<I", 0xFC9E1595))
    old_vertices, old_uvs, *_ = read_mesh_with_islands(data[at:at + 8 + struct.unpack_from("<I", data, at + 4)[0]])
    parts = decode_mesh_parts(load_asset_index(operators._database(), {mesh}).records(), {})
    if len(parts) != 1:
        return False
    new = parts[0]
    return (len(old_vertices) == len(new.vertices) and len(old_uvs) == len(new.uvs)
            and all(tuple(a) == tuple(b) for a, b in zip(old_uvs, new.uvs))
            and all(tuple(a) == tuple(b) for a, b in zip(old_vertices, new.vertices)))


def _identical(folder: Path, data: dict, meshes: set[int]) -> bool:
    """Every one of today's meshes identical in the old build; remembered per game build (an update can change
    today's side), and not remembered when the comparison itself failed."""
    game = str((operators._game() / "datapc64.forge").stat().st_mtime_ns)
    if data["same"].get("game") != game:
        data["same"] = {"game": game}
    fresh = False
    for mesh in (f"{m:016X}" for m in sorted(meshes)):
        if mesh not in data["same"]:
            try:
                data["same"][mesh] = _same_mesh(folder, int(mesh, 16))
                fresh = True
            except Exception as error:
                print(f"Old build {folder}, mesh {mesh}: {error}", file=sys.stderr)
                return False
        if not data["same"][mesh]:
            break
    if fresh:
        with _lock:
            _save(_cache(folder), data)
    return all(data["same"].get(f"{m:016X}") for m in meshes)


def for_weapon(meshes: set[int], loaded: list[tuple[Path, dict]]) -> list[tuple[set[int], str, str, str]]:
    """The old skins of a weapon of today (its body meshes), from the builds `loaded` read:
    [(icon uids, file, season label, look)]. An old weapon is today's when it has every one of today's mesh uids
    (one shared uid isn't enough: today's Bearing 9 shares one with 2017's AUG). When each is identical, vertex for
    vertex, the old textures go on today's mesh; when the mesh was redone since (a few vertices, the UVs: G36C,
    AUG, MP5…), on the old build's own mesh (file ends with OWN_MESH), which is today's shape in today's place. The
    look (colour sheet and tint) lets catalog.join_old leave out two skins that would come out the same."""
    out: list[tuple[set[int], str, str, str]] = []
    for folder, data in loaded:
        for weapon in data["weapons"]:
            if not meshes or not meshes <= {int(m, 16) for m in weapon["meshes"]}:
                continue
            own = "" if _identical(folder, data, meshes) else OWN_MESH
            for look in weapon["looks"]:
                node = next((n for n in look["nodes"] if n in data["textures"]), None)
                if node:
                    roles = data["textures"][node]
                    sheet = ",".join(sorted(roles["color"].values())) + (f" x {roles['tint']}" if roles.get("tint") else "")
                    out.append(({int(i, 16) for i in look["icons"]}, f"{OLD}{_key(folder)}:{node}{own}", label(folder), sheet))
    return out


def charms(loaded: list[tuple[Path, dict]]) -> dict[int, tuple[str, str]]:
    """The old builds' charms by icon uid: {icon: (file, season label)}, the first build that has one wins."""
    out: dict[int, tuple[str, str]] = {}
    for folder, data in loaded:
        for icon in data.get("charms", {}):
            out.setdefault(int(icon, 16), (f"{OLD_CHARM}{_key(folder)}:{icon}", label(folder)))
    return out


def available(file: str) -> bool:
    """Whether the old build an old skin or charm comes from is still set in Settings and there."""
    return any(_key(folder) == file.split(":")[1] for folder in builds())


def loaded(announce: bool = False) -> list[tuple[Path, dict]]:
    """Every old build that reads, read once for a whole run (a minute or so each the first time, then from the
    cache); announce: with its own step on Prepare's bar."""
    folders, out = builds(), []
    for done, folder in enumerate(folders):
        if announce:
            emit("operators.progress", {"step": "old", "done": done, "total": len(folders), "file": folder.name})
        try:
            out.append((folder, load(folder)))
        except Exception as error:  # an unreadable or partial build shouldn't cost the rest
            print(f"Old build {folder}: {error}", file=sys.stderr)
    return out


def textures(file: str, out: Path) -> dict[str, str]:
    """Colour (in its tint), normal and specular of an old skin, the best quality its build has, saved as PNG in `out`."""
    key, node = file[len(OLD):].split(":")[:2]
    folder = next((f for f in builds() if _key(f) == key), None)
    roles = load(folder)["textures"].get(node) if folder else None
    if not roles:
        raise ValueError(f"the old build of skin {node} isn't in Settings any more")
    return _save_maps(folder, _index(folder), roles, out, roles.get("tint"))


def weapon_gltf(file: str, meshes: set[int], model: int, out: Path, maps: dict[str, str]) -> Path | None:
    """Today's meshes of a weapon (body or magazine, by uid) as the old build of an old skin has them, in the skin's
    maps from `textures`: the old sheets fit the old UVs, and the old meshes have today's shape and place (see
    for_weapon). None when that build doesn't have every one of them."""
    from src.gltf import write_gltf

    folder = next((f for f in builds() if _key(f) == file[len(OLD):].split(":")[0]), None)
    files = _index(folder) if folder else {}
    if not meshes or not meshes <= files.keys():
        return None
    return write_gltf(model, _parts(folder, files, [f"{m:016X}" for m in sorted(meshes)]), out, **maps)


def charm_gltf(file: str, out: Path) -> Path:
    """An old charm as glTF: its mesh(es) from the old build, read by R6-parser's mesh reader, in its own maps."""
    from src.gltf import write_gltf

    key, _, icon = file[len(OLD_CHARM):].partition(":")
    folder = next((f for f in builds() if _key(f) == key), None)
    charm = load(folder).get("charms", {}).get(icon) if folder else None
    if not charm:
        raise ValueError(f"the old build of charm {icon} isn't in Settings any more")
    from src.gltf import MaterialTextures

    files = _index(folder)
    parts = _parts(folder, files, charm["meshes"])
    # skinned charms keep their bind pose far from the origin (up to metres): hang each one from it, as today's are
    points = [v for part in parts for v in part.vertices]
    shift = ((min(p[0] for p in points) + max(p[0] for p in points)) / 2, (min(p[1] for p in points) + max(p[1] for p in points)) / 2,
             max(p[2] for p in points))
    parts = [replace(part, vertices=tuple((x - shift[0], y - shift[1], z - shift[2]) for x, y, z in part.vertices)) for part in parts]
    if charm.get("slots"):
        # every slot in its own maps and tint, a mesh's slots after the previous mesh's; where a mesh has a slot more
        # than its node lists materials (the regular chibis), it wears the last one there, as it always did
        materials, placed = [], []
        for part, mesh in zip(parts, charm["meshes"]):
            slots, top = charm["slots"][mesh], len(charm["slots"][mesh]) - 1
            placed.append(replace(part, islands=tuple(replace(i, material_id=len(materials) + min(i.material_id, top)) for i in part.islands)))
            for slot in slots:
                maps = _save_maps(folder, files, slot["textures"], out, slot["tint"])
                materials.append(MaterialTextures(**maps, solid_color=None if "diffuse" in maps else tuple(slot["tint"])))
        return write_gltf(int(icon, 16), placed, out, material_textures=materials)
    maps = _save_maps(folder, files, charm["textures"], out)
    if not charm["textures"].get("several"):
        return write_gltf(int(icon, 16), parts, out, **maps)
    # parts painted from different sheets: which sheet goes where isn't known, so only the main part (the most
    # faces) gets the colour sheet and the others stay a plain grey rather than wearing the wrong one
    faces = defaultdict(int)
    for part in parts:
        for island in part.islands:
            faces[island.material_id] += len(island.faces)
    main = max(faces, key=faces.get)
    slots = [MaterialTextures(**maps) if slot == main else MaterialTextures(solid_color=(0.45, 0.45, 0.45, 1.0)) for slot in range(max(faces) + 1)]
    return write_gltf(int(icon, 16), parts, out, material_textures=slots)


def _parts(folder: Path, files: dict, meshes: list[str]) -> list:
    """Meshes of an old build as R6-parser mesh parts (its CompiledMesh reader reads the v29 ones as they are)."""
    from src.mesh import read_mesh_with_islands
    from src.model import MeshPart

    parts = []
    for number, mesh in enumerate(meshes):
        archive, offset, size, _ = files[int(mesh, 16)]
        with open(folder / archive, "rb") as f:
            f.seek(offset)
            data = legacy.asset_data(f.read(size))
        at = data.find(struct.pack("<I", 0xFC9E1595))
        if at < 0:
            raise ValueError(f"old mesh {mesh} has no geometry")
        vertices, uvs, normals, tangents, _, _, islands = read_mesh_with_islands(data[at:at + 8 + struct.unpack_from("<I", data, at + 4)[0]])
        parts.append(MeshPart(uid=number, vertices=vertices, uvs=uvs, normals=normals, islands=islands, tangents=tuple(tangents)))
    return parts


# The 2017 EOTech is today's Holo A: today's model (3EA76C8D23) has no meshes on disk, installed or streamed, while an
# old build still has its body, window and reticle, in today's sight space (base on the rail, centred, facing +y:
# several sight bodies are byte for byte the same then and now). Its textures are in no build found so far (the
# material template its parts name is missing even in Y2S3), so it gets plain paint: black body, clear window, red dot.
EOTECH = {"0000003EA76C8D23": ("00000004FD399809", "0000000619E8004A", "0000000619E8004F")}  # body, window, reticle
PAINT = [
    {"name": "EOTech body", "pbrMetallicRoughness": {"baseColorFactor": [0.03, 0.03, 0.035, 1.0], "metallicFactor": 0.2, "roughnessFactor": 0.55}},
    {"name": "EOTech glass", "alphaMode": "BLEND", "doubleSided": True,
     "pbrMetallicRoughness": {"baseColorFactor": [0.55, 0.7, 0.75, 0.18], "metallicFactor": 0.0, "roughnessFactor": 0.05}},
    {"name": "EOTech reticle", "emissiveFactor": [1.0, 0.08, 0.05], "doubleSided": True,
     "pbrMetallicRoughness": {"baseColorFactor": [1.0, 0.08, 0.05, 1.0], "metallicFactor": 0.0, "roughnessFactor": 0.4}},
]


def sights(loaded: list[tuple[Path, dict]]) -> dict[str, tuple[str, str]]:
    """Today's sight models whose meshes an old build still has: {model: (file, season label)}."""
    out: dict[str, tuple[str, str]] = {}
    for folder, data in loaded:
        for model in data.get("sights", ()):
            out.setdefault(model, (f"{OLD_SIGHT}{_key(folder)}:{model}", label(folder)))
    return out


def sight_gltf(file: str, out: Path) -> Path:
    """The old EOTech as glTF in plain paint: the body (its window plane is its second material), glass, reticle."""
    from src.gltf import write_gltf

    key, _, model = file[len(OLD_SIGHT):].partition(":")
    folder = next((f for f in builds() if _key(f) == key), None)
    meshes = load(folder).get("sights", {}).get(model) if folder else None
    if not meshes:
        raise ValueError(f"the old build of sight {model} isn't in Settings any more")
    gltf = Path(write_gltf(int(model, 16), _parts(folder, _index(folder), meshes), out))
    doc = json.loads(gltf.read_text(encoding="utf-8"))
    doc["materials"] = PAINT
    for number, mesh in enumerate(doc["meshes"]):
        for primitive in mesh["primitives"]:
            primitive["material"] = (0 if primitive.get("material", 0) == 0 else 1) if number == 0 else min(number, 2)
    gltf.write_text(json.dumps(doc), encoding="utf-8")
    return gltf


def _save_maps(folder: Path, files: dict, roles: dict, out: Path, tint: list[float] | None = None) -> dict[str, str]:
    """The best quality of each map (colour → diffuse, normal, specular) as PNG in `out`: glTF texture names. A tint
    other than white is multiplied into the colour, as the game does."""
    from PIL import Image, ImageChops

    saved = {}
    out.mkdir(parents=True, exist_ok=True)
    colour = tuple(min(255, round(255 * c)) for c in tint[:3]) if tint else (255, 255, 255)
    for role, name in (("color", "diffuse"), ("normal", "normal"), ("specular", "specular")):
        if not roles.get(role):
            continue
        uid = int(roles[role][max(roles[role], key=int)], 16)  # the highest quality it has
        image, file = legacy.texture_png(_body(folder, files, uid)), f"{uid:016X}.png"
        if role == "color" and colour != (255, 255, 255):
            tinted = ImageChops.multiply(image.convert("RGB"), Image.new("RGB", image.size, colour))
            if "A" in image.getbands():
                tinted.putalpha(image.getchannel("A"))
            image, file = tinted, f"{uid:016X}_{bytes(colour).hex()}.png"
        image.save(out / file, compress_level=1)
        saved[name] = file
    return saved
