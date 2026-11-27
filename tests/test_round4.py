"""Regression tests for the third audit (RB = open blocker, RS = should fix, RN = nit of round 3).
Each failed on the audited tree (or on a mutant of the fix, for test gaps) and passes after its fix."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from forever import net, paths
from forever.data import Store
from tests import fixtures
from tests.fakenet import FakeNet, forever_routes
from tests.test_round1 import Base, read, write

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOTED = hasattr(os, 'geteuid') and os.geteuid() == 0


# ---- RB1: one list of names for the gate, whoever asks --------------------------------------------------------


class RB1OneFolderForBothRoles(Base):
    def shared_env(self, shared):
        return {'FOREVER_CACHE_DIR': shared, 'FOREVER_CONFIG_DIR': shared}

    def test_rb1_a_foreign_config_json_in_a_folder_used_for_both(self):
        shared = os.path.join(self.t.root, 'shared')
        write(os.path.join(shared, 'config.json'), '{"other": 1}')
        with mock.patch.dict(os.environ, self.shared_env(shared)):
            s, rc, fake = self.update(cache=shared)
            self.assertEqual(rc, 2, '\n'.join(self.lines))
            rc, text = self.run_cli('setup', '--no-download')
            self.assertEqual(rc, 2, text)
            rc, text = self.run_cli('setup', '--uninstall', '--purge')
        self.assertFalse(os.path.exists(os.path.join(shared, paths.MARKER)))
        self.assertEqual(read(os.path.join(shared, 'config.json')), '{"other": 1}')

    def test_rb1_a_foreign_forever_db_and_me_first(self):
        shared = os.path.join(self.t.root, 'shared')
        write(os.path.join(shared, 'forever.db'), 'not ours')
        with mock.patch.dict(os.environ, self.shared_env(shared)):
            rc, text = self.run_cli('me')
            self.assertEqual(rc, 0, text)
            self.assertFalse(os.path.exists(os.path.join(shared, paths.MARKER)))
            s, rc, fake = self.update(cache=shared)
            self.assertEqual(rc, 2, '\n'.join(self.lines))
        self.assertEqual(read(os.path.join(shared, 'forever.db')), 'not ours')
        self.assertFalse(os.path.exists(os.path.join(shared, 'levels.json')))


# ---- RB2, RS1, RN1, RN5: error lines hold no home and no account folder name ----------------------------------
@unittest.skipIf(ROOTED or os.name != 'posix', 'file modes need a non-root POSIX user')
class RB2ErrorLinesMasked(unittest.TestCase):
    HOME_NAME, ACCOUNT_NAME = 'homeofzorba', 'ZORBAACCOUNT'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fg-rb2-')
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.unlock)
        self.home = os.path.join(self.tmp.name, self.HOME_NAME)
        self.game = fixtures.fake_game(os.path.join(self.home, 'Games'))
        os.rename(os.path.join(self.game, 'WTF', 'Account', 'TESTACCOUNT'),
                  os.path.join(self.game, 'WTF', 'Account', self.ACCOUNT_NAME))
        self.sv = os.path.join(self.game, 'WTF', 'Account', self.ACCOUNT_NAME, 'SavedVariables')
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('FOREVER_', 'XDG_'))}
        self.env.update(HOME=self.home, FOREVER_OFFLINE='1')
        self.cache = paths.cache_dir(self.env, None, self.home)
        self.locked = []
        s = Store(cache=self.cache, game=self.game, http=net.Http(offline=False, opener=FakeNet(forever_routes()),
                                                                  sleep=lambda s: None), out=lambda *_: None)
        s.update()
        s.close()

    def lock(self, path, mode):
        os.chmod(path, mode)
        self.locked.append(path)

    def unlock(self):
        for p in self.locked:
            os.chmod(p, 0o755 if os.path.isdir(p) else 0o644)

    def run_forever(self, *argv, env=None):
        r = subprocess.run([sys.executable, '-B', '-I', os.path.join(ROOT, 'forever')] + list(argv)
                           + ['--game', self.game], capture_output=True, text=True, env=dict(self.env, **(env or {})),
                           cwd=self.tmp.name)
        return r.returncode, r.stdout + r.stderr

    def clean(self, text, what):
        self.assertNotIn(self.HOME_NAME, text, what)
        self.assertNotIn(self.ACCOUNT_NAME, text, what)
        self.assertNotIn('Traceback', text, what)

    def test_rb2_an_unreadable_snapshot(self):
        self.lock(os.path.join(self.sv, 'ForeverBridge.lua'), 0)
        for argv in (('me',), ('me', 'status')):
            rc, text = self.run_forever(*argv)
            self.clean(text, argv)
            self.assertIn('Permission denied', text)
            self.assertNotIn('something went wrong', text)

    def test_rb2_a_folder_named_like_the_snapshot(self):
        os.remove(os.path.join(self.sv, 'ForeverBridge.lua'))
        os.makedirs(os.path.join(self.sv, 'ForeverBridge.lua'))
        rc, text = self.run_forever('me')
        self.clean(text, 'folder')
        self.assertNotIn('something went wrong', text)

    def test_rb2_an_unreadable_auctionator_file(self):
        self.lock(os.path.join(self.sv, 'Auctionator.lua'), 0)
        rc, text = self.run_forever('price', 'Mock Salt')
        self.clean(text, 'price')
        self.assertIn('Permission denied', text)

    def test_rb2_rn5_a_read_only_cache_folder(self):
        # the tool's own cache, now read-only: the database cannot be rebuilt (sqlite: "unable to open database file")
        self.lock(self.cache, 0o555)
        rc, text = self.run_forever('update')
        self.clean(text, 'update')
        self.assertNotIn('OperationalError', text)
        self.assertNotIn('something went wrong', text)
        self.assertIn('cannot be written', text)
        # a cache folder that cannot even be made
        fresh = os.path.join(self.tmp.name, 'readonly-parent')
        os.makedirs(fresh)
        self.lock(fresh, 0o555)
        rc, text = self.run_forever('update', env={'FOREVER_CACHE_DIR': os.path.join(fresh, 'cache')})
        self.assertNotIn('something went wrong', text)
        self.assertIn('cannot be written', text)

    def test_rs1_me_answers_when_its_config_folder_cannot_be_made(self):
        parent = os.path.join(self.tmp.name, 'locked')
        os.makedirs(parent)
        self.lock(parent, 0o555)
        rc, text = self.run_forever('me', env={'FOREVER_CONFIG_DIR': os.path.join(parent, 'config')})
        self.assertEqual(rc, 0, text)
        self.assertIn('Testa-Mockrealm', text)

    def test_rn1_me_file_and_its_error_line(self):
        for argv in (('me', '--file', os.path.join(self.sv, 'ForeverBridge.lua')),
                     ('me', '--file', os.path.join(self.sv, 'Nothing.lua')),
                     ('me', 'status', '--file', os.path.join(self.sv, 'Auctionator.lua'))):
            rc, text = self.run_forever(*argv)
            self.clean(text, argv)

    def test_rb2_the_masking_helper(self):
        env = {'HOME': self.home}
        text = "[Errno 13] Permission denied: '%s/x/WTF/Account/%s/SavedVariables/a.lua' and %s/b" % (
            self.home, self.ACCOUNT_NAME, self.home)
        masked = paths.mask(text, env)
        self.assertNotIn(self.HOME_NAME, masked)
        self.assertNotIn(self.ACCOUNT_NAME, masked)
        self.assertEqual(masked.count('~'), 2)
        err = PermissionError(13, 'Permission denied', os.path.join(self.home, 'f.lua'))
        self.assertEqual(paths.describe(err, env), 'Permission denied: ' + os.path.join('~', 'f.lua'))


@unittest.skipIf(os.name != 'posix' or not hasattr(os, 'symlink'), 'symbolic links')
class RN5DanglingInterface(Base):
    def test_rn5_a_dangling_interface_link(self):
        shutil.rmtree(os.path.join(self.game, 'Interface'))
        os.symlink(os.path.join(self.t.root, 'gone'), os.path.join(self.game, 'Interface'))
        rc, text = self.run_cli('setup', '--no-download', '--force')
        self.assertEqual(rc, 2, text)
        self.assertIn('does not exist', text)
        self.assertNotIn('something went wrong', text)
        self.assertFalse(os.path.exists(os.path.join(self.t.root, 'gone')))


# ---- RN4: nothing is marked when the install is refused -------------------------------------------------------


class RN4MarkOnlyAfterInstall(Base):
    @unittest.skipIf(os.name != 'posix' or not hasattr(os, 'symlink'), 'symbolic links')
    def test_rn4_a_refused_install_leaves_no_marked_folders(self):
        other = os.path.join(self.t.root, 'other')
        os.makedirs(other)
        os.symlink(other, os.path.join(self.addons, 'ForeverBridge'))
        rc, text = self.run_cli('setup', '--no-download')
        self.assertEqual(rc, 2, text)
        self.assertFalse(os.path.exists(self.conf))
        self.assertFalse(os.path.exists(self.cache))


# ---- RS3, RN3, RN7 ------------------------------------------------------------------------------------------------


class RS3Sizes(Base):
    def manifest(self, change):
        routes = forever_routes()
        man = json.loads(routes['https://foreverdb.net/downloads/addon-manifest.json'])
        for f in man['data']['files']:
            change(f)
        routes['https://foreverdb.net/downloads/addon-manifest.json'] = json.dumps(man).encode()
        return routes

    def test_rs3_the_fixture_gives_a_number_like_the_real_manifest_and_it_is_used(self):
        routes = forever_routes()
        man = json.loads(routes['https://foreverdb.net/downloads/addon-manifest.json'])
        self.assertTrue(all(isinstance(f['bytes'], int) for f in man['data']['files']))
        self.update(self.manifest(lambda f: f.update(bytes=5 << 10) if f['path'].endswith('QuestXP.lua') else None))
        self.assertIn('QuestXP.lua (5 KB)', '\n'.join(self.lines))  # the number branch, not "0 KB"

    def test_rs3_a_digit_string_is_accepted_too(self):
        self.update(self.manifest(lambda f: f.update(bytes=str(6 << 10)) if f['path'].endswith('QuestXP.lua') else None))
        self.assertIn('QuestXP.lua (6 KB)', '\n'.join(self.lines))

    def test_rn7_a_huge_published_size_is_not_printed_as_it_comes(self):
        self.update(self.manifest(lambda f: f.update(bytes=10 ** 15) if f['path'].endswith('Loot.lua') else None))
        text = '\n'.join(self.lines)
        self.assertNotIn(str(10 ** 15 // 1024), text)
        self.assertIn('Loot.lua (more than', text)


class RN3MixedSources(Base):
    def test_rn3_read_and_unread_kinds_together(self):
        self.update()
        rc, text = self.run_cli('item', '900051')
        self.assertIn('Quest: Mock Quest', text)
        self.assertIn('and more of kinds not read yet', text)


# ---- RB3, RB4, RB5, RS4, RN2, RN6: texts and files -----------------------------------------------------------
def j(*parts):
    """The numbers this test forbids are put together at run time, so that this file does not hold them."""
    return ''.join(parts)


class Round4Files(unittest.TestCase):
    def text(self, rel):
        with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
            return fh.read()

    def flat(self, rel):
        return ' '.join(self.text(rel).split())

    def test_rb3_rs4_rn2_the_texts_say_what_the_code_does(self):
        notice, readme, security = self.flat('NOTICE.md'), self.flat('README.md'), self.flat('SECURITY.md')
        self.assertIn('in the data line of every lookup (`item`, `quest`, `where`, `me quests "<name>"`, `me xp`)',
                      notice)  # the rest of the sentence: test_round5.U2Notice
        self.assertIn('and its own leftover temporary files', security)
        self.assertIn('it goes on with what is missing', readme)
        self.assertIn('goes on with what is missing', notice)
        self.assertNotIn('resumable', notice)
        self.assertNotIn('continues where it stopped', readme)
        self.assertNotIn('downloaded the first time you run it', readme)
        self.assertIn('`setup` and `update` download', readme)

    def test_rn6_no_writer_of_another_add_on_file_in_the_tests(self):
        self.assertNotIn(j('Old', 'Bridge'), self.text('tests/test_cli.py'))


if __name__ == '__main__':
    unittest.main()
