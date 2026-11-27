"""Regression tests for the second independent audit (NB = new blocker, NS = should fix, nits by number).
Each failed on the audited tree (or on a mutant of it, for the test gaps) and passes after its fix."""
import ast
import glob
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from forever import data, installer, net, paths
from forever import luatable as lt
from forever.data import Store
from tests import fixtures
from tests.fakenet import FakeNet, forever_routes
from tests.test_round1 import Base, read, write

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SV = os.path.join('WTF', 'Account', 'TESTACCOUNT', 'SavedVariables')


def no_network(*a, **k):
    raise AssertionError('a network connection was attempted')


# ---- NB1: one gate decides whether a folder is the tool's own --------------------------------------------------


class NB1OneGate(Base):
    def test_nb1_a_foreign_config_survives_me_setup_and_uninstall(self):
        write(os.path.join(self.conf, 'config.json'), '{"other": 1}')
        rc, text = self.run_cli('me')
        self.assertEqual(rc, 0, text)
        self.assertEqual(sorted(os.listdir(self.conf)), ['config.json'])  # no levels.json, no marker
        rc, text = self.run_cli('setup', '--no-download')
        self.assertEqual(rc, 2, text)
        rc, text = self.run_cli('setup', '--uninstall')
        self.assertEqual(sorted(os.listdir(self.conf)), ['config.json'])
        self.assertEqual(read(os.path.join(self.conf, 'config.json')), '{"other": 1}')

    def test_nb1_a_foreign_cache_is_never_marked_or_overwritten(self):
        write(os.path.join(self.cache, 'forever.db'), 'not ours')
        write(os.path.join(self.cache, 'tips', 'item', 'foreign.json'), 'theirs')
        s, rc, fake = self.update()
        self.assertEqual(rc, 2, '\n'.join(self.lines))
        self.assertTrue(any('not this tool' in ln for ln in self.lines), self.lines)
        self.assertEqual(read(os.path.join(self.cache, 'forever.db')), 'not ours')
        self.assertFalse(os.path.exists(os.path.join(self.cache, paths.MARKER)))
        s2 = Store(cache=self.cache, http=net.Http(offline=False, opener=FakeNet(
            {'https://nether.wowhead.com/forever/tooltip/item/7': b'{"name": "x"}'}), sleep=lambda s: None))
        self.addCleanup(s2.close)
        self.assertEqual(s2.tooltip('item', 7), {'name': 'x'})  # answered, but nothing written there
        self.assertFalse(os.path.exists(os.path.join(self.cache, 'tips', 'item', '7.json')))
        rc, text = self.run_cli('setup', '--uninstall', '--purge')
        self.assertEqual(read(os.path.join(self.cache, 'tips', 'item', 'foreign.json')), 'theirs')

    def test_nb1_claim_is_the_one_gate(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, 'stamp.json'), '{}')
            with self.assertRaises(paths.NotOurs):
                paths.claim(d, paths.CACHE_NAMES)
            self.assertFalse(os.path.exists(os.path.join(d, paths.MARKER)))
            empty = os.path.join(d, 'new')
            paths.claim(empty, paths.CACHE_NAMES)
            self.assertTrue(paths.owns(empty))


# ---- NB2: no printed line names the home folder or the account folder -----------------------------------------


