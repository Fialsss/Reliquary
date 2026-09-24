"""Retired weapon skins from old builds: Glacier and the other skins today's game neither installs nor streams.

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
from pathlib import Path

from . import legacy, operators, settings
from .rpc import emit, method

LINK, NAME, SKIN_LIST, SKIN_ENTRY = 0x7855A3D0, 0x6C7B8D30, 0x328A37EF, 0x8D1D966B
MESH, SKIN_NODE, PREFAB = 0xABEB2DFB, 0x22ECBE63, 0x971A842E
UI, ICON = 0x51066FDD, 0x989DC6B2  # a skin's UI object and its icons (GUI texture specs, 4F09331E today)
QUALITY = {0xD7B5C478: 0, 0xF9C80707: 1, 0x59CE4D13: 2, 0x9F492D22: 3}  # low, medium, high, ultra
OLD = "old:"  # a skin's `file` when its textures come from an old build: old:<build key>:<texture node uid>
VERSION = 6  # of the cache below


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


def _read(folder: Path) -> dict:
    """Every weapon of the old build with the meshes of its default look and its skins, each skin with its texture
    node and its icons; and every skin node's textures by role and quality."""
    files, graph = _index(folder), _depgraph(folder)
    kind = lambda uid: files[uid][3] if uid in files else None  # noqa: E731
    archive, offset, size, _ = files[0x800]
    with open(folder / archive, "rb") as f:
        f.seek(offset)
        registry = legacy.asset_data(f.read(size))
    weapons = _names(registry, struct.pack("<I", NAME), 4, 12)
    entries = _objects(registry, SKIN_ENTRY)
    token = {uid: links[0] for uid, body in entries.items() if (links := _links(body))}
    # A skin's icons: UI objects name its token (and often its weapon) together with its GUI texture specs, and
    # those uids are still today's (a skin definition names them): the one thing old and new builds share for a
    # skin, renamed or not. The (weapon, token) pair decides; the token alone is the fallback (a few are shared).
    pair, alone, tokens = defaultdict(set), defaultdict(set), set(token.values())
    for body in _objects(registry, UI, limit=8192).values():
        refs = _u64s(body)
        shown = {u for u in refs if kind(u) == ICON}
        for t in refs & tokens:
            alone[t] |= shown
            for w in refs & weapons.keys():
                pair[(w, t)] |= shown
    out, nodes = [], set()
    for body in _objects(registry, SKIN_LIST).values():
        links = _links(body)
        if not links or links[0] not in weapons:
            continue
        start = body.find(struct.pack("<II", LINK, 0), body.find(struct.pack("<II", LINK, 1)) + 16)
        if start < 0 or start + 12 > len(body):
            continue
        count = struct.unpack_from("<I", body, start + 8)[0]
        listed = [u for u in struct.unpack_from(f"<{min(count, (len(body) - start - 12) // 8)}Q", body, start + 12) if u in entries]
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
    # a node can list two maps of one role and quality: its own, and a small detail map every node of that skin
    # shares (Onami's normal): the one fewest nodes list is the node's, the larger one if that doesn't decide
    listed_by = defaultdict(int)
    for node in nodes:
        for child in graph.get(node, ()):
            listed_by[child] += 1
    textures = {}
    for node in nodes:
        found: dict[tuple[str, int], list[tuple[int, int, int]]] = defaultdict(list)
        for child in graph.get(node, ()):
            if kind(child) in QUALITY:
                a, o, s, _ = files[child]
                with open(folder / a, "rb") as f:
                    info = legacy.texture_info(f, o, s)
                if info and info["kind"] in ("color", "normal", "specular"):
                    found[(info["kind"], QUALITY[kind(child)])].append((listed_by[child], -info["width"] * info["height"], child))
        roles: dict[str, dict[int, str]] = defaultdict(dict)
        for (role, quality), options in found.items():
            roles[role][quality] = f"{min(options)[2]:016X}"
        if roles.get("color"):
            textures[f"{node:016X}"] = roles
    # A colour sheet several skins of one weapon share, and plain near-white, is a tint mask: those skins' colour
    # lives in a tint (Masonry Ruby, Cyan, Diamond, Topaz) that the exported textures can't carry. Marked here, left out.
    plain: dict[tuple, bool] = {}
    for weapon in out:
        owners: dict[tuple, set[str]] = defaultdict(set)
        for look in weapon["looks"]:
            node = next((n for n in look["nodes"] if n in textures), None)
            if node:
                owners[tuple(sorted(textures[node]["color"].values()))].add(node)
        for sheet, nodes_of in owners.items():
            if len(nodes_of) > 1:
                if sheet not in plain:
                    plain[sheet] = _plain(folder, files, textures[next(iter(nodes_of))]["color"])
                for node in nodes_of if plain[sheet] else ():
                    textures[node]["tint"] = True
    return {"weapons": out, "textures": textures}


def _plain(folder: Path, files: dict, colour: dict[int, str]) -> bool:
    """Whether a colour sheet is a plain near-white mask (its smallest size is enough to tell)."""
    from PIL import ImageStat

    archive, offset, size, _ = files[int(colour[min(colour)], 16)]
    with open(folder / archive, "rb") as f:
        f.seek(offset)
        stat = ImageStat.Stat(legacy.texture_png(legacy.asset_data(f.read(size))).convert("RGB"))
    return min(stat.mean) > 215 and max(stat.mean) - min(stat.mean) < 12


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
    """The old skins that fit a weapon of today (its body meshes), from the builds `loaded` read:
    [(icon uids, file, season label, colour sheet)]. An old weapon fits when it has every one of today's meshes
    and each is identical. The colour sheet lets catalog.join_old leave out tint-only variants."""
    out: list[tuple[set[int], str, str, str]] = []
    for folder, data in loaded:
        for weapon in data["weapons"]:
            if not meshes or not meshes <= {int(m, 16) for m in weapon["meshes"]} or not _identical(folder, data, meshes):
                continue
            for look in weapon["looks"]:
                node = next((n for n in look["nodes"] if n in data["textures"]), None)
                if node and not data["textures"][node].get("tint"):
                    sheet = ",".join(sorted(data["textures"][node]["color"].values()))
                    out.append(({int(i, 16) for i in look["icons"]}, f"{OLD}{_key(folder)}:{node}", label(folder), sheet))
    return out


def available(file: str) -> bool:
    """Whether the old build an old skin comes from is still set in Settings and there."""
    return any(_key(folder) == file[len(OLD):].split(":")[0] for folder in builds())


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
    """Colour, normal and specular of an old skin, the best quality its build has, saved as PNG in `out`."""
    key, _, node = file[len(OLD):].partition(":")
    folder = next((f for f in builds() if _key(f) == key), None)
    roles = load(folder)["textures"].get(node) if folder else None
    if not roles:
        raise ValueError(f"the old build of skin {node} isn't in Settings any more")
    files, saved = _index(folder), {}
    out.mkdir(parents=True, exist_ok=True)
    for role, name in (("color", "diffuse"), ("normal", "normal"), ("specular", "specular")):
        if not roles.get(role):
            continue
        uid = int(roles[role][max(roles[role], key=int)], 16)  # the highest quality it has
        archive, offset, size, _ = files[uid]
        with open(folder / archive, "rb") as f:
            f.seek(offset)
            image = legacy.texture_png(legacy.asset_data(f.read(size)))
        image.save(out / f"{uid:016X}.png", compress_level=1)
        saved[name] = f"{uid:016X}.png"
    return saved
