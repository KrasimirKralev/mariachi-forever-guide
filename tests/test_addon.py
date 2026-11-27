"""Runs the add-on against the mock game in tests/addon_harness.lua (needs a Lua 5.1-compatible runner)."""
import os
import shutil
import subprocess
import tempfile
import unittest

from forever import snapshot

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON = os.path.join(ROOT, 'addon', 'ForeverBridge')
HARNESS = os.path.join(ROOT, 'tests', 'addon_harness.lua')


def lua_runner():
    """The first Lua found: nvim -l (Neovim carries LuaJIT), luajit, lua5.1, then lua."""
    if shutil.which('nvim'):
        return ['nvim', '--clean', '--headless', '-l']
    for name in ('luajit', 'lua5.1', 'lua'):
        if shutil.which(name):
            return [name]
    return None


class AddOn(unittest.TestCase):
    def setUp(self):
        self.runner = lua_runner()
        if not self.runner:
            self.skipTest('no Lua found (install Neovim, LuaJIT or Lua 5.1 to run the add-on harness)')
        self.tmp = tempfile.TemporaryDirectory(prefix='fg-addon-')

    def tearDown(self):
        self.tmp.cleanup()

    def run_variant(self, variant):
        out = os.path.join(self.tmp.name, variant + '.lua')
        r = subprocess.run(self.runner + [HARNESS, ADDON, out, variant], capture_output=True, text=True, timeout=120,
                           cwd=self.tmp.name)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('OK ' + variant, r.stdout)
        return out

    def test_variants_and_the_reader(self):
        for variant in ('modern', 'legacy', 'minimal'):
            with self.subTest(variant=variant):
                out = self.run_variant(variant)
                # the file the harness wrote the way WoW does is read back by the Python reader
                db = snapshot.read_db(out)
                self.assertIsNotNone(db)
                key, char = snapshot.pick(db)
                self.assertEqual(key, 'Testa-Mockrealm')
                if variant != 'minimal':
                    self.assertEqual(len(char['equipped']), 5)
                    self.assertEqual(char['reason'], 'logout')

    def test_toc_matches_the_code(self):
        with open(os.path.join(ADDON, 'ForeverBridge.toc'), encoding='utf-8') as fh:
            toc = fh.read()
        self.assertIn('## SavedVariables: ForeverBridgeDB', toc)
        self.assertIn('ForeverBridge.lua', toc)
        with open(os.path.join(ADDON, 'ForeverBridge.lua'), encoding='utf-8') as fh:
            code = fh.read()
        self.assertIn('SLASH_FOREVERBRIDGE1 = "/fbridge"', code)
        self.assertIn('NOT recorded: chat, whispers, guild notes, friends, other players.', code)
        for word in ('LoggingChat', 'SendChatMessage', 'SendAddonMessage', 'C_ChatInfo'):
            self.assertNotIn(word, code)

    def test_n4_no_test_hook_and_no_shadowed_helper_in_the_shipped_add_on(self):
        with open(os.path.join(ADDON, 'ForeverBridge.lua'), encoding='utf-8') as fh:
            code = fh.read()
        self.assertNotIn('TestMinAge', code)
        self.assertNotIn('local first =', code)
        self.assertNotIn('SlashCmdList = ', code)  # S8: the game's table is never assigned


if __name__ == '__main__':
    unittest.main()