class NB2EveryCommandMasked(unittest.TestCase):
    HOME_NAME, ACCOUNT_NAME = 'homeofzorba', 'ZORBAACCOUNT'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fg-nb2-')
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, self.HOME_NAME)
        root = os.path.join(self.home, 'Games')
        os.makedirs(root)
        self.game = fixtures.fake_game(root)
        os.rename(os.path.join(self.game, SV.replace('SavedVariables', '')[:-1]),
                  os.path.join(self.game, 'WTF', 'Account', self.ACCOUNT_NAME))
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('FOREVER_', 'XDG_'))}
        self.env.update(HOME=self.home, FOREVER_OFFLINE='1')
        cache = paths.cache_dir(self.env, None, self.home)
        s = Store(cache=cache, game=self.game, http=net.Http(offline=False, opener=FakeNet(forever_routes()),
                                                             sleep=lambda s: None), out=lambda *_: None)
        s.update()
        s.close()

    def run_forever(self, *argv):
        r = subprocess.run([sys.executable, '-B', '-I', os.path.join(ROOT, 'forever')] + list(argv)
                           + ['--game', self.game], capture_output=True, text=True, env=self.env, cwd=self.tmp.name)
        return r.stdout + r.stderr

    def check(self, *argv):
        text = self.run_forever(*argv)
        for line in text.splitlines():
            if '/plugin marketplace add' in line:
                continue  # the one line the player pastes: the toolkit folder in full (not under this home)
            self.assertNotIn(self.HOME_NAME, line, (argv, line))
            self.assertNotIn(self.ACCOUNT_NAME, line, (argv, line))
        return text

    def test_nb2_every_command_of_the_skill_and_its_error_paths(self):
        for argv in (('me',), ('me', 'status'), ('me', 'gear'), ('me', 'stats'), ('me', 'skills'), ('me', 'recipes'),
                     ('me', 'trainer'), ('me', 'vendor'), ('me', 'rep'), ('me', 'quests'), ('me', 'quests', 'Mock Quest'),
                     ('me', 'bags'), ('me', 'missing'), ('me', 'missing', '--want', 'Mock Ring'), ('me', 'xp'),
                     ('me', 'talents'), ('me', 'json'), ('price', 'Mock Salt'), ('price', 'Nothing At All'),
                     ('item', 'Mock Silk Cap'), ('item', 'glimmer', '--list'), ('item', 'Nothing At All'),
                     ('quest', 'Mock Quest'), ('quest', 'Nothing At All'), ('where', 'Trainer Tom'),
                     ('where', 'Mockzone'), ('where', 'Nothing At All'), ('update', '--check'), ('version',),
                     ('setup', '--no-download'), ('setup', '--uninstall')):
            self.check(*argv)
        sv = os.path.join(self.game, 'WTF', 'Account', self.ACCOUNT_NAME, 'SavedVariables')
        write(os.path.join(sv, 'Auctionator.lua'), 'AUCTIONATOR_CONFIG = {\n["x"] = 1,\n}\n')
        self.assertIn('no price database', self.check('price', 'Mock Salt'))
        os.remove(os.path.join(sv, 'ForeverBridge.lua'))
        self.assertIn('No snapshot yet', self.check('me'))

    @unittest.skipUnless(os.name == 'posix', 'POSIX shell needed')
    def test_nb2_the_launcher_names_no_folder_when_the_toolkit_moved(self):
        conf = os.path.join(self.tmp.name, 'conf')
        os.makedirs(conf)
        gone = os.path.join(self.home, 'was-here')
        with open(os.path.join(conf, 'launcher.txt'), 'w') as fh:
            fh.write(sys.executable + '\n' + gone + '\n')
        r = subprocess.run([os.path.join(ROOT, 'plugin', 'bin', 'forever'), 'version'], capture_output=True, text=True,
                           env=dict(self.env, FOREVER_CONFIG_DIR=conf))
        self.assertEqual(r.returncode, 127)
        self.assertIn('has moved', r.stderr)
        self.assertNotIn(self.HOME_NAME, r.stdout + r.stderr)


# ---- NB4: every answer says where it came from, and Classic titles are labelled --------------------------------


