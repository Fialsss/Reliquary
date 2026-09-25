"""Retired skins meet today's catalog through their icons: one look, one skin, never over something exportable,
and never two skins on the same look (colour sheet and tint). A charm's materials are read slot by slot with their tint."""
import struct
import unittest
from pathlib import Path
from unittest import mock

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

    def test_two_skins_on_the_same_look_get_neither(self):
        self.assertEqual(self.files([({3}, "old:k:R", "Y2S3", "white"), ({6}, "old:k:C", "Y2S3", "white")]), {})

    def test_one_sheet_in_two_tints_is_two_looks(self):
        self.assertEqual(self.files([({3}, "old:k:R", "Y2S3", "white x [1, 0.02, 0.02, 1]"), ({6}, "old:k:C", "Y2S3", "white x [0, 1, 1, 1]")]),
                         {"ruby": ("old:k:R", "Y2S3"), "cyan": ("old:k:C", "Y2S3")})

    def test_a_sheet_shared_with_a_look_that_lands_nowhere_still_counts(self):
        self.assertEqual(self.files([({3}, "old:k:R", "Y2S3", "skulls"), ({99}, "old:k:X", "Y2S3", "skulls")]), {"ruby": ("old:k:R", "Y2S3")})

    def test_a_charms_slots_are_its_mesh_objects_materials_in_order(self):
        def obj(kind, uid, props=b""):
            return struct.pack("<IIIQI", kind, 12 + len(props), 0, uid, kind) + props
        mesh, colour = 0x75D0DCA8B, 0x7F692B296
        body = (obj(retired.SKIN_NODE, 1) + obj(retired.MESH_OBJECT, 2, struct.pack("<QQQ", mesh, 11, 10))
                + obj(retired.MATERIAL, 10, struct.pack("<4fQ", 0.98, 0.784, 0.235, 1.0, 20)) + obj(retired.MATERIAL, 11, struct.pack("<4f", 1, 1, 1, 1))
                + obj(retired.ICON, 20, struct.pack("<Q", 30)) + obj(retired.TEXTURE_SET, 30, struct.pack("<Q", colour)))
        files = {colour: ("a.forge", 0, 0, 0x9F492D22)}
        with mock.patch.object(retired, "_body", return_value=body), \
                mock.patch.object(retired, "_maps", side_effect=lambda folder, files, children, listed_by: {"color": sorted(children)}):
            slots = retired._slots(Path("old"), files, 1, [mesh], {})
        self.assertEqual(slots, {f"{mesh:016X}": [{"textures": {"color": []}, "tint": [1.0, 1.0, 1.0, 1.0]},
                                                  {"textures": {"color": [colour]}, "tint": [0.98, 0.784, 0.235, 1.0]}]})

    def test_an_old_weapon_is_todays_by_its_mesh_uids_and_brings_its_mesh_when_todays_was_redone(self):
        build = [(Path(r"E:\old\Y2S3_A"), {"weapons": [{"meshes": ["00000000000000AA"], "looks": [{"nodes": ["N"], "icons": ["0000000000000001"]}]}],
                                          "textures": {"N": {"color": {"0": "C"}}}})]
        for identical, own in ((True, False), (False, True)):
            with mock.patch.object(retired, "_identical", return_value=identical):
                (look,) = retired.for_weapon({0xAA}, build)
            self.assertEqual(look[1].endswith(retired.OWN_MESH), own)
        # one shared uid is another gun (today's Bearing 9 and 2017's AUG), or a mesh the old build can't give
        self.assertEqual(retired.for_weapon({0xBB}, build), [])
        self.assertEqual(retired.for_weapon({0xAA, 0xBB}, build), [])

    def test_old_charms_by_icon_first_build_wins(self):
        a, b = Path(r"E:\old\Y2S3_A"), Path(r"E:\old\Y1S1_B")
        found = retired.charms([(a, {"charms": {"00000008E1F45A05": {}}}), (b, {"charms": {"00000008E1F45A05": {}, "000000000000ABCD": {}}})])
        self.assertEqual(found[0x8E1F45A05], (f"oldcharm:{retired._key(a)}:00000008E1F45A05", "Y2S3"))
        self.assertEqual(found[0xABCD][1], "Y1S1")

    def test_the_label_is_the_season_even_for_a_vault_folder(self):
        self.assertEqual(retired.label(Path(r"E:\Old R6\Downloads\Y2S3_BloodOrchid")), "Y2S3")
        self.assertEqual(retired.label(Path(r"C:\lib\Y1S1\8358812283631269928")), "Y1S1")
        self.assertEqual(retired.label(Path(r"D:\builds\old")), "old")


if __name__ == "__main__":
    unittest.main()
