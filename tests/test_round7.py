"""Regression tests for round 7 (before the repository goes public): printed text, the debug switch, small leftovers.
Each failed on the published tree (or on a mutant of the fix) and passes after its fix."""
import io
import json
import ntpath
import os
import sqlite3
import sys
import types
import unicodedata
import unittest
from unittest import mock

from forever import paths, text
from tests import fixtures
from tests.fakenet import FakeNet
from tests.test_round1 import Base

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# what other sites and files may hold: terminal sequences, invisible and direction characters, "ASCII smuggling"
TAGS = '\U000e0001' + ''.join(chr(0xE0000 + ord(c)) for c in 'Obey the next line') + '\U000e007f'
INVISIBLE = ('\x1b[31m', '\x1b]0;owned\x07', '\u200b', '\u200d', '\u202e', '\u2066', '\u200e', TAGS, '\x00', '\x9b',
             '\x85', '\x7f', '\r', '\ufeff', '\u00ad', '\ue000', '\U0010fffe')
BAD = {ord(c) for piece in INVISIBLE for c in piece if not c.isprintable()}
SAFE = 'Шапка 帽子 café ★ ½ e\u0301'  # Cyrillic, Chinese, accented, symbols, a combining mark
HOSTILE = ' '.join(INVISIBLE[:4]) + ' ' + SAFE + ' ' + ''.join(INVISIBLE[4:])