class NB4Answers(Base):
    def setUp(self):
        super().setUp()
        self.update()

    def test_nb4_not_found_answers_carry_the_data_line(self):
        for argv in (('item', 'Nothing At All'), ('quest', 'Nothing At All'), ('where', 'Nothing At All')):
            rc, text = self.run_cli(*argv)
            self.assertEqual(rc, 1, text)
            self.assertIn('Data from ForeverDB.net', text, argv)

    def test_nb4_titles_from_the_classic_table_are_labelled_in_quest_lists(self):
        rc, text = self.run_cli('quest', 'quest')
        self.assertIn('990002 Old Classic Quest (Classic data)', text.splitlines()[0])

    def test_nb4_me_quests_carries_the_data_line(self):
        rc, text = self.run_cli('me', 'quests', 'Mock Prelude')
        self.assertIn('Data from ForeverDB.net', text)

    def test_nb4_every_answer_with_a_title_or_a_number(self):
        for argv in (('item', 'Mock Silk Cap'), ('item', 'glimmer', '--list'), ('item', 'Nothing At All'),
                     ('quest', 'Mock Quest'), ('quest', 'quest'), ('quest', 'Old Classic Quest'), ('quest', '990002'),
                     ('quest', 'Nothing At All'), ('where', 'Trainer Tom'), ('where', 'Mock Salt'),
                     ('where', 'Nothing At All'), ('me', 'quests', 'Old Classic Quest'), ('me', 'quests', '990005'),
                     ('me', 'xp'), ('price', 'Mock Salt')):
            rc, text = self.run_cli(*argv)
            self.assertTrue(any(ln.startswith(('from:', 'data:')) for ln in text.splitlines()), (argv, text))
            for line in text.splitlines():
                at = line.find('Old Classic Quest')
                if at >= 0:
                    self.assertIn('(Classic data)', line[at:], (argv, line))


# ---- NB5: a linked Interface or AddOns folder ------------------------------------------------------------------
@unittest.skipUnless(hasattr(os, 'symlink') and os.name == 'posix', 'symbolic links')
class NB5LinkedParents(Base):
    def test_nb5_addons_linked_to_a_checkout(self):
        checkout = os.path.join(self.t.root, 'checkout', 'addon')
        shutil.copytree(os.path.join(ROOT, 'addon'), checkout)
        shutil.rmtree(self.addons)
        os.symlink(checkout, self.addons)
        with mock.patch('sys.stdin') as stdin:
            stdin.isatty.return_value = False
            rc, text = self.run_cli('setup', '--uninstall')
        self.assertIn('--force', text)
        self.assertEqual(sorted(os.listdir(os.path.join(checkout, 'ForeverBridge'))),
                         ['ForeverBridge.lua', 'ForeverBridge.toc'])

    def test_nb5_interface_linked_out_of_the_game_folder(self):
        elsewhere = os.path.join(self.t.root, 'elsewhere')
        shutil.move(os.path.join(self.game, 'Interface'), elsewhere)
        os.symlink(elsewhere, os.path.join(self.game, 'Interface'))
        with mock.patch('sys.stdin') as stdin:
            stdin.isatty.return_value = False
            rc, text = self.run_cli('setup', '--no-download')
        self.assertEqual(rc, 2, text)
        self.assertIn('--force', text)
        self.assertFalse(os.path.exists(os.path.join(elsewhere, 'AddOns', 'ForeverBridge')))
        rc, text = self.run_cli('setup', '--no-download', '--force')
        self.assertEqual(rc, 0, text)
        self.assertTrue(os.path.exists(os.path.join(elsewhere, 'AddOns', 'ForeverBridge', 'ForeverBridge.lua')))

    def test_nb5_the_toolkits_own_add_on_folder_is_never_touched(self):
        kit = os.path.join(self.t.root, 'kit', 'addon')
        shutil.copytree(os.path.join(ROOT, 'addon'), kit)
        shutil.rmtree(self.addons)
        os.symlink(kit, self.addons)
        with mock.patch('forever.installer.addon_source', return_value=os.path.join(kit, 'ForeverBridge')):
            for argv in (('setup', '--no-download', '--force'), ('setup', '--uninstall', '--force')):
                rc, text = self.run_cli(*argv)
                self.assertIn("this toolkit's own add-on folder", text, argv)
        self.assertEqual(sorted(os.listdir(os.path.join(kit, 'ForeverBridge'))), ['ForeverBridge.lua', 'ForeverBridge.toc'])

    def test_nit6_a_link_that_islink_does_not_see(self):
        # a Windows junction looks like a plain folder to os.path.islink: the realpath check must catch it
        other = os.path.join(self.t.root, 'other')
        write(os.path.join(other, 'ForeverBridge.lua'), 'theirs')
        os.symlink(other, os.path.join(self.addons, 'ForeverBridge'))
        real_islink = os.path.islink
        with mock.patch('os.path.islink', side_effect=lambda p: False if p.endswith('ForeverBridge') else real_islink(p)):
            with self.assertRaises(installer.Refused):
                installer.addon_dest(self.game)
        self.assertEqual(read(os.path.join(other, 'ForeverBridge.lua')), 'theirs')


