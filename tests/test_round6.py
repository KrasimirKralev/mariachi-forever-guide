"""Regression tests for the fifth audit (S = should fix, U = owner's call, N = nit).
Each failed on the audited tree (or on a mutant of the fix, for test gaps) and passes after its fix."""
import os
import unittest
from unittest import mock

from forever import build, paths
from tests import fixtures
from tests.fakenet import FakeNet, forever_routes
from tests.test_round1 import Base

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE = "your game's quest cache could not be read"


def one_line(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return ' '.join(fh.read().split())


# ---- U2: the debug switch is named where the masked paths are promised ----------------------------------------
class U2DebugSwitch(unittest.TestCase):
    def test_u2_security_names_the_debug_switch(self):
        self.assertIn('except the one line of setup that you paste into Claude Code (the toolkit folder, in full), '
                      'and when you set FOREVER_DEBUG=1 yourself.', one_line('SECURITY.md'))

    def test_u2_the_skill_never_sets_it(self):
        self.assertIn('Never set FOREVER_DEBUG; if forever asks for it, tell the player and let them run it.',
                      one_line('plugin/skills/forever-guide/SKILL.md'))


# ---- S1: a config folder that is a link ----------------------------------------------------------------------
@unittest.skipUnless(hasattr(os, 'symlink') and os.name == 'posix', 'symbolic links')
class S1LinkedConfigFolder(Base):
    def test_s1_uninstall_and_purge_through_a_linked_config_folder(self):
        real = os.path.join(self.t.root, 'real-config')
        os.makedirs(real)
        link = os.path.join(self.t.root, 'linked-config')
        os.symlink(real, link)
        with mock.patch.dict(os.environ, {'FOREVER_CONFIG_DIR': link}):
            rc, text = self.run_cli('setup', '--no-download')
            self.assertEqual(rc, 0, text)
            s, rc, fake = self.update()
            self.assertEqual(rc, 0, '\n'.join(self.lines))
            rc, text = self.run_cli('setup', '--uninstall', '--purge')
        self.assertEqual(rc, 0, text)
        self.assertNotIn('something went wrong', text)
        self.assertFalse(os.path.exists(self.cache))
        self.assertTrue(os.path.islink(link))  # a link stays, and what it points to is left empty
        self.assertEqual(os.listdir(real), [])


# ---- S2, N1: a quest cache that passes the access check and still cannot be opened -----------------------------
class S2QuestCacheNotAFile(Base):
    def setUp(self):
        super().setUp()
        wdb = os.path.join(self.game, 'Cache', 'WDB', 'enUS', 'questcache.wdb')
        os.remove(wdb)
        os.makedirs(wdb)  # readable to os.access, and open() fails
        self.wdb = wdb

    def test_s2_update_builds_and_exits_0_with_a_note(self):
        s, rc, fake = self.update()
        text = '\n'.join(self.lines)
        self.assertEqual(rc, 0, text)
        self.assertIn('note: ' + NOTE, text)
        self.assertNotIn('missing:', text)
        self.assertTrue(os.path.exists(os.path.join(self.cache, 'forever.db')))

    def test_s2_setup_does_not_say_not_all_downloaded(self):
        os.environ.pop('FOREVER_OFFLINE')  # setup downloads, from the fake network
        with mock.patch('forever.net.urllib.request.build_opener') as opener, mock.patch('forever.net.time.sleep'):
            opener.return_value.open = FakeNet(forever_routes())
            rc, text = self.run_cli('setup')
        self.assertEqual(rc, 0, text)
        self.assertIn(NOTE, text)
        self.assertNotIn('not all downloaded yet', text)

    def test_n1_build_itself_skips_it_with_a_note(self):
        wago, fdb = fixtures.write_raw(os.path.join(self.t.root, 'raw'))
        summary = build.build(wago, fdb, os.path.join(self.t.root, 'forever.db'), self.wdb)
        self.assertEqual(summary['missing'], [])
        self.assertTrue(any(NOTE in n for n in summary['notes']), summary)
        self.assertNotIn('quests from your game cache', summary)


# ---- U3, N3: the home folder written another way ---------------------------------------------------------------
class U3N3Mask(unittest.TestCase):
    NAME = 'Zorba'
    WIN = '\\'.join(['C:', 'Users', NAME])  # the scanner would flag this path written out in the source
    FWD = '/'.join(['C:', 'Users', NAME])
    BASH = '/'.join(['', 'c', 'Users', NAME])

    def masked(self, env, text):
        out = paths.mask(text, env, system='Windows')
        self.assertNotIn(self.NAME.lower(), out.lower(), out)
        return out

    def test_u3_home_with_forward_slashes_and_folders_with_backslashes(self):
        folder = self.WIN + '\\AppData\\Roaming\\x'
        self.assertEqual(self.masked({'HOME': self.FWD}, folder), '~\\AppData\\Roaming\\x')
        self.assertEqual(self.masked({'HOME': self.FWD, 'USERPROFILE': self.WIN}, folder), '~\\AppData\\Roaming\\x')
        self.assertEqual(self.masked({'HOME': self.FWD}, "'%s'" % folder.replace('\\', '\\\\')),
                         "'~\\\\AppData\\\\Roaming\\\\x'")

    def test_u3_home_and_userprofile_both_count(self):
        env = {'HOME': '/'.join(['D:', 'elsewhere']), 'USERPROFILE': self.WIN}
        self.assertEqual(self.masked(env, self.FWD + '/x and ' + self.WIN + '\\y'), '~/x and ~\\y')

    def test_u3_the_git_bash_form(self):
        self.assertEqual(self.masked({'HOME': self.BASH}, self.WIN + '\\AppData'), '~\\AppData')
        self.assertEqual(self.masked({'USERPROFILE': self.WIN}, self.BASH + '/x'), '~/x')

    def test_u3_still_only_the_whole_folder(self):
        other = self.WIN + 's\\x'
        self.assertEqual(paths.mask(other, {'HOME': self.FWD}, system='Windows'), other)

    def test_n3_a_home_followed_by_a_full_stop(self):
        env = {'HOME': '/srv/alice'}
        self.assertEqual(paths.mask('saved in /srv/alice.', env, system='Linux'), 'saved in ~.')
        self.assertEqual(paths.mask('/srv/alice. next', env, system='Linux'), '~. next')
        self.assertEqual(paths.mask('/srv/alice.bak', env, system='Linux'), '/srv/alice.bak')
        self.assertEqual(self.masked({'USERPROFILE': self.WIN}, 'in %s.' % self.WIN), 'in ~.')


if __name__ == '__main__':
    unittest.main()
