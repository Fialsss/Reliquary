"""The credentials flow against a fake DepotDownloader that asks like the real one (prompts with no newline)."""
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from reliquary import env, settings, vault

FAKE = r'''
import sys
def ask(text):
    sys.stdout.write(text)
    sys.stdout.flush()
    return sys.stdin.readline().strip()
password = ask('Enter account password for "demo": ')
print()
if password != "hunter2":
    print("Failed to authenticate with Steam: InvalidPassword")
    sys.exit(1)
code = ask("STEAM GUARD! Please enter your 2-factor auth code from your authenticator app: ")
while code != "AB12C":  # like DepotDownloader: say so, then ask again
    sys.stderr.write("The previous 2-factor auth code you have provided is incorrect.\n")
    code = ask("STEAM GUARD! Please enter your 2-factor auth code from your authenticator app: ")
print()
print("Got 3 licenses for account!")
print("Got manifest")
'''


class CredentialsLoginTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = (settings.HOME, settings.FILE, env.STORE_NOTE, env.ISOLATED, vault._ensure_tool, vault.emit)
        settings.HOME, settings.FILE = self.tmp, self.tmp / "settings.json"
        env.STORE_NOTE, env.ISOLATED = self.tmp / "steam-store.txt", self.tmp / "isolated"
        (self.tmp / "fake_depot.py").write_text(FAKE, encoding="utf-8")
        tool = self.tmp / "DepotDownloader.cmd"
        tool.write_text(f'@"{sys.executable}" -u "%~dp0fake_depot.py" %*\n', encoding="utf-8")
        vault._ensure_tool = lambda: tool
        self.events = []
        vault.emit = lambda name, data=None: self.events.append((name, data))

    def tearDown(self):
        settings.HOME, settings.FILE, env.STORE_NOTE, env.ISOLATED, vault._ensure_tool, vault.emit = self.saved

    def run_login(self, password, *codes):
        # the window answers each Steam Guard question as it's asked, in order
        def answer():
            for n, code in enumerate(codes, start=1):
                while sum(name == "steam.code" for name, _ in self.events) < n:
                    threading.Event().wait(0.05)
                vault.provide_code(code)
        threading.Thread(target=answer, daemon=True).start()
        return vault._run(["-manifest-only"], {"username": "demo", "password": password})

    def test_wrong_code_then_right_code(self):
        log = self.run_login("hunter2", "ZZ999", "AB12C")
        self.assertIn("Got manifest", log)
        codes = [data for name, data in self.events if name == "steam.code"]
        self.assertEqual(codes, [{"kind": "app", "retry": False}, {"kind": "app", "retry": True}])

    def test_password_and_code_reach_the_tool(self):
        log = self.run_login("hunter2", "AB12C")
        self.assertIn("Got manifest", log)
        self.assertEqual(settings.load()["steam_user"], "demo")
        self.assertIn(("steam.code", {"kind": "app", "retry": False}), self.events)
        # the password is never echoed back as an event
        self.assertFalse(any("hunter2" in str(data) for _, data in self.events))

    def test_welcome_comes_as_soon_as_steam_accepts(self):
        self.run_login("hunter2", "AB12C")
        signed = self.events.index(("steam.signed_in", {"user": "demo"}))
        self.assertLess(signed, self.events.index(("vault.log", "Got manifest")))  # not after the whole job
        self.assertEqual(sum(name == "steam.signed_in" for name, _ in self.events), 1)

    def test_wrong_password_is_reported(self):
        with self.assertRaises(vault.Failure) as caught:
            self.run_login("nope", "AB12C")
        self.assertEqual(str(caught.exception), "error.wrongPassword")

    def test_prompt_kinds(self):
        self.assertEqual(vault.prompt_kind('Enter account password for "x": '), "password")
        self.assertEqual(vault.prompt_kind("STEAM GUARD! Please enter the auth code sent to the email at a@b.c: "), "code_email")
        self.assertIsNone(vault.prompt_kind("Connecting to Steam3..."))


if __name__ == "__main__":
    unittest.main()
