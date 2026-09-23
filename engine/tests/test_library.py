"""Disk space: the library listing, deleting one build or everything, and never deleting outside it."""
import json
import tempfile
import unittest
from pathlib import Path

from reliquary import settings, vault


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = (settings.HOME, settings.FILE)
        settings.HOME, settings.FILE = self.tmp, self.tmp / "settings.json"
        settings.update(library=str(self.tmp / "library"))
        # two downloaded builds of Neon Dawn and one of Black Ice
        neon = next(s for s in vault._seasons() if s["id"] == "Y5S4")
        for patch in neon["patches"]:
            self.fake_download("Y5S4", patch["manifest"], 1000)
        self.fake_download("Y1S1", vault._seasons()[1]["patches"][0]["manifest"], 500)
        self.outside = self.tmp / "precious.txt"
        self.outside.write_text("keep me")

    def tearDown(self):
        settings.HOME, settings.FILE = self.saved

    def fake_download(self, season, manifest, size):
        folder = vault._library(season, manifest)
        folder.mkdir(parents=True)
        (folder / "datapc64.forge").write_bytes(b"x" * size)
        (folder / vault.MARKER).write_text(json.dumps({"files": ["datapc64.forge"]}))

    def test_listing_and_totals(self):
        lib = vault.library()
        self.assertEqual(len(lib["items"]), 3)
        self.assertGreaterEqual(lib["total"], 2500)

    def test_delete_one_build_then_everything(self):
        first = vault.library()["items"][0]
        after = vault.delete(first["season"], first["manifest"])
        self.assertEqual(len(after["items"]), 2)
        self.assertEqual(vault.delete()["items"], [])
        self.assertTrue(self.outside.exists())  # nothing outside the library was touched

    def test_refuses_paths_outside_the_library(self):
        with self.assertRaises(vault.Failure):
            vault._remove_inside_library(self.tmp)
        with self.assertRaises(vault.Failure):
            vault._remove_inside_library(self.tmp / "library" / ".." / "precious.txt")
        self.assertTrue(self.outside.exists())

    def test_unknown_season(self):
        with self.assertRaises(vault.Failure):
            vault.delete("Y99S9")


if __name__ == "__main__":
    unittest.main()
