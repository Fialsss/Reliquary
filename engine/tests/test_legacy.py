"""Old (v29) Forge archives: index, chunked Zstandard blocks, texture header and trailer, PNG decode."""
import struct
import tempfile
import unittest
from pathlib import Path

import zstandard

from reliquary import legacy


def block(chunks):
    """An asset block: magic, header (kind 3 = chunked Zstandard), chunk table, then hash + bytes per chunk."""
    table = b"".join(struct.pack("<II", unpacked, len(packed)) for packed, unpacked in chunks)
    body = b"".join(b"HASH" + packed for packed, _ in chunks)
    return legacy.BLOCK_MAGIC + struct.pack("<HHBHHH", 2, 3, 0, 0x8004, len(chunks), 0) + table + body


def texture_payload(width, height, fmt, kind, surface):
    head = b"\x78\xc4\xb5\xd7" + b"\0" * 28 + legacy.TEXTURE_MAP + struct.pack("<4I", fmt, 1, 0, kind) + b"\0" * 24
    trailer = struct.pack("<9IIB", width, height, 1, 0, 0, 0, 1, 0, 7, 7, 1)[:legacy.TRAILER]
    return head + legacy.TEXTURE_DATA + struct.pack("<II", len(surface) + 4, 7) + surface + trailer


def forge(path, uid, entry):
    """A v29 header with one file table holding one entry."""
    header = bytearray(b"scimitar\x00" + struct.pack("<I", 29) + b"\0" * 0x60)
    table_pos, fat = 0x80, 0x100
    struct.pack_into("<IIIIQ", header, 0x1E + 20, 0, 0, 0, 1, table_pos)
    data = bytearray(header.ljust(table_pos, b"\0"))
    data += struct.pack("<iiqq", 1, 0, fat, -1)
    data = data.ljust(fat, b"\0")
    offset = fat + 20
    data += struct.pack("<QQI", offset, uid, len(entry)) + entry
    path.write_bytes(bytes(data))


class LegacyTest(unittest.TestCase):
    def test_texture_round_trip(self):
        # BC1 8x8: four blocks; red endpoints (0xF800) with all indices 0 = solid red
        surface = (struct.pack("<HHI", 0xF800, 0xF800, 0)) * 4
        payload = texture_payload(8, 8, 2, 0, surface)
        cut = len(payload) // 2  # two chunks: the first compressed, the last stored as is
        meta = block([(b"M" * 30, 30)])
        data = block([(zstandard.ZstdCompressor().compress(payload[:cut]), cut), (payload[cut:], len(payload) - cut)])
        path = Path(tempfile.mkdtemp()) / "datapc64_test_bnk_textures0.forge"
        forge(path, 0x1234, meta + data)

        version, entries = legacy.read_index(path)
        self.assertEqual((version, [(e[1], e[2]) for e in entries]), (29, [(0x1234, len(meta + data))]))
        with open(path, "rb") as f:
            offset, _, size = entries[0]
            self.assertEqual(legacy.texture_info(f, offset, size), {"format": 2, "kind": "color", "width": 8, "height": 8})
            f.seek(offset)
            image = legacy.texture_png(legacy.asset_data(f.read(size)))
        self.assertEqual(image.size, (8, 8))
        self.assertEqual(image.getpixel((3, 5))[:3], (255, 0, 0))

    def test_not_a_texture(self):
        meta = block([(b"M" * 30, 30)])
        data = block([(b"just some object", 16)])
        path = Path(tempfile.mkdtemp()) / "datapc64.forge"
        forge(path, 7, meta + data)
        _, entries = legacy.read_index(path)
        with open(path, "rb") as f:
            self.assertIsNone(legacy.texture_info(f, entries[0][0], entries[0][2]))


if __name__ == "__main__":
    unittest.main()