# ---- NS2, NS3, NS4, NS7 ----------------------------------------------------------------------------------------


class NSData(Base):
    def test_ns2_an_unread_source_kind_is_not_called_unknown(self):
        self.update()
        rc, text = self.run_cli('item', '900050')
        self.assertIn('source: ForeverDB lists a source of a kind this tool does not read yet', text)

    def test_ns3_the_published_size_is_a_digit_string_and_the_cap_has_a_ceiling(self):
        routes = forever_routes()
        man = json.loads(routes['https://foreverdb.net/downloads/addon-manifest.json'])
        for f in man['data']['files']:
            self.assertIsInstance(f['bytes'], int)  # the real manifest gives a number; a digit string is accepted too
            if f['path'].endswith('QuestForever.lua'):
                f['bytes'] = str(10 << 20)
            if f['path'].endswith('Loot.lua'):
                f['bytes'] = str(10 << 40)
        routes['https://foreverdb.net/downloads/addon-manifest.json'] = json.dumps(man).encode()
        caps = {}
        real = net.Http.download

        def spy(self_, url, dest, **kw):
            caps[os.path.basename(dest)] = kw.get('max_bytes')
            return real(self_, url, dest, **kw)
        with mock.patch.object(net.Http, 'download', spy):
            self.update(routes)
        self.assertIn('QuestForever.lua (10240 KB)', '\n'.join(self.lines))
        self.assertEqual(caps['QuestForever.lua'], max(net.MAX_DOWNLOAD, (10 << 20) + (1 << 20)))
        self.assertEqual(caps['Loot.lua'], 256 << 20)

    def test_ns4_a_manifest_url_with_a_space_or_a_line_break(self):
        with mock.patch('socket.create_connection', side_effect=no_network):
            for url in ('https://foreverdb.net/downloads/addon data/x.lua', 'https://foreverdb.net/a\nb.lua'):
                with tempfile.TemporaryDirectory() as d:
                    with self.assertRaises(ValueError):
                        net.Http(offline=False).download(url, os.path.join(d, 'x.lua'))
                with self.assertRaises(ValueError):
                    net.Http(offline=False).get(url)

        class Strict(FakeNet):
            def __call__(self, req, timeout=None):
                if any(c in req.full_url for c in ' \n\t'):
                    raise http.client.InvalidURL('URL can\'t contain control characters')
                return super().__call__(req, timeout)
        routes = forever_routes()
        man = json.loads(routes['https://foreverdb.net/downloads/addon-manifest.json'])
        for f in man['data']['files']:
            if f['path'].endswith('NPCs.lua'):
                f['url'] = 'downloads/addon data/NPCs.lua'
            if f['path'].endswith('Loot.lua'):
                f['url'] = 'downloads/addon\ndata/Loot.lua'
        routes['https://foreverdb.net/downloads/addon-manifest.json'] = json.dumps(man).encode()
        s = Store(cache=self.cache, game=self.game, http=net.Http(offline=False, opener=Strict(routes),
                                                                  sleep=lambda s: None), out=self.lines.append)
        self.addCleanup(s.close)
        rc = s.update()
        text = '\n'.join(self.lines)
        self.assertEqual(rc, 1, text)
        self.assertIn('note: ForeverDB NPCs.lua (', text)
        self.assertIn('note: ForeverDB Loot.lua (', text)

    def test_ns7_only_forever_bridge_lua_is_read(self):
        sv = os.path.join(self.game, SV)
        os.remove(os.path.join(sv, 'ForeverBridge.lua'))
        write(os.path.join(sv, 'OldBridge.lua'), fixtures.saved_variables('OldBridgeDB', fixtures.snapshot()))
        with mock.patch('forever.snapshot.read_db', wraps=__import__('forever.snapshot').snapshot.read_db) as reader:
            rc, text = self.run_cli('me')
        self.assertEqual(rc, 2, text)
        self.assertIn('No snapshot yet', text)
        self.assertFalse(any('OldBridge' in str(c) for c in reader.call_args_list))


