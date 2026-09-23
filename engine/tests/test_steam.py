import base64
import json
import unittest
import zlib

from reliquary.steam import accounts_in_config, steamid_from_config


def b64(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def token(steamid: str) -> bytes:
    # Steam's tokens carry spaces in their JSON, so they start with "eyAi", not "eyJ"
    header = b64(b'{ "typ": "JWT", "alg": "EdDSA" }')
    payload = b64(json.dumps({"iss": "steam", "sub": steamid, "aud": ["client"]}, indent=1).encode())
    return header + b"." + payload + b"." + b64(b"signature" * 8)


def varint(n: int) -> bytes:
    out = b""
    while True:
        byte, n = n & 0x7F, n >> 7
        out += bytes([byte | (0x80 if n else 0)])
        if not n:
            return out


def account_config(tokens: dict[str, str]) -> bytes:
    """Same shape as DepotDownloader's file: raw deflate of a protobuf map<string, string> (field 4)."""
    body = b""
    for user, sid in tokens.items():
        value = token(sid)
        entry = b"\x0a" + bytes([len(user)]) + user.encode() + b"\x12" + varint(len(value)) + value
        body += b"\x22" + varint(len(entry)) + entry
    deflate = zlib.compressobj(wbits=-15)
    return deflate.compress(body) + deflate.flush()


class AccountConfigTest(unittest.TestCase):
    raw = account_config({"first_user": "76561198000000001", "second.user": "76561198000000002"})

    def test_steamid_per_account(self):
        self.assertEqual(steamid_from_config(self.raw, "first_user"), "76561198000000001")
        self.assertEqual(steamid_from_config(self.raw, "second.user"), "76561198000000002")

    def test_unknown_account_or_garbage(self):
        self.assertIsNone(steamid_from_config(self.raw, "nobody"))
        self.assertIsNone(steamid_from_config(b"not deflate", "first_user"))

    def test_account_names(self):
        self.assertEqual(accounts_in_config(self.raw), ["first_user", "second.user"])


if __name__ == "__main__":
    unittest.main()
