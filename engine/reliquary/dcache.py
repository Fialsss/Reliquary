"""Siege's download cache: the weapon skins and charms the game streams in, as glTF documents with names.

download/downloadcache/v_7/data/**.data, one entry per file: a big-endian header (u32 version 7, u64 FILETIME,
u32 payload and file sizes), padding, the u32 decompressed size right before the old Forge block magic
34aafb5799fa1410, a 7-byte block header, then groups [u8 n][n x (u32 packed, u32 unpacked)][n x (u32 hash,
bytes)] of Zstandard chunks. What comes out is a binary glTF written by Ubisoft's tools:

- materials and textures carry real names: W_AR_FAMAS_UNISKIN_Lacquer, W_Charm_Y8S2_CaptainLaserhawk…
- each texture keeps its pixels in the binary chunk, per quality preset (PlatformCompiledData = buffer view),
  in the same BCn formats as the game archives;
- a mesh stores the game's CompiledMesh body in a buffer view (extras.Data); charms have one, weapon skins
  don't (the weapon's mesh is the installed one), so a skinned weapon = installed mesh + these textures.

Only what the game has downloaded on this PC is there (skins and charms you own or previewed).
"""
from __future__ import annotations

import io
import json
import os
import re
import struct
import sys
from pathlib import Path

import zstandard

from . import operators, settings  # noqa: F401  (operators puts the vendored R6-parser on the path)
from .rpc import emit

MAGIC = bytes.fromhex("34aafb5799fa1410")
PRESETS = ("Preset3_Ultra", "Preset2_High", "Preset1_Medium", "Preset0_Low")
CLASSES = ("AR", "SMG", "SG", "SA", "LMG", "SR", "MP", "SGM")


def cache_root() -> Path:
    return operators._game() / "download" / "downloadcache" / "v_7" / "data"


def read_entry(data: bytes) -> bytes | None:
    """The decompressed content of one cache entry, or None when it isn't a complete Forge entry: about a third of
    the cache are placeholders the game hasn't filled yet (zeros after the header), and some are media files."""
    pos = data.find(MAGIC)
    if pos < 4:
        return None
    total = struct.unpack_from("<I", data, pos - 4)[0]
    cursor, out = pos + 15, bytearray()
    zstd = zstandard.ZstdDecompressor()  # one per call: a decompressor isn't safe to share between threads
    while len(out) < total and cursor < len(data):
        count = data[cursor]
        sizes = [struct.unpack_from("<II", data, cursor + 1 + 8 * i) for i in range(count)]
        cursor += 1 + 8 * count
        for packed, unpacked in sizes:
            chunk = data[cursor + 4:cursor + 4 + packed]
            if len(chunk) < packed:
                return None
            cursor += 4 + packed
            out += chunk if packed == unpacked else zstd.decompress(chunk, max_output_size=unpacked)
    return bytes(out) if len(out) >= total else None


def glb(data: bytes) -> tuple[dict, bytes] | None:
    """(JSON document, binary chunk) of a binary glTF."""
    if not data or not data.startswith(b"glTF"):
        return None
    length = struct.unpack_from("<I", data, 12)[0]
    try:
        doc = json.loads(data[20:20 + length])
    except ValueError:
        return None
    return doc, data[20 + length + 8:]


def _view(doc: dict, binary: bytes, index) -> bytes:
    view = doc["bufferViews"][int(index)]
    start = view.get("byteOffset", 0)
    return binary[start:start + view["byteLength"]]


def _pretty(name: str, code: str = "") -> str:
    words = [w for w in re.split(r"[_\s]+", name) if w and w.upper() not in ("W", "UNISKIN", "UNSHARED", "PC", "WS", "ADDITION")]
    if code:
        words = [w for w in words if w.lower() != code.lower()]
    return " ".join(words).strip() or name