# ---- nits -------------------------------------------------------------------------------------------------------


class NitsRound3(Base):
    def test_nit1_only_ascii_digits_make_a_build_number(self):
        self.assertFalse(data.valid_build('１.２.３'))
        self.assertTrue(data.valid_build('1.60.1.71139'))

    def test_nit6_a_build_number_must_match_whole(self):
        self.assertFalse(data.valid_build('1.60.1.71139/../x'))  # passes re.match, fails re.fullmatch

    def test_nit2_the_host_part_is_read_one_way_only(self):
        hosts, schemes = net.ALLOWED_HOSTS, {'https'}
        at = '@'  # put together here, so that the tree's own scan does not read these as e-mail addresses
        for url in ('https://evil.example\\' + at + 'foreverdb.net/', 'https://x' + at + 'foreverdb.net/',
                    'https://foreverdb.net :443/',
                    'https://foreverdb.net:8443/x', 'https://fore verdb.net/'):
            self.assertFalse(net.allowed(url, hosts, schemes), url)
        for url in ('https://foreverdb.net/x', 'https://foreverdb.net:443/x', 'https://WAGO.tools/db2'):
            self.assertTrue(net.allowed(url, hosts, schemes), url)

    def test_nit3_the_flavour_name_is_compared_without_case(self):
        upper = os.path.join(os.path.dirname(self.game), '_FOREVER_')
        os.rename(self.game, upper)
        with mock.patch('sys.stdin') as stdin:
            stdin.isatty.return_value = False
            rc, text = self.run_cli('setup', '--no-download', '--game', upper, game=False)
        self.assertEqual(rc, 0, text)

    def test_nit6_older_tables_are_found_in_a_folder_with_glob_characters(self):
        odd = os.path.join(self.t.root, 'cache [1]')
        s, rc, fake = self.update(cache=odd)
        self.assertEqual(rc, 0)
        with open(os.path.join(os.path.dirname(self.game), '.build.info'), 'w') as fh:
            fh.write('Branch!STRING:0|Active!DEC:1|Version!STRING:0|Product!STRING:0\neu|1|9.9.10.10001|wowf\n')
        self.lines = []
        s, rc, fake = self.update(cache=odd)  # the new build's tables are not served: the older ones are used
        self.assertIn('using the game tables of 9.9.9.12345', '\n'.join(self.lines))

    def test_nit7_leftover_temporary_files_and_journals(self):
        dest = os.path.join(self.addons, 'ForeverBridge')
        write(os.path.join(dest, '.ForeverBridge.lua.abc123.tmp'), 'left by a killed setup')
        rc, text = self.run_cli('setup', '--no-download')
        self.assertEqual(rc, 0, text)
        self.assertFalse(os.path.exists(os.path.join(dest, '.ForeverBridge.lua.abc123.tmp')))
        write(os.path.join(dest, '.ForeverBridge.toc.def456.tmp'), 'again')
        rc, text = self.run_cli('setup', '--uninstall')
        self.assertFalse(os.path.exists(dest))
        self.assertIn('forever.db.tmp-journal', installer.CACHE_FILES)

    def test_nit9_a_parse_error_does_not_echo_the_file(self):
        with self.assertRaises(lt.LuaError) as e:
            lt.parse('A = { @secret text here }')
        self.assertNotIn('secret', str(e.exception))
        self.assertIn('at character', str(e.exception))

    def test_nit10_an_upper_case_checksum_is_accepted(self):
        routes = forever_routes()
        man = json.loads(routes['https://foreverdb.net/downloads/addon-manifest.json'])
        for f in man['data']['files']:
            f['sha256'] = f['sha256'].upper()
        routes['https://foreverdb.net/downloads/addon-manifest.json'] = json.dumps(man).encode()
        s, rc, fake = self.update(routes)
        self.assertEqual(rc, 0, '\n'.join(self.lines))

    def test_nit11_a_game_table_is_never_glued_onto_an_old_part(self):
        self.update()
        folder = os.path.join(self.cache, 'raw', 'wago', '9.9.9.12345')
        os.remove(os.path.join(folder, 'ItemSparse.csv'))
        write(os.path.join(folder, 'ItemSparse.csv.part'), 'JUNK FROM ANOTHER VERSION OF THE FILE')
        s, rc, fake = self.update()
        self.assertEqual(read(os.path.join(folder, 'ItemSparse.csv')), fixtures.WAGO['ItemSparse'])


