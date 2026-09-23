"""Old builds from the Vault: read their Forge archives and extract the textures.

Builds before the current format (Forge version 29 and nearby) keep every asset
as two blocks, metadata and data, each cut into chunks compressed with
Zstandard. Textures carry their format code in the header and their size in a
0x29-byte trailer; the pixels in between decode with the same BCn formats as
today, so the PNG conversion is R6-parser's. Checked on a full Y2S3 build:
6,536 of 6,550 textures of its high-resolution archive decode.
"""
from __future__ import annotations

import io
import struct
import sys
import threading
from collections import Counter
from pathlib import Path

import zstandard

from . import operators, settings, vault  # noqa: F401  (operators puts the vendored R6-parser on the path)
from .rpc import Failure, emit, method

BLOCK_MAGIC = bytes.fromhex("34aafb5799fa1410")
TEXTURE_MAP = bytes.fromhex("e97f2313")
TEXTURE_DATA = bytes.fromhex("3d4b0cc3")
TRAILER = 0x29
KINDS = {0: "color", 1: "normal", 2: "specular"}  # 3, 8, 9…: masks (BC4 single channel, detail patterns)

_zstd = zstandard.ZstdDecompressor()
_scans: dict[str, list[dict]] = {}
_cancel = threading.Event()


# ------------------------------------------------------------------ format

def read_index(path: Path) -> tuple[int, list[tuple[int, int, int]]]:
    """(version, [(offset, uid, size)]) from a Forge header and its file tables (layout as in RainbowForge)."""
    with open(path, "rb") as f:
        head = f.read(0x60)
        if head[:9] != b"scimitar\x00":
            raise Failure(f"{path.name} isn't a Forge archive")
        version = struct.unpack_from("<I", head, 9)[0]
        cursor = 0x1E + 4 * 5 if version >= 27 else 0x1E + 4 * 4  # entries, dirs, 2 unknown (+1 from v27)
        _, _, _, tables, first = struct.unpack_from("<IIIIQ", head, cursor)
        entries, position = [], first
        for _ in range(tables):
            f.seek(position)
            max_file, _, fat, next_fat = struct.unpack("<iiqq", f.read(24))
            f.seek(fat)
            table = f.read(20 * max_file)
            entries += [struct.unpack_from("<QQI", table, 20 * i) for i in range(max_file)]
            if next_fat == -1:
                break
            position = next_fat
    return version, entries


def _block_chunks(blob: bytes, pos: int) -> tuple[list[tuple[int, int, int]], int]:
    """The chunks of the block at `pos`: [(data offset, packed, unpacked)] and where the next block starts."""
    if blob[pos:pos + 8] != BLOCK_MAGIC:
        raise ValueError("not an asset block")
    kind = struct.unpack_from("<H", blob, pos + 10)[0]
    if kind != 3:  # 3 = chunked Zstandard; 13 (Oodle) and 7 (flat) belong to other versions
        raise ValueError(f"block type {kind}")
    count = struct.unpack_from("<H", blob, pos + 15)[0]
    sizes = [struct.unpack_from("<II", blob, pos + 19 + 8 * i) for i in range(count)]
    cursor, chunks = pos + 19 + 8 * count, []
    for unpacked, packed in sizes:
        chunks.append((cursor + 4, packed, unpacked))  # each chunk: u32 hash, then its bytes
        cursor += 4 + packed
    return chunks, cursor


def _inflate(blob: bytes, chunk: tuple[int, int, int]) -> bytes:
    start, packed, unpacked = chunk
    data = blob[start:start + packed]
    return data if packed == unpacked else _zstd.decompress(data, max_output_size=unpacked)


def asset_data(blob: bytes) -> bytes:
    """The data block of one entry (the one after its metadata block), decompressed."""
    _, after_meta = _block_chunks(blob, 0)
    chunks, _ = _block_chunks(blob, after_meta)
    return b"".join(_inflate(blob, c) for c in chunks)


def _chunk_at(f, offset: int, peek: bytes, chunk: tuple[int, int, int]) -> bytes:
    start, packed, unpacked = chunk
    if start + packed > len(peek):
        f.seek(offset + start)
        peek, start = f.read(packed), 0
    return _inflate(peek, (start, packed, unpacked))


def texture_info(f, offset: int, size: int) -> dict | None:
    """Format, kind and size of a texture entry, reading only its headers, first and last chunk from disk."""
    f.seek(offset)
    peek = f.read(min(size, 8192))
    try:
        _, after_meta = _block_chunks(peek, 0)
        chunks, _ = _block_chunks(peek, after_meta)
        head, tail = _chunk_at(f, offset, peek, chunks[0]), _chunk_at(f, offset, peek, chunks[-1])
    except (ValueError, struct.error, zstandard.ZstdError):
        return None
    at = head.find(TEXTURE_MAP)
    if at < 0 or TEXTURE_DATA not in head or len(tail) < TRAILER:
        return None
    fmt, _, _, kind = struct.unpack_from("<4I", head, at + 4)
    w, h, _, _, shift = struct.unpack_from("<5I", tail, len(tail) - TRAILER)
    if shift > 16:
        return None
    return {"format": fmt, "kind": KINDS.get(kind, "mask"), "width": max(1, w >> shift), "height": max(1, h >> shift)}


