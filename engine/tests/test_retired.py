"""Retired skins meet today's catalog through their icons: one look, one skin, never over something exportable,
and never a tint-only variant (a colour sheet landing on two different skins)."""
import unittest
from pathlib import Path

from reliquary import catalog, retired


class RetiredTest(unittest.TestCase):
    SHOWS = {"glacier": {1, 2}, "ruby": {3}, "cyan": {6}, "shared": {4}, "cached": {5}}

    def skins(self):
        return [{"id": s, "file": "a.data" if s == "cached" else ""} for s in self.SHOWS]

    def files(self, old, shows=None):
        skins = self.skins()
        catalog.join_old(skins, shows or self.SHOWS, old)
        return {s["id"]: (s["file"], s.get("source")) for s in skins if s["file"] and s["id"] != "cached"}

    def test_a_look_goes_to_the_skin_with_its_icon(self):
        self.assertEqual(self.files([({2}, "old:k:A", "Y2S3", "g")]), {"glacier": ("old:k:A", "Y2S3")})

    def test_ambiguous_or_exportable_skins_are_left_alone(self):
        self.assertEqual(self.files([({4}, "old:k:C", "Y2S3", "s"), ({5}, "old:k:D", "Y2S3", "c")], {**self.SHOWS, "ruby": {3, 4}}), {})

    def test_a_sheet_on_two_skins_is_a_tint_and_neither_gets_it(self):
        self.assertEqual(self.files([({3}, "old:k:R", "Y2S3", "white"), ({6}, "old:k:C", "Y2S3", "white")]), {})

    def test_a_sheet_shared_with_a_look_that_lands_nowhere_still_counts(self):
        self.assertEqual(self.files([({3}, "old:k:R", "Y2S3", "skulls"), ({99}, "old:k:X", "Y2S3", "skulls")]), {"ruby": ("old:k:R", "Y2S3")})

    def test_the_label_is_the_season_even_for_a_vault_folder(self):
        self.assertEqual(retired.label(Path(r"E:\Old R6\Downloads\Y2S3_BloodOrchid")), "Y2S3")
        self.assertEqual(retired.label(Path(r"C:\lib\Y1S1\8358812283631269928")), "Y1S1")
        self.assertEqual(retired.label(Path(r"D:\builds\old")), "old")


if __name__ == "__main__":
    unittest.main()