def describe(doc: dict) -> dict | None:
    """What a cache document is: a charm (mesh + textures) or a weapon skin (textures for an installed mesh)."""
    materials = [m.get("name", "") for m in doc.get("materials", [])]
    textures = {t.get("name", "") for t in doc.get("textures", [])}
    roles = {role for name in textures for role in ("Diffuse", "Normal", "Specular") if role in name}
    has_mesh = any("Data" in m.get("extras", {}) for m in doc.get("meshes", []))
    bones = sorted({n["extras"]["BoneId"] for n in doc.get("nodes", []) if "BoneId" in n.get("extras", {})})
    patterns = sorted(t for t in textures if "WeaponPattern" in t)
    for material in materials:
        parts = material.split("_")
        if len(parts) > 2 and parts[1] == "Charm" and has_mesh and "Diffuse" in roles:
            return {"kind": "charm", "name": _pretty("_".join(parts[2:])), "material": material}
        if len(parts) > 2 and parts[1] in CLASSES and patterns:  # a camo pattern (Aloha, Camo1950…) laid over the weapon
            look = re.sub(r"_?(DiffuseMap|Diffuse|Map)?_?PC$", "", patterns[0].replace("W_WeaponPattern_", ""))
            return {"kind": "skin", "class": parts[1], "code": parts[2], "name": _pretty(look), "material": material,
                    "bones": bones, "pattern": True}
        if len(parts) > 2 and parts[1] in CLASSES and {"Diffuse", "Normal"} <= roles:
            return {"kind": "skin", "class": parts[1], "code": parts[2], "name": _pretty("_".join(parts[3:]), parts[2]) or "Default",
                    "material": material, "bones": bones}
    return None


def _signature(root: Path) -> str:
    """Whether the game downloaded something: its own index of the cache changes with every download (walking the
    5,000 files instead takes over a second)."""
    index = root.parent / "downloadcache.dcindex"
    if index.is_file():
        stat = index.stat()
        return f"i:{stat.st_size}:{stat.st_mtime_ns}"
    files = [f for f in root.rglob("*.data")]
    return f"2:{len(files)}:{max((f.stat().st_mtime_ns for f in files), default=0)}"


def catalog(announce: bool = True) -> list[dict]:
    """Every usable document in the cache, remembered on disk: later calls read only what the game added."""
    root = cache_root()
    if not root.is_dir():
        return []
    store = settings.HOME / "dcache.json"
    try:
        saved = json.loads(store.read_text(encoding="utf-8"))
        known = saved["files"] if saved.get("version") == 3 else {}
    except (OSError, ValueError, KeyError):
        known = {}
    # each file is read once: {path: [size, mtime, what it is or None]}; a file the game rewrites is read again
    files, seen = sorted(root.rglob("*.data")), {}
    for done, path in enumerate(files):
        if announce and done % 200 == 0:
            emit("operators.progress", {"step": "cache", "done": done, "total": len(files), "file": ""})
        file = str(path.relative_to(root))
        try:
            stat = path.stat()
            stamp = [stat.st_size, stat.st_mtime_ns]
            if known.get(file, [])[:2] == stamp:
                seen[file] = known[file]
                continue
            data = path.read_bytes()
        except OSError as error:  # evicted or being written by the game: looked at again next time
            print(f"Cache entry {path.name}: {error}", file=sys.stderr)
            continue
        try:
            content = read_entry(data)
            parsed = glb(content) if content else None
            info = describe(parsed[0]) if parsed else None
        except (ValueError, KeyError, struct.error, zstandard.ZstdError) as error:
            print(f"Cache entry {path.name}: {error}", file=sys.stderr)
            info = None
        seen[file] = stamp + [info]
    if seen != known:
        store.write_text(json.dumps({"version": 3, "files": seen}), encoding="utf-8")
    return [{"file": file, **info} for file, (_, _, info) in seen.items() if info]


def _open(file: str) -> tuple[dict, bytes]:
    parsed = glb(read_entry((cache_root() / file).read_bytes()) or b"")
    if parsed is None:
        raise ValueError(f"cache entry {file} is incomplete")
    return parsed


