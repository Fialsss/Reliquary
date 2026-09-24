"""The download cache is read once: a second look only opens the files the game added or rewrote."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reliquary import dcache, settings


class CacheTest(unittest.TestCase):
    def test_second_look_reads_only_new_files(self):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home) / "data"
            (root / "00").mkdir(parents=True)
            (root / "00" / "a.data").write_bytes(b"old")
            reads = []
            with mock.patch.object(settings, "HOME", Path(home)), mock.patch.object(dcache, "cache_root", return_value=root), \
                    mock.patch.object(dcache, "read_entry", side_effect=lambda data: reads.append(data)):
                dcache.catalog(announce=False)
                (root / "00" / "b.data").write_bytes(b"new")
                dcache.catalog(announce=False)
            self.assertEqual(reads, [b"old", b"new"])


if __name__ == "__main__":
    unittest.main()
