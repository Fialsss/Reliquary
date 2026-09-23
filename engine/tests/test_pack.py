"""Operator packs: which models an appearance wears, and icons of any size (the parser only decodes powers of two)."""
import struct
import unittest

from reliquary import operators


class PackTest(unittest.TestCase):
    def test_primary_models_are_group_zero_without_repeats(self):
        groups = [(0xA1, 0xA2, 0xA1), (0xB1,), (), (), (), (), ()]
        data = b"\0" * 79 + b"".join(struct.pack(f"<I{len(g)}Q", len(g), *g) for g in groups) + b"\0"
        self.assertEqual(operators._primary_models(data), [0xA1, 0xA2])

    def test_icon_of_a_size_that_is_not_a_power_of_two(self):
        from src import texture

        width, height = 12, 8  # BC1: 3x2 blocks of 8 bytes; red endpoints and indices 0 = solid red
        surface = struct.pack("<HHI", 0xF800, 0xF800, 0) * 6
        # the trailer as the game writes it: w, h, 1, 0, shift, …, format code (2 = BC1) at +32, …
        trailer = struct.pack("<8I", width, height, 1, 0, 0, 0, 1, 0) + struct.pack("<I", 2) + b"\0" * 16
        payload = b"\0" * 40 + texture.TEXMAPDATA_MAGIC + struct.pack("<II", len(surface), 7) + surface + trailer
        image = operators._gui_image(payload)
        self.assertEqual(image.size, (width, height))
        self.assertEqual(image.getpixel((5, 3))[:3], (255, 0, 0))


class MatchSkinsTest(unittest.TestCase):
    SKINS = [
        {"file": "a", "code": "FAMASG2", "material": "W_AR_FAMASG2_UNISKIN_Gold", "bones": [1, 2, 3, 4, 9]},
        {"file": "b", "code": "Famas", "material": "W_AR_Famas_UNISKIN_Wave", "bones": [1, 2, 3, 4]},
        {"file": "c", "code": "L85A2", "material": "W_AR_L85A2_UNISKIN_Gold", "bones": [1, 2, 3, 4]},
        {"file": "d", "code": "R4-C", "material": "W_AR_R4-C_Y5S4_USA", "bones": [1, 2, 5]},
        {"file": "e", "code": "M4", "material": "W_AR_M4_UNISKIN_Cobalt", "bones": [1, 2, 5, 6]},
        {"file": "h", "code": "R4-C", "material": "W_AR_R4-C_Y5S4_ProTeam", "bones": [1, 2, 5]},
        {"file": "f", "code": "USP45", "material": "W_SA_USP45_Kenya_2019", "bones": [1, 7]},
        {"file": "g", "code": "UMP45", "material": "W_SMG_UMP45_Kenya_2019", "bones": [1, 8]},
    ]

    def files(self, label, bones, names=()):
        return sorted(s["file"] for s in operators.match_skins(label, bones, list(names), self.SKINS))

    def test_names_join_their_spellings(self):
        self.assertEqual(self.files("FAMAS G2", [1, 2]), ["a", "b"])

    def test_aliases_and_bones(self):
        self.assertEqual(self.files("REMINGTON R4", [1, 5]), ["d", "e", "h"])

    def test_bones_keep_lookalike_names_apart(self):
        self.assertEqual(self.files("UMP 45", [1, 8]), ["g"])

    def test_nameless_weapon_votes_with_its_skins_names(self):
        self.assertEqual(self.files("", [1, 2], ["Y5S4_USA", "Y5S4_ProTeam"]), ["d", "h"])
        self.assertEqual(self.files("", [1, 2], ["Kenya_2019"]), [])  # a tie between two codes: nothing


if __name__ == "__main__":
    unittest.main()
