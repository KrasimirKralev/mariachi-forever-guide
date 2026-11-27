"""Regression tests for the fourth audit (B = blocker, S = should fix, U = owner's call, N = nit).
Each failed on the audited tree (or on a mutant of the fix, for test gaps) and passes after its fix."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from forever import installer, net, paths
from forever.data import Store
from tests import fixtures
from tests.fakenet import FakeNet, forever_routes
from tests.test_round1 import Base, write

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOTED = hasattr(os, 'geteuid') and os.geteuid() == 0
MODES = unittest.skipIf(ROOTED or os.name != 'posix', 'file modes need a non-root POSIX user')


class Locks(Base):
    def setUp(self):
        super().setUp()
        self.locked = []
        self.addCleanup(self.unlock)

    def lock(self, path, mode):
        os.chmod(path, mode)
        self.locked.append(path)

    def unlock(self):
        for p in reversed(self.locked):
            os.chmod(p, 0o755 if os.path.isdir(p) else 0o644)


# ---- B1: a side file that cannot be read or written does not cost the answer ----------------------------------
@MODES
class B1SideFiles(Locks):
    def test_b1a_a_tooltip_that_cannot_be_kept_is_still_shown(self):
        self.update()
        routes = {'https://nether.wowhead.com/forever/tooltip/item/900004':
                  json.dumps({'name': 'Mock Wand', 'tooltip': '<b>Mock Wand</b><br>+3 Mock Power'}).encode(),
                  'https://nether.wowhead.com/forever/tooltip/quest/990001':
                  json.dumps({'name': 'Mock Quest', 'tooltip': '<b>Mock Quest</b><br>- Mock Silk (5)'}).encode()}
        self.lock(self.cache, 0o555)
        os.environ.pop('FOREVER_OFFLINE')
        with mock.patch('forever.net.urllib.request.build_opener') as build:
            build.return_value.open = FakeNet(routes)
            rc, text = self.run_cli('item', 'Mock Wand')
            self.assertEqual(rc, 0, text)
            self.assertIn('+3 Mock Power', text)
            rc, text = self.run_cli('quest', 'Mock Quest')
            self.assertEqual(rc, 0, text)
            self.assertIn('needs: Mock Silk (5)', text)

    def test_b1b_an_unreadable_quest_cache_is_skipped_with_a_note(self):
        self.lock(os.path.join(self.game, 'Cache', 'WDB', 'enUS', 'questcache.wdb'), 0)
        s, rc, fake = self.update()
        text = '\n'.join(self.lines)
        self.assertEqual(rc, 0, text)
        self.assertIn("your game's quest cache could not be read", text)
        self.assertNotIn('cannot be written', text)
        self.assertTrue(os.path.exists(os.path.join(self.cache, 'forever.db')))

    def test_b1c_an_unreadable_wish_list(self):
        rc, text = self.run_cli('me')  # makes the config folder the tool's
        write(os.path.join(self.conf, 'wishlist.txt'), 'Mock Ring\n')
        self.lock(os.path.join(self.conf, 'wishlist.txt'), 0)
        rc, text = self.run_cli('me', 'missing')
        self.assertEqual(rc, 0, text)
        self.assertIn('Empty slots:', text)
        self.assertIn('Wish list: not readable (', text)
        self.assertNotIn('wish list not readable', text)  # N4 (audit 5): said once


# ---- B2: one folder for both roles ---------------------------------------------------------------------------
class B2OneOwnFolder(Base):
    def test_b2_uninstall_and_purge_with_one_folder_for_both_roles(self):
        shared = os.path.join(self.t.root, 'one')
        with mock.patch.dict(os.environ, {'FOREVER_CACHE_DIR': shared, 'FOREVER_CONFIG_DIR': shared}):
            rc, text = self.run_cli('setup', '--no-download')
            self.assertEqual(rc, 0, text)
            s, rc, fake = self.update(cache=shared)
            self.assertEqual(rc, 0, '\n'.join(self.lines))
            rc, text = self.run_cli('setup', '--uninstall')
            self.assertEqual(rc, 0, text)
            self.assertTrue(os.path.exists(os.path.join(shared, paths.MARKER)))
            self.assertTrue(os.path.exists(os.path.join(shared, 'forever.db')))
            self.assertFalse(os.path.exists(os.path.join(shared, 'config.json')))
            self.lines = []
            s, rc, fake = self.update(cache=shared)
            self.assertEqual(rc, 0, '\n'.join(self.lines))
            rc, text = self.run_cli('setup', '--no-download')
            self.assertEqual(rc, 0, text)
            rc, text = self.run_cli('setup', '--uninstall', '--purge')
            self.assertEqual(rc, 0, text)
            self.assertNotIn('left alone', text)
        self.assertFalse(os.path.exists(shared))


# ---- B3, S1: the last lines that print a folder or an error's text -------------------------------------------
class B3S1Masked(unittest.TestCase):
    HOME_NAME, ACCOUNT_NAME = 'homeofzorba', 'ZORBAACCOUNT'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fg-r5-')
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, self.HOME_NAME)
        self.game = fixtures.fake_game(os.path.join(self.home, 'Games'))
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('FOREVER_', 'XDG_'))}
        self.env.update(HOME=self.home, FOREVER_OFFLINE='1')
        self.locked = []
        self.addCleanup(self.unlock)

    def unlock(self):
        for p in reversed(self.locked):
            os.chmod(p, 0o755)

    def clean(self, text, what):
        self.assertNotIn(self.HOME_NAME, text, what)
        self.assertNotIn(self.ACCOUNT_NAME, text, what)

    def test_b3_the_wrong_folder_answer_is_masked(self):
        lines = []
        answers = iter([os.path.join(self.home, 'not', 'the', 'game'), ''])
        with mock.patch.dict(os.environ, {'HOME': self.home}):
            installer.ask_for_game(lambda prompt: next(answers), lines.append)
        text = '\n'.join(lines)
        self.assertIn('not a WoW Forever folder', text)
        self.clean(text, 'ask_for_game')

    def test_s1_the_general_error_line_is_masked(self):
        conf = paths.config_dir(self.env, None, self.home)
        os.makedirs(os.path.join(conf, 'config.json.tmp'))  # a folder where a file must go
        r = subprocess.run([sys.executable, '-B', '-I', os.path.join(ROOT, 'forever'), 'setup', '--no-download',
                            '--game', self.game], capture_output=True, text=True, env=self.env, cwd=self.tmp.name)
        text = r.stdout + r.stderr
        self.assertIn('something went wrong', text)
        self.clean(text, 'setup')

    @MODES
    def test_s1_the_two_update_problem_lines_are_masked(self):
        cache = paths.cache_dir(self.env, None, self.home)
        lines = []
        with mock.patch.dict(os.environ, {'HOME': self.home}):
            s = Store(cache=cache, game=self.game, http=net.Http(offline=False, opener=FakeNet(forever_routes()),
                                                                 sleep=lambda s: None), out=lines.append)
            s.update()
            os.remove(os.path.join(cache, 'raw', 'wago', '9.9.9.12345', 'TaxiNodes.csv'))
            for d in (os.path.join(cache, 'raw', 'foreverdb'), os.path.join(cache, 'raw', 'wago', '9.9.9.12345')):
                os.chmod(d, 0o555)
                self.locked.append(d)
            routes = forever_routes()
            man = json.loads(routes['https://foreverdb.net/downloads/addon-manifest.json'])
            man['data']['version'] = 'a newer one'
            routes['https://foreverdb.net/downloads/addon-manifest.json'] = json.dumps(man).encode()
            lines.clear()
            s2 = Store(cache=cache, game=self.game, http=net.Http(offline=False, opener=FakeNet(routes),
                                                                  sleep=lambda s: None), out=lines.append)
            s2.update()
            s.close()
            s2.close()
        text = '\n'.join(lines)
        self.assertIn('game tables not downloaded:', text)
        self.assertIn('ForeverDB not refreshed', text)
        self.clean(text, 'update')


# ---- U3, N2: masking on Windows and at a word's end ----------------------------------------------------------
class U3N2Mask(unittest.TestCase):
    def test_n2_the_home_is_replaced_only_as_a_whole_folder(self):
        env = {'HOME': '/srv/alice'}
        self.assertEqual(paths.mask('/srv/alicebob/x and /srv/alice/y and /srv/alice', env, system='Linux'),
                         '/srv/alicebob/x and ~/y and ~')
        self.assertEqual(paths.show('/srv/alicebob/x', env), '/srv/alicebob/x')

    def test_u3_windows_paths_in_another_case_and_with_doubled_backslashes(self):
        env = {'USERPROFILE': 'D:\\Profiles\\Zorba'}
        text = ("[WinError 5] Access is denied: 'd:\\\\profiles\\\\zorba\\\\Games\\\\WTF\\\\Account\\\\ZORBAACCOUNT\\\\x' "
                "and D:\\Profiles\\ZORBA\\b")
        masked = paths.mask(text, env, system='Windows')
        self.assertNotIn('zorba', masked.lower())
        self.assertIn('<account>', masked)
        self.assertEqual(paths.mask('d:\\profiles\\zorba\\x', env, system='Linux'), 'd:\\profiles\\zorba\\x')


class U2Notice(unittest.TestCase):
    def test_u2_the_notice_sentence(self):
        with open(os.path.join(ROOT, 'NOTICE.md'), encoding='utf-8') as fh:
            notice = ' '.join(fh.read().split())
        self.assertIn('in the data line of every lookup (`item`, `quest`, `where`, `me quests "<name>"`, `me xp`), '
                      "and here; item names that the other `me` parts and `price` print come from the game's tables "
                      "and, where those have none, from ForeverDB's name lists.", notice)


if __name__ == '__main__':
    unittest.main()