def _texture_png(doc: dict, binary: bytes, tex: dict, path: Path, tile: int = 1) -> None:
    """The best preset of a texture as PNG, BCn through R6-parser's decoder.
    tile: repeat it n x n, the way the game lays a camo pattern over the weapon's UVs."""
    from PIL import Image
    from src import texture

    extras = tex["extras"]
    preset = next(extras[p] for p in PRESETS if p in extras)
    info, fmt = preset["CompiledTextureMapData"], preset["PixelFormat"]
    width, height = max(1, info["Width"] >> info["MipStart"]), max(1, info["Height"] >> info["MipStart"])
    if fmt not in texture.FORMATS:
        raise ValueError(f"texture format {fmt}")
    dxgi, block = texture.FORMATS[fmt]
    top = ((width + 3) // 4) * ((height + 3) // 4) * block
    surface = _view(doc, binary, preset["PlatformCompiledData"])[:top]
    with Image.open(io.BytesIO(texture._dds_dx10(width, height, surface, dxgi))) as source:
        image = source.convert("RGBA")
    if fmt == 6 and preset.get("TextureMapType") == 1:
        image = texture.reconstruct_bc5_z(image)  # BC5 normals keep X and Y only
    repeat(image, tile).save(path)


def repeat(image, tile: int):
    """A camo pattern repeated tile x tile, the way the game lays it over the weapon's UVs (within 2048 px)."""
    from PIL import Image

    if tile <= 1:
        return image
    image.thumbnail((2048 // tile, 2048 // tile))
    sheet = Image.new(image.mode, (image.width * tile, image.height * tile))
    for n in range(tile * tile):
        sheet.paste(image, ((n % tile) * image.width, (n // tile) * image.height))
    return sheet


def textures(file: str, out: Path) -> dict[str, str]:
    """Diffuse, normal and specular of a cache document, saved as PNG next to where the glTF will be.
    A camo pattern is its diffuse alone, repeated as often as its material says (CamoTilingU, 4 so far)."""
    doc, binary = _open(file)
    out.mkdir(parents=True, exist_ok=True)
    params = next((m.get("extras", {}).get("ShaderTemplateParams", {}) for m in doc.get("materials", [])), {})
    pattern = any("WeaponPattern" in t.get("name", "") for t in doc.get("textures", []))
    tile = max(1, min(8, round(params.get("CamoTilingU", 4)))) if pattern else 1
    roles = {}
    for tex in doc.get("textures", []):
        name = tex.get("name", "")
        role = next((r.lower() for r in ("Diffuse", "Normal", "Specular") if r in name), None)
        if role and role not in roles:
            _texture_png(doc, binary, tex, out / f"{name}.png", tile)
            roles[role] = f"{name}.png"
    return roles


def charm_gltf(file: str, out: Path) -> Path:
    """A charm as a standard glTF: its CompiledMesh through R6-parser's mesh reader and writer."""
    from src.gltf import write_gltf
    from src.mesh import read_mesh_with_islands
    from src.model import MeshPart

    doc, binary = _open(file)
    # glows and sparkles (…_Emissive, alpha-tested) need the game's effect shaders: drawn plain they'd hide the charm
    effects = {n for n, m in enumerate(doc.get("materials", []))
               if m.get("name", "").endswith("_Emissive") or m.get("extras", {}).get("AlphaTestEnabled")}
    parts = []
    for number, mesh in enumerate(doc.get("meshes", [])):
        if "Data" not in mesh.get("extras", {}):
            continue
        body = _view(doc, binary, mesh["extras"]["Data"])
        verts, uvs, normals, tangents, _, _, islands = read_mesh_with_islands(struct.pack("<II", 0xFC9E1595, len(body)) + body)
        slots = [int(m) for m in mesh["extras"].get("GltfMaterials", [])]  # island material id → document material
        kept = [i for i in islands if (slots[i.material_id] if i.material_id < len(slots) else -1) not in effects]
        islands = kept or islands
        parts.append(MeshPart(uid=number, vertices=verts, uvs=uvs, normals=normals, islands=islands, tangents=tuple(tangents)))
    roles = textures(file, out)
    return write_gltf(0xC4A12, parts, out, **roles)
