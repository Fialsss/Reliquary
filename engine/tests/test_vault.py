import random
import unittest

from reliquary.vault import parse_manifest, qr_matrix


def sample_matrix(size=29, seed=7):
    rng = random.Random(seed)
    rows = ["".join(rng.choice("01") for _ in range(size)) for _ in range(size)]
    # finder-like left column so the left edge is always dark somewhere
    return ["1" + r[1:] for r in rows]


class QrTest(unittest.TestCase):
    def test_full_blocks(self):
        matrix = sample_matrix()
        text = ["", " " * 20] + ["        " + "".join("██" if c == "1" else "  " for c in r) + "        " for r in matrix] + [""]
        self.assertEqual(qr_matrix(text), matrix)

    def test_half_blocks(self):
        matrix = sample_matrix(size=25)
        padded = matrix + ["0" * 25]
        text = []
        for top, bottom in zip(padded[::2], padded[1::2]):
            chars = {("1", "1"): "█", ("1", "0"): "▀", ("0", "1"): "▄", ("0", "0"): " "}
            text.append("    " + "".join(chars[(a, b)] for a, b in zip(top, bottom)))
        self.assertEqual(qr_matrix(text), matrix)


class ManifestTest(unittest.TestCase):
    def test_rows(self):
        text = """Content Manifest for Depot 359551

          Size Chunks File SHA                                 Flags Name
        172200      1 96fadc51a01277fd7311a463c974516a4b7f6dcd     0 amd_ags_x64.dll
             0      0 0000000000000000000000000000000000000000    40 BattlEye
    9176481792   8751 1111111111111111111111111111111111111111     0 datapc64_merged_bnk_textures1.forge
     123456789    118 2222222222222222222222222222222222222222     0 datapc64_ondemand.forge
          4096      1 3333333333333333333333333333333333333333     0 datapc64_ondemand.depgraphbin
"""
        files = parse_manifest(text)
        self.assertEqual([f["name"] for f in files], [
            "datapc64_merged_bnk_textures1.forge", "datapc64_ondemand.depgraphbin", "datapc64_ondemand.forge"])
        self.assertEqual(files[0]["category"], "textures")
        self.assertEqual(files[0]["size"], 9176481792)
        self.assertEqual(files[2]["category"], "data")


if __name__ == "__main__":
    unittest.main()