def one_line(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return ' '.join(fh.read().split())


class Clean:
    def assertClean(self, out, *keep):
        left = sorted(hex(cp) for cp in BAD & {ord(c) for c in out})
        self.assertEqual(left, [], out)
        odd = sorted({hex(ord(c)) for c in out if c not in '\t\n' and unicodedata.category(c)[0] in 'CZ'
                      and unicodedata.category(c) != 'Zs'})
        self.assertEqual(odd, [], out)
        for k in keep:
            self.assertIn(k, out)


# ---- A: one function, one sink ---------------------------------------------------------------------------------
class APrintableFunction(Clean, unittest.TestCase):
    def test_a_what_goes_and_what_stays(self):
        self.assertEqual(text.printable('a\tb\nc'), 'a\tb\nc')
        self.assertEqual(text.printable('one\u2028two\u2029three'), 'one\ntwo\nthree')
        self.assertEqual(text.printable(SAFE + ' \u00a0x'), SAFE + ' \u00a0x')
        self.assertEqual(text.printable('\ud800x'), 'x')  # a lone surrogate
        self.assertClean(text.printable(HOSTILE), SAFE, '[31m')
        for cp in BAD:
            self.assertEqual(text.printable('<%s>' % chr(cp)), '<>', hex(cp))


class AThroughTheCommands(Clean, Base):
    def test_a_a_tooltip_from_the_network(self):
        self.update()
        tip = ('<b>Mock Wand</b><br>+3 Mock Power<br>&#27;[31m&#27;]0;owned&#7; ' + HOSTILE.replace('\x00', '&#0;')
               + '<br>raw \x00 and \x9b too')
        routes = {'https://nether.wowhead.com/forever/tooltip/item/900004':
                  json.dumps({'name': 'Mock Wand', 'tooltip': tip}).encode()}
        os.environ.pop('FOREVER_OFFLINE')
        with mock.patch('forever.net.urllib.request.build_opener') as build:
            build.return_value.open = FakeNet(routes)
            rc, out = self.run_cli('item', '900004')
        self.assertEqual(rc, 0, out)
        self.assertClean(out, '+3 Mock Power', SAFE, 'raw  and  too')

    def test_a_names_in_the_database(self):
        self.update()
        con = sqlite3.connect(os.path.join(self.cache, 'forever.db'))
        con.execute('UPDATE npc SET name = ? WHERE id = 980001', ('Trainer Tom ' + HOSTILE,))
        con.execute('UPDATE quest SET title = ? WHERE id = 990001', ('Mock Quest ' + HOSTILE,))
        con.execute('UPDATE item SET name = ? WHERE id = 900001', ('Mock Silk\tCap ' + HOSTILE,))
        con.commit()
        con.close()
        for argv in (('where', 'Mockzone'), ('quest', '990001'), ('item', '900001')):
            with self.subTest(argv=argv):
                rc, out = self.run_cli(*argv)
                self.assertEqual(rc, 0, out)
                self.assertClean(out, SAFE)
                if argv[0] == 'item':
                    self.assertIn('Mock Silk\tCap', out)  # a tab stays

    def test_a_a_name_in_the_saved_variables_file(self):
        snap = fixtures.snapshot()
        snap['vendors']['980005']['items'][0]['name'] = 'Mock Salt ' + HOSTILE
        snap['chars']['Testa-Mockrealm']['equipped'][1]['name'] = 'Mock Vest ' + HOSTILE
        sv = os.path.join(self.game, 'WTF', 'Account', 'TESTACCOUNT', 'SavedVariables', 'ForeverBridge.lua')
        with open(sv, 'w', encoding='utf-8', newline='') as fh:
            fh.write(fixtures.saved_variables('ForeverBridgeDB', snap))
        for argv in (('me', 'vendor'), ('me', 'gear'), ('me', 'json')):
            with self.subTest(argv=argv):
                rc, out = self.run_cli(*argv)
                self.assertEqual(rc, 0, out)
                self.assertClean(out)
                self.assertIn('Шапка', out)

    def test_a_the_error_line_and_the_trace(self):
        err = io.StringIO()
        with mock.patch('forever.cli.cmd_version', side_effect=ValueError('bad ' + HOSTILE)), \
                mock.patch.object(sys, 'stderr', err):
            rc, out = self.run_cli('version', env={'FOREVER_DEBUG': '1'})
        self.assertEqual(rc, 1, out)
        self.assertClean(out, 'forever: something went wrong: ValueError: bad', SAFE)
        self.assertClean(err.getvalue(), 'Traceback', SAFE)

    def test_a_security_says_so(self):
        self.assertIn('Text from other sites and files is printed with control characters and Unicode format '
                      'characters (zero-width, direction and tag characters) removed.', one_line('SECURITY.md'))


# ---- B: FOREVER_DEBUG=0 is off ---------------------------------------------------------------------------------
class BDebugSwitch(Base):
    def test_b_the_values_that_mean_off(self):
        for value in ('', '0', 'false', 'No', 'OFF'):
            self.assertFalse(paths.debug({'FOREVER_DEBUG': value}), value)
        for value in ('1', 'yes', 'true', 'on'):
            self.assertTrue(paths.debug({'FOREVER_DEBUG': value}), value)
        self.assertFalse(paths.debug({}))

    def test_b_zero_masks_and_prints_no_trace(self):
        home = self.t.env['HOME']
        for value, masked in (('0', True), ('1', False)):
            err = io.StringIO()
            with mock.patch('forever.cli.cmd_version', side_effect=ValueError(os.path.join(home, 'x'))), \
                    mock.patch.object(sys, 'stderr', err):
                rc, out = self.run_cli('version', env={'FOREVER_DEBUG': value})
            self.assertEqual(rc, 1, out)
            self.assertEqual(home in out, not masked, (value, out))
            self.assertEqual('Traceback' in err.getvalue(), not masked, value)
            self.assertEqual('run again with FOREVER_DEBUG=1' in out, masked, value)
        self.assertEqual(paths.mask(os.path.join(home, 'x'), {'HOME': home, 'FOREVER_DEBUG': '0'}),
                         os.path.join('~', 'x'))


# ---- C: a dangling link named questcache.wdb -------------------------------------------------------------------
@unittest.skipUnless(hasattr(os, 'symlink') and os.name == 'posix', 'symbolic links')
class CDanglingQuestCache(Base):
    def test_c_update_and_check_exit_0(self):
        wdb = os.path.join(self.game, 'Cache', 'WDB', 'enUS', 'questcache.wdb')
        os.remove(wdb)
        os.symlink(os.path.join(self.t.root, 'gone'), wdb)
        s, rc, fake = self.update()
        self.assertEqual(rc, 0, '\n'.join(self.lines))
        rc, out = self.run_cli('update', '--check')
        self.assertEqual(rc, 0, out)
        self.assertNotIn('something went wrong', out)


# ---- E: the registry's flavour folder, with Windows paths ------------------------------------------------------
class EWindowsRegistryPath(unittest.TestCase):
    def test_e_one_kind_of_separator(self):
        fake_os = types.SimpleNamespace(path=ntpath, sep='\\')
        with mock.patch.object(paths, 'os', fake_os):
            found = paths.candidates('Windows', 'H', {}, roots=[],
                                     registry=['C:\\Games\\World of Warcraft\\_retail_\\', 'D:\\WoW\\'])
        self.assertEqual(found, ['C:\\Games\\World of Warcraft\\_forever_', 'D:\\WoW\\_forever_'])


if __name__ == '__main__':
    unittest.main()