def texture_png(data: bytes):
    """Decode the largest mip of an old texture to a Pillow image."""
    from PIL import Image
    from src import texture

    at = data.find(TEXTURE_MAP)
    fmt, _, _, kind = struct.unpack_from("<4I", data, at + 4)
    w, h, _, _, shift = struct.unpack_from("<5I", data, len(data) - TRAILER)
    width, height = max(1, w >> shift), max(1, h >> shift)
    surface = data[data.find(TEXTURE_DATA) + 12:len(data) - TRAILER]
    if fmt == 0:
        return Image.frombytes("RGBA", (width, height), surface[:width * height * 4], "raw", "BGRA")
    if fmt not in texture.FORMATS:
        raise ValueError(f"texture format {fmt} isn't supported")
    dxgi, block = texture.FORMATS[fmt]
    top = ((width + 3) // 4) * ((height + 3) // 4) * block
    with Image.open(io.BytesIO(texture._dds_dx10(width, height, surface[:top], dxgi))) as source:
        image = source.convert("RGBA")
    if fmt == 6 and kind == 1:
        image = texture.reconstruct_bc5_z(image)  # BC5 normals store X and Y only
    if kind == 0 and image.getextrema()[3] == (0, 0):
        image.putalpha(255)  # color maps with an unused, all-zero alpha
    return image


# ----------------------------------------------------------------- methods

def _archive(season: str, manifest: str, file: str) -> Path:
    path = vault._library(season, manifest) / file
    if not path.is_file() or path.suffix != ".forge":
        raise Failure(f"{file} isn't downloaded")
    return path


@method("legacy.scan")
def scan(season: str, manifest: str, file: str) -> dict:
    """What a downloaded archive holds: its format version and every texture with kind and size."""
    path = _archive(season, manifest, file)
    version, entries = read_index(path)
    if version >= 34:  # the current format: obfuscated index, Oodle chunks
        raise Failure("error.currentFormat")
    found = []
    with open(path, "rb") as f:
        for done, (offset, uid, size) in enumerate(entries):
            if done % 500 == 0:
                emit("legacy.progress", {"step": "scan", "done": done, "total": len(entries)})
            info = texture_info(f, offset, size)
            if info:
                found.append({"uid": f"{uid:016X}", "offset": offset, "size": size, **info})
    if not found and len(entries) > 10:
        raise Failure(f"No textures Reliquary can read in {file} (Forge version {version})")
    _scans[str(path)] = found
    counts = Counter((t["kind"], max(t["width"], t["height"])) for t in found)
    return {"version": version, "entries": len(entries), "textures": len(found),
            "counts": [[kind, side, n] for (kind, side), n in sorted(counts.items())]}


@method("legacy.extract")
def extract(season: str, manifest: str, file: str, min_size: int = 1024, kinds: list[str] | None = None) -> dict:
    """Save the textures of one archive as PNG, the ones at least `min_size` on their long side and of `kinds`."""
    path = _archive(season, manifest, file)
    if str(path) not in _scans:
        scan(season, manifest, file)
    wanted = [t for t in _scans[str(path)]
              if max(t["width"], t["height"]) >= min_size and t["kind"] in (kinds or [*KINDS.values(), "mask"])]
    target = Path(settings.load()["exports"]) / f"{season} {manifest}" / path.stem
    _cancel.clear()
    saved = failed = 0
    with open(path, "rb") as f:
        for done, item in enumerate(wanted):
            if _cancel.is_set():
                break
            emit("legacy.progress", {"step": "extract", "done": done, "total": len(wanted)})
            f.seek(item["offset"])
            try:
                image = texture_png(asset_data(f.read(item["size"])))
            except (ValueError, struct.error, zstandard.ZstdError, OSError) as error:
                print(f"{item['uid']}: {error}", file=sys.stderr)
                failed += 1
                continue
            folder = target / item["kind"]
            folder.mkdir(parents=True, exist_ok=True)
            image.save(folder / f"{item['uid']}_{image.width}x{image.height}.png", compress_level=1)
            saved += 1
    emit("legacy.progress", {"step": "extract", "done": len(wanted), "total": len(wanted)})
    return {"folder": str(target), "saved": saved, "failed": failed, "cancelled": _cancel.is_set()}


@method("legacy.cancel")
def cancel() -> bool:
    _cancel.set()
    return True