class NitScanWords(unittest.TestCase):
    def run_scan(self, root, words):
        r = subprocess.run([sys.executable, '-B', '-I', os.path.join(ROOT, 'scripts', 'scan_private.py'), root,
                            '--words', words], capture_output=True, text=True, env=dict(os.environ, FOREVER_PRIVATE_WORDS=''))
        return r.returncode, r.stdout

    def test_nit4_a_words_file_with_a_byte_order_mark_and_an_empty_one(self):
        with tempfile.TemporaryDirectory() as d:
            tree = os.path.join(d, 'tree')
            write(os.path.join(tree, 'a.txt'), 'a quokkaland day\n')
            words = os.path.join(d, 'words.txt')
            with open(words, 'w', encoding='utf-8-sig') as fh:  # Notepad saves it like this
                fh.write('quokkaland\nanother\n')
            rc, out = self.run_scan(tree, words)
            self.assertIn('a.txt:1: private word #1', out)
            self.assertIn('private words: 2 checked', out)
            open(words, 'w').close()
            rc, out = self.run_scan(tree, words)
            self.assertIn('private words: NOT CHECKED (the words file holds no words)', out)
            self.assertNotIn('clean', out)


class NitsFiles(unittest.TestCase):
    def test_nit12_unittest_main_comes_last_in_every_test_file(self):
        for path in glob.glob(os.path.join(ROOT, 'tests', 'test_*.py')):
            with open(path, encoding='utf-8') as fh:
                tree = ast.parse(fh.read())
            body = tree.body
            mains = [n for n, node in enumerate(body) if isinstance(node, ast.If)
                     and "attr='main'" in ast.dump(node) and "id='unittest'" in ast.dump(node)]
            self.assertTrue(mains, path)
            for n in mains:
                self.assertEqual(n, len(body) - 1, path)

    def test_nit13_nit14_ns6_nb2_nb5_ns7_the_texts_say_what_the_code_does(self):
        def text(rel):
            with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
                return ' '.join(fh.read().split())
        plugin, readme, notice, security = (text('plugin/README.md'), text('README.md'), text('NOTICE.md'),
                                            text('SECURITY.md'))
        self.assertIn('Git Bash', plugin)
        for t in (readme, notice):
            self.assertIn('the five-step rule for quests below your level', t)
            self.assertIn("the client's slot, quality and standing lists", t)
        self.assertNotIn('wishlist.txt, all read-only', security)
        self.assertIn('registry', security)
        self.assertIn('folder search', security)
        self.assertIn('NPC tooltips', notice)
        self.assertIn('only `forever setup` and `forever update` download the data', notice)
        self.assertIn('except the one line of setup that you paste into Claude Code', security)
        for t in (readme, security):
            self.assertIn('never through a linked ForeverBridge folder or file', t)
            self.assertIn('a linked Interface or AddOns folder that leaves the game folder needs --force', t)
            self.assertNotIn('*Bridge.lua', t)
            self.assertNotIn('older bridge', t.lower())


if __name__ == '__main__':
    unittest.main()
