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


class NamesTest(unittest.TestCase):
    def test_side_is_the_list_before_property_2f73b62b(self):
        before, after = bytes.fromhex("0d8152e3"), bytes.fromhex("2f73b62b")
        noise = before + struct.pack("<I", 1) + b"\1" * 8 + b"\0" * 4  # the same tag elsewhere, not followed by it
        attacker = noise + before + struct.pack("<I", 0) + after
        defender = noise + before + struct.pack("<IQ", 1, 0x47A08A8F8C) + after
        self.assertEqual((operators._side(attacker), operators._side(defender), operators._side(b"")), ("attack", "defense", ""))

    def test_catalog_names_seasons_and_kinds(self):
        from reliquary import catalog

        def item(name_id, *tags):
            return {"nameId": name_id, "tags": list(tags)}

        platinum = item("weapon_charms_universal.Y1S3.Season_Rank_reward_Platinum_.DUST_LINE_PLATINUM", "Y1S3", "rarity_superrare")
        self.assertEqual(catalog.describe(platinum), {"name": "Dust Line Platinum", "season": "Y1S3", "rarity": "superrare"})
        self.assertEqual((catalog.family(platinum), catalog.rank(platinum)), ("ranked", "platinum"))
        hex_named = item("Charm.Y8S3.GO_Y8S3_Influencer_Rasco.0x5c7390c1ee", "Y8S3")
        self.assertEqual(catalog.name(hex_named), "Influencer Rasco")
        glory = item("weapon_skins.Y1_MC.R4-C.VC-W_AR_R4C-FBI-R6Siege_Unique-PerCTU.GLORY", "rarity_rare")
        self.assertEqual((catalog.name(glory), catalog.season(glory)), ("Glory", "Y1"))
        major = item("weapon_charms_universal.Y5S2.Drop_TBD_02.SIX_MAJOR_USA_COPPER_2020", "Y5S2")
        self.assertEqual((catalog.family(major), catalog.rank(major)), ("esports", ""))

    def test_cache_documents_meet_their_catalog_items(self):
        from reliquary import catalog

        entries = [{"_words": {"y3s2", "signature", "marble", "ancient"}}, {"_words": {"y4s2", "collection", "marble", "and", "gold"}}]
        catalog.attach(entries, [{"file": "a", "w": {"signature", "marble"}}, {"file": "b", "w": {"marble"}}], lambda d: d["w"])
        self.assertEqual([e.get("file") for e in entries], ["a", None])  # "marble" alone fits both: left alone

    def test_sight_names_read_like_the_game(self):
        self.assertEqual([operators._sight_name(n) for n in ("RedDot", "IRON SIGHT [PLACEHOLDER]", "EosHolo", "SCOPE 2.5x A")],
                         ["Red Dot", "Iron Sight", "Holo", "Scope 2.5x A"])


if __name__ == "__main__":
    unittest.main()
