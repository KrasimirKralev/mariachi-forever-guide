"""Regression tests for the findings of the first independent audit (B = blocker, S = should fix, N = nit).
Each test failed on the code the audit read and passes after its fix. Offline, temp folders only."""
import http.server
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
from unittest import mock

from forever import cli, net, paths
from forever.data import Store
from tests import fixtures
from tests.fakenet import FakeNet, forever_routes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Base(unittest.TestCase):
    def setUp(self):
        self.t = fixtures.TempEnv().__enter__()
        self.addCleanup(self.t.__exit__)
        self.game = fixtures.fake_game(self.t.root)
        self.cache = self.t.env['FOREVER_CACHE_DIR']
        self.conf = self.t.env['FOREVER_CONFIG_DIR']
        self.addons = os.path.join(self.game, 'Interface', 'AddOns')
        self.lines = []

    def run_cli(self, *argv, game=True, env=None):
        lines = []
        args = list(argv) + (['--game', self.game] if game else [])
        rc = cli.main(args, env=dict(os.environ, **(env or {})), out=lines.append)
        return rc, '\n'.join(str(x) for x in lines)

    def update(self, routes=None, game='default', cache=None):
        fake = FakeNet(routes or forever_routes())
        s = Store(cache=cache or self.cache, game=self.game if game == 'default' else game,
                  http=net.Http(offline=False, opener=fake, sleep=lambda s: None), out=self.lines.append)
        self.addCleanup(s.close)
        return s, s.update(), fake


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)


def read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


# ---- B2: links out of the add-on folder ----------------------------------------------------------------------
@unittest.skipUnless(hasattr(os, 'symlink') and os.name == 'posix', 'symbolic links')
class B2Links(Base):
    def test_b2a_a_planted_tmp_link_is_never_written_through(self):
        victim = os.path.join(self.t.root, 'victim.txt')
        write(victim, 'precious')
        dest = os.path.join(self.addons, 'ForeverBridge')
        os.makedirs(dest)
        for name in ('ForeverBridge.lua.tmp', 'ForeverBridge.toc.tmp'):
            os.symlink(victim, os.path.join(dest, name))
        rc, text = self.run_cli('setup', '--no-download')
        self.assertEqual(rc, 0, text)
        self.assertEqual(read(victim), 'precious')
        for name in ('ForeverBridge.lua', 'ForeverBridge.toc'):
            self.assertFalse(os.path.islink(os.path.join(dest, name)))
        self.assertIn('ForeverBridgeDB', read(os.path.join(dest, 'ForeverBridge.toc')))

    def test_b2b_the_add_on_folder_is_a_link_to_another_folder(self):
        other = os.path.join(self.t.root, 'elsewhere')
        write(os.path.join(other, 'ForeverBridge.lua'), 'not yours')
        write(os.path.join(other, 'ForeverBridge.toc'), 'not yours either')
        os.symlink(other, os.path.join(self.addons, 'ForeverBridge'))
        rc, text = self.run_cli('setup', '--no-download')
        self.assertEqual(rc, 2, text)
        self.assertIn('is a link', text)
        self.assertEqual(read(os.path.join(other, 'ForeverBridge.lua')), 'not yours')
        rc, text = self.run_cli('setup', '--uninstall')
        self.assertIn('is a link', text)
        self.assertEqual(sorted(os.listdir(other)), ['ForeverBridge.lua', 'ForeverBridge.toc'])

    def test_b2c_a_contributor_link_to_the_checkout_survives_uninstall(self):
        checkout = os.path.join(self.t.root, 'checkout', 'addon', 'ForeverBridge')
        shutil.copytree(os.path.join(ROOT, 'addon', 'ForeverBridge'), checkout)
        os.symlink(checkout, os.path.join(self.addons, 'ForeverBridge'))
        rc, text = self.run_cli('setup', '--uninstall')
        self.assertIn('is a link', text)
        self.assertEqual(sorted(os.listdir(checkout)), ['ForeverBridge.lua', 'ForeverBridge.toc'])


# ---- B3: shared cache and config folders -----------------------------------------------------------------------
class B3SharedFolders(Base):
    def test_b3_purge_leaves_a_shared_cache_alone(self):
        shared = os.path.join(self.t.root, 'photos')
        write(os.path.join(shared, 'raw', 'IMG_0001.raw'), 'a photo')
        write(os.path.join(shared, 'tips', 'notes.txt'), 'my notes')
        self.update(cache=shared)  # the tool has been used there: its own files sit next to the photos
        self.assertTrue(os.path.exists(os.path.join(shared, 'forever.db')))
        rc, text = self.run_cli('setup', '--uninstall', '--purge', '--cache', shared)
        self.assertEqual(rc, 0, text)
        self.assertEqual(read(os.path.join(shared, 'raw', 'IMG_0001.raw')), 'a photo')
        self.assertEqual(read(os.path.join(shared, 'tips', 'notes.txt')), 'my notes')
        for gone in ('forever.db', 'stamp.json', os.path.join('raw', 'wago'), os.path.join('raw', 'foreverdb'),
                     paths.MARKER):
            self.assertFalse(os.path.exists(os.path.join(shared, gone)), gone)

    def test_b3_a_folder_the_tool_never_used_is_not_purged(self):
        shared = os.path.join(self.t.root, 'photos')
        write(os.path.join(shared, 'raw', 'wago', 'mine.txt'), 'mine')
        write(os.path.join(shared, 'stamp.json'), '{"mine": true}')
        rc, text = self.run_cli('setup', '--uninstall', '--purge', '--cache', shared)
        self.assertEqual(rc, 0, text)
        self.assertEqual(read(os.path.join(shared, 'raw', 'wago', 'mine.txt')), 'mine')
        self.assertEqual(read(os.path.join(shared, 'stamp.json')), '{"mine": true}')
        self.assertIn('not this tool', text)

    def test_b3_a_foreign_config_json_is_never_overwritten_or_removed(self):
        write(os.path.join(self.conf, 'config.json'), '{"project": 1}')
        rc, text = self.run_cli('setup', '--no-download')
        self.assertEqual(rc, 2, text)
        self.assertIn('config.json', text)
        self.assertEqual(read(os.path.join(self.conf, 'config.json')), '{"project": 1}')
        rc, text = self.run_cli('setup', '--uninstall')
        self.assertEqual(read(os.path.join(self.conf, 'config.json')), '{"project": 1}')

    def test_b3_its_own_config_folder_is_cleaned(self):
        rc, text = self.run_cli('setup', '--no-download')
        self.assertEqual(rc, 0, text)
        self.assertTrue(os.path.exists(os.path.join(self.conf, paths.MARKER)))
        rc, text = self.run_cli('setup', '--uninstall')
        self.assertFalse(os.path.exists(self.conf) and os.listdir(self.conf))


# ---- B4, S2, S3: what the network says is checked before it is used --------------------------------------------
class B4S2S3Network(Base):
    def files_outside_the_cache(self):
        out = []
        for d, _, files in os.walk(self.t.root):
            for f in files:
                p = os.path.join(d, f)
                if f.endswith('.csv') and not os.path.abspath(p).startswith(os.path.abspath(self.cache) + os.sep):
                    out.append(p)
        return out

    def test_b4_a_hostile_build_number_from_the_network(self):
        evil = '../../../../escaped'
        routes = forever_routes()
        routes['https://wago.tools/api/builds'] = json.dumps({'wowf': [{'version': evil}]}).encode()
        for t in ('ItemSparse', 'SpellName', 'SpellItemEnchantment', 'UiMap', 'UiMapAssignment', 'TaxiNodes'):
            routes['https://wago.tools/db2/%s/csv?build=%s' % (t, evil)] = b'ID,x\n1,2\n'
        s, rc, fake = self.update(routes, game=None)
        self.assertEqual(rc, 2, '\n'.join(self.lines))
        self.assertTrue(any('cannot tell which game build' in ln.lower() for ln in self.lines), self.lines)
        self.assertEqual(self.files_outside_the_cache(), [])

    def test_b4_a_hostile_build_number_in_the_build_file(self):
        with open(os.path.join(os.path.dirname(self.game), '.build.info'), 'w') as fh:
            fh.write('Branch!STRING:0|Active!DEC:1|Version!STRING:0|Product!STRING:0\neu|1|../../../../escaped|wowf\n')
        s, rc, fake = self.update()
        self.assertEqual(self.files_outside_the_cache(), [])
        self.assertIn('https://wago.tools/api/builds', [u for u, _ in fake.requests])  # asked the network instead
        self.assertEqual(s.stamp()['build'], '9.9.9.12345')

    def manifest(self, routes, change):
        man = json.loads(routes['https://foreverdb.net/downloads/addon-manifest.json'])
        change(man)
        routes['https://foreverdb.net/downloads/addon-manifest.json'] = json.dumps(man).encode()
        return routes

    def test_s2_a_file_without_a_checksum_is_not_kept(self):
        def drop(man):
            for f in man['data']['files']:
                if f['path'].endswith('NPCs.lua'):
                    del f['sha256']
                if f['path'].endswith('Loot.lua'):
                    f['sha256'] = 'not-a-checksum'
        s, rc, fake = self.update(self.manifest(forever_routes(), drop))
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(os.path.join(self.cache, 'raw', 'foreverdb', 'NPCs.lua')))
        self.assertFalse(os.path.exists(os.path.join(self.cache, 'raw', 'foreverdb', 'Loot.lua')))
        text = '\n'.join(self.lines)
        self.assertIn('NPCs.lua (no valid checksum', text)
        self.assertIn('Loot.lua (no valid checksum', text)
        self.assertFalse(any('NPCs.lua' in u for u, _ in fake.requests))

    def test_s3_an_odd_manifest_keeps_the_copy_in_the_cache(self):
        s, rc, fake = self.update()
        self.assertEqual(rc, 0)
        for change in (lambda m: m['data'].__setitem__('files', ['QuestForever.lua']),
                       lambda m: m['data']['files'][0].pop('path'),
                       lambda m: m['data']['files'][1].pop('url'),
                       lambda m: m.__setitem__('data', [])):
            self.lines = []
            s, rc, fake = self.update(self.manifest(forever_routes(), change))
            text = '\n'.join(self.lines)
            self.assertNotIn('something went wrong', text)
            self.assertIn(rc, (0, 1), text)
            self.assertTrue(os.path.exists(os.path.join(self.cache, 'forever.db')))

    def test_s3_a_build_list_without_a_version(self):
        routes = forever_routes()
        routes['https://wago.tools/api/builds'] = json.dumps({'wowf': [{}]}).encode()
        s, rc, fake = self.update(routes, game=None)
        self.assertEqual(rc, 2)
        self.assertTrue(any('cannot tell which game build' in ln.lower() for ln in self.lines), self.lines)


# ---- S1: one opener that stays on the tool's own sites, and size caps ------------------------------------------
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == '/elsewhere':
            self.send_response(302)
            self.send_header('Location', 'http://localhost:%d/x' % self.server.server_port)
            self.end_headers()
        elif self.path == '/big':
            body = b'x' * (9 << 20)
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == '/chunked-big':
            self.send_response(200)
            self.end_headers()
            for _ in range(70):
                self.wfile.write(b'y' * (1 << 20))
        else:
            self.send_response(200)
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'ok')


class QuietServer(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        pass  # the client hanging up on an oversized answer is the point of the test


class S1Opener(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = QuietServer(('127.0.0.1', 0), Handler)
        cls.port = cls.server.server_port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def http(self):
        return net.Http(offline=False, hosts={'127.0.0.1'}, schemes={'http'}, sleep=lambda s: None)

    def url(self, path):
        return 'http://127.0.0.1:%d%s' % (self.port, path)

    def test_s1_the_loopback_server_answers(self):
        self.assertEqual(self.http().get(self.url('/ok')), b'ok')

    def test_s1_a_redirect_to_another_host_is_refused(self):
        with self.assertRaises(net.Refused) as e:
            self.http().get(self.url('/elsewhere'))
        self.assertIn('localhost', str(e.exception))

    def test_s1_a_redirect_to_plain_http_is_refused(self):
        handler = net.Redirects({'wago.tools'}, {'https'})
        req = urllib.request.Request('https://wago.tools/db2/x')
        with self.assertRaises(net.Refused):
            handler.redirect_request(req, io.BytesIO(), 302, 'Found', {}, 'http://wago.tools/db2/x')
        with self.assertRaises(net.Refused):
            handler.redirect_request(req, io.BytesIO(), 302, 'Found', {}, 'https://cdn.example.com/x')
        self.assertIsNotNone(handler.redirect_request(req, io.BytesIO(), 302, 'Found', {}, 'https://wago.tools/y'))

    def test_s1_the_default_opener_only_knows_the_tools_sites(self):
        h = net.Http(offline=False)
        with self.assertRaises(net.Refused):
            h.get('https://example.com/')  # refused before any connection is made
        with self.assertRaises(net.Refused):
            h.get('http://wago.tools/api/builds')
        self.assertEqual(net.ALLOWED_HOSTS & {'foreverdb.net', 'wago.tools', 'nether.wowhead.com'},
                         {'foreverdb.net', 'wago.tools', 'nether.wowhead.com'})

    def test_s1_an_oversized_answer_stops(self):
        with self.assertRaises(net.TooBig):
            self.http().get(self.url('/big'))  # 9 MB, the cap is 8 MB
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, 'f.csv')
            with self.assertRaises(net.TooBig):
                self.http().download(self.url('/chunked-big'), dest)  # 70 MB with no length, the cap is 64 MB
            self.assertFalse(os.path.exists(dest))
            self.assertFalse(os.path.exists(dest + '.part'))


# ---- S4, S5, S11, B5, B6, S6, N5, N6, N7 ------------------------------------------------------------------------
class S4Brackets(Base):
    def setUp(self):
        self.t = fixtures.TempEnv().__enter__()
        self.addCleanup(self.t.__exit__)
        self.game = fixtures.fake_game(os.path.join(self.t.root, 'brackets [SSD] *?'))
        self.cache = self.t.env['FOREVER_CACHE_DIR']
        self.lines = []

    def test_s4_a_folder_with_glob_characters(self):
        s, rc, fake = self.update()
        self.assertEqual(s.stamp()['counts'].get('quests from your game cache'), 2)
        rc, text = self.run_cli('me')
        self.assertEqual(rc, 0, text)
        self.assertIn('Testa-Mockrealm', text)
        rc, text = self.run_cli('price', 'Mock Salt')
        self.assertIn('53c', text)


class S5S11Setup(Base):
    def test_s5_uninstall_finishes_when_the_game_folder_is_gone(self):
        self.update()
        rc, text = self.run_cli('setup', '--no-download')
        self.assertEqual(rc, 0, text)
        shutil.rmtree(os.path.dirname(self.game))
        rc, text = self.run_cli('setup', '--uninstall', '--purge')
        self.assertEqual(rc, 0, text)
        self.assertFalse(os.path.exists(os.path.join(self.conf, 'config.json')))
        self.assertFalse(os.path.exists(os.path.join(self.conf, 'launcher.txt')))
        self.assertFalse(os.path.exists(os.path.join(self.cache, 'forever.db')))

    def test_s11_another_game_flavour_needs_force(self):
        retail = os.path.join(os.path.dirname(self.game), '_retail_')
        os.makedirs(os.path.join(retail, 'WTF'))
        with mock.patch('sys.stdin') as stdin:
            stdin.isatty.return_value = False
            rc, text = self.run_cli('setup', '--no-download', '--game', retail, game=False)
        self.assertEqual(rc, 2, text)
        self.assertIn('_retail_', text)
        self.assertIn('--force', text)
        self.assertFalse(os.path.exists(os.path.join(retail, 'Interface', 'AddOns', 'ForeverBridge')))
        rc, text = self.run_cli('setup', '--no-download', '--force', '--game', retail, game=False)
        self.assertEqual(rc, 0, text)
        self.assertTrue(os.path.exists(os.path.join(retail, 'Interface', 'AddOns', 'ForeverBridge', 'ForeverBridge.lua')))

    def test_s11_an_interactive_player_is_asked(self):
        retail = os.path.join(os.path.dirname(self.game), '_retail_')
        os.makedirs(os.path.join(retail, 'WTF'))
        with mock.patch('sys.stdin') as stdin, mock.patch('builtins.input', return_value='n'):
            stdin.isatty.return_value = True
            rc, text = self.run_cli('setup', '--no-download', '--game', retail, game=False)
        self.assertEqual(rc, 2, text)
        self.assertFalse(os.path.exists(os.path.join(retail, 'Interface', 'AddOns', 'ForeverBridge')))


class Output(Base):
    def setUp(self):
        super().setUp()
        self.update()

    def test_b5_every_number_from_the_classic_table_is_labelled(self):
        rc, text = self.run_cli('me', 'xp')
        for line in text.splitlines():
            if line.startswith(('Room before', '  that ')):  # both add up the Classic bars of 23 to 29
                self.assertIn('Classic data', line, line)
        # 300 XP short of 23: handing everything in crosses into a level whose bar is Classic's
        snap = fixtures.snapshot()
        snap['chars']['Testa-Mockrealm']['xp'] = 27000
        sv = os.path.join(self.game, 'WTF', 'Account', 'TESTACCOUNT', 'SavedVariables', 'ForeverBridge.lua')
        write(sv, fixtures.saved_variables('ForeverBridgeDB', snap))
        rc, text = self.run_cli('me', 'xp')
        hand_in = [ln for ln in text.splitlines() if ln.startswith('  handing in')]
        self.assertTrue(hand_in and 'level 23' in hand_in[0] and 'Classic data' in hand_in[0], text)
        # once the game has shown every level, nothing is Classic any more
        with open(os.path.join(self.conf, 'levels.json'), 'w') as fh:
            json.dump({str(n): 30000 + n for n in range(20, 31)}, fh)
        open(os.path.join(self.conf, paths.MARKER), 'w').close()
        rc, text = self.run_cli('me', 'xp')
        self.assertNotIn('Classic data', text)

    def test_b6a_item_list_says_where_it_came_from(self):
        rc, text = self.run_cli('item', 'glimmer', '--list')
        self.assertIn('Data from ForeverDB.net', text)

    def test_b6a_me_json_carries_its_source(self):
        rc, text = self.run_cli('me', 'json')
        obj = json.loads(text)
        self.assertIn('from: your snapshot ForeverBridge.lua', obj['_from'])
        sv = os.path.join(self.game, 'WTF', 'Account', 'TESTACCOUNT', 'SavedVariables', 'ForeverBridge.lua')
        self.assertNotIn('_from', read(sv))

    def test_b6b_classic_only_titles_are_labelled_in_me_quests(self):
        rc, text = self.run_cli('me', 'quests', 'Old Classic Quest')
        self.assertIn('Old Classic Quest (Classic data)', text)
        rc, text = self.run_cli('me', 'quests', '990002')
        self.assertIn('990002 Old Classic Quest: in your quest log', text)  # the log's own title: the game's
        snap = fixtures.snapshot()
        q = snap['chars']['Testa-Mockrealm']['quests']
        q['active'] = [a for a in q['active'] if a['id'] != 990002]
        sv = os.path.join(self.game, 'WTF', 'Account', 'TESTACCOUNT', 'SavedVariables', 'ForeverBridge.lua')
        write(sv, fixtures.saved_variables('ForeverBridgeDB', snap))
        rc, text = self.run_cli('me', 'quests', '990002')
        self.assertIn('990002 Old Classic Quest (Classic data): not done', text)
        rc, text = self.run_cli('me', 'quests', 'Mock Prelude')
        self.assertNotIn('Classic data', text.split('from:')[0])

    def test_b6b_a_vendor_place_from_classic_data_is_labelled(self):
        rc, text = self.run_cli('item', 'Mock Salt', '--side', 'alliance')
        line = next(ln for ln in text.splitlines() if 'sold by' in ln)
        self.assertIn('Alice Ally (Trade Supplies), Testvale (10.0, 10.0) (Classic data)', line)
        rc, text = self.run_cli('where', 'Mock Salt')
        self.assertIn('Alice Ally (Trade Supplies), Testvale (10.0, 10.0) (Classic data): 45c', text)
        self.assertIn('Vera Vendor (Trade Supplies), Testvale (40.0, 60.0): 50c', text)

    def test_s6_printed_paths_hide_the_home_and_the_account(self):
        home = self.t.env['HOME']
        game = os.path.join(home, 'Games', 'World of Warcraft', '_forever_')
        shutil.copytree(self.game, game)
        shutil.copy(os.path.join(os.path.dirname(self.game), '.build.info'), os.path.dirname(game))
        for argv in (('me', 'status'), ('version',), ('setup', '--no-download')):
            rc, text = self.run_cli(*argv, '--game', game, game=False)
            self.assertNotIn(home, text, argv)
            self.assertNotIn('TESTACCOUNT', text, argv)
        rc, text = self.run_cli('me', 'status', '--game', game, game=False)
        self.assertIn(os.path.join('~', 'Games'), text)
        self.assertIn(os.path.join('WTF', 'Account', '<account>', 'SavedVariables'), text)
        with mock.patch.dict(os.environ, {'FOREVER_DEBUG': '1'}):
            rc, text = self.run_cli('me', 'status', '--game', game, game=False)
        self.assertIn('TESTACCOUNT', text)

    def test_n7_piped_output_is_utf8(self):
        raw = io.BytesIO()
        fake = io.TextIOWrapper(raw, encoding='cp1252', errors='strict')
        with mock.patch.object(sys, 'stdout', fake):
            rc = cli.main(['me', '--game', self.game], env=dict(os.environ))
            sys.stdout.flush()
        self.assertEqual(rc, 0)
        self.assertIn('·'.encode('utf-8'), raw.getvalue())


class Nits(unittest.TestCase):
    def test_n5_a_tooltip_is_tried_once(self):
        calls, sleeps = [], []

        def dead(req, timeout=None):
            calls.append(req.full_url)
            raise urllib.error.URLError('down')
        with tempfile.TemporaryDirectory() as d:
            s = Store(cache=d, http=net.Http(offline=False, opener=dead, sleep=sleeps.append))
            self.assertIsNone(s.tooltip('item', 1))
        self.assertEqual(len(calls), 1)
        self.assertEqual([x for x in sleeps if x >= 1], [])

    def test_n6_the_progress_line_ends(self):
        class Tty(io.StringIO):
            def isatty(self):
                return True
        out = Tty()
        show = net.progress_printer('table', out)
        show(50, 100)
        show(100, 100)
        self.assertTrue(out.getvalue().endswith('\n'))

    def test_n6_http_errors_are_closed(self):
        body = io.BytesIO(b'')
        err = urllib.error.HTTPError('https://wago.tools/x', 404, 'Not Found', {}, body)

        def opener(req, timeout=None):
            raise err
        with self.assertRaises(urllib.error.HTTPError):
            net.Http(offline=False, opener=opener).get('https://wago.tools/x')
        self.assertTrue(body.closed)


# ---- the second review: R2, R4, R5 ----------------------------------------------------------------------------
def dead(req, timeout=None):
    raise urllib.error.URLError('[Errno 111] Connection refused')


class R2LinkedParents(Base):
    @unittest.skipUnless(hasattr(os, 'symlink') and os.name == 'posix', 'symbolic links')
    def test_r2_purge_never_follows_a_linked_raw_or_tips_folder(self):
        self.update()
        other = os.path.join(self.t.root, 'other')
        write(os.path.join(other, 'wago', 'keep.txt'), 'not the tool\'s')
        write(os.path.join(other, 'item', 'keep.txt'), 'not the tool\'s either')
        for name in ('raw', 'tips'):
            shutil.rmtree(os.path.join(self.cache, name), ignore_errors=True)
            os.symlink(other, os.path.join(self.cache, name))
        rc, text = self.run_cli('setup', '--uninstall', '--purge')
        self.assertEqual(rc, 0, text)
        self.assertEqual(read(os.path.join(other, 'wago', 'keep.txt')), "not the tool's")
        self.assertEqual(read(os.path.join(other, 'item', 'keep.txt')), "not the tool's either")
        self.assertIn('is a link', text)


class R4DeadNetwork(Base):
    def store(self, opener):
        s = Store(cache=self.cache, game=self.game, http=net.Http(offline=False, opener=opener, sleep=lambda s: None),
                  out=self.lines.append)
        self.addCleanup(s.close)
        return s

    def test_r4_update_with_a_game_build_and_nothing_cached(self):
        rc = self.store(dead).update()
        text = '\n'.join(self.lines)
        self.assertEqual(rc, 2, text)
        self.assertIn('game tables not downloaded:', text)
        self.assertIn('No data could be downloaded. Check the connection and run  forever update  again '
                      '(what was already downloaded is kept).', text)

    def test_r4_update_without_a_game_build(self):
        s = Store(cache=self.cache, game=None, http=net.Http(offline=False, opener=dead, sleep=lambda s: None),
                  out=self.lines.append)
        self.addCleanup(s.close)
        self.assertEqual(s.update(), 2)
        self.assertTrue(any('cannot tell which game build' in ln.lower() for ln in self.lines), self.lines)

    def test_r4_second_run_after_a_partial_success(self):
        routes = forever_routes()
        missing = [u for u in routes if '/db2/TaxiNodes/' in u][0]
        del routes[missing]  # the first run gets every file but one
        self.assertEqual(self.store(FakeNet(routes)).update(), 1)
        self.lines = []
        rc = self.store(dead).update()  # then the network dies: the cached data must carry on
        text = '\n'.join(self.lines)
        self.assertIn(rc, (0, 1), text)
        self.assertIn('game tables not downloaded:', text)
        self.assertIn('ForeverDB not refreshed', text)
        self.assertTrue(os.path.exists(os.path.join(self.cache, 'forever.db')))

    def test_r4_setup_with_a_dead_network_still_prints_the_next_steps(self):
        os.environ.pop('FOREVER_OFFLINE')  # really try the (dead) network
        with mock.patch('forever.net.urllib.request.build_opener') as build, mock.patch('forever.net.time.sleep'):
            build.return_value.open = dead
            rc, text = self.run_cli('setup')
        self.assertEqual(rc, 2, text)
        self.assertIn('data: not downloaded yet, run  python forever update  when you are online', text)
        self.assertIn('Next:', text)
        self.assertIn('/fbridge save', text)

    def test_r4_lookups_stay_quiet_offline(self):
        self.update()
        os.environ.pop('FOREVER_OFFLINE')  # really try the (dead) network
        with mock.patch('forever.net.urllib.request.build_opener') as build, mock.patch('forever.net.time.sleep'):
            build.return_value.open = dead
            rc, text = self.run_cli('item', 'Mock Wand')
        self.assertEqual(rc, 0, text)
        self.assertIn('(no tooltip yet: the tooltip service did not answer)', text)
        self.assertNotIn('something went wrong', text)


class R4NoWaitAfterTheLastTry(unittest.TestCase):
    def test_r4_a_dead_download_does_not_wait_after_its_last_try(self):
        sleeps = []
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(urllib.error.URLError):
                net.Http(offline=False, opener=dead, sleep=sleeps.append).download('https://wago.tools/x', d + '/x')
        self.assertEqual([x for x in sleeps if x >= 1], [3, 6])  # between the tries, not after the last one


class R5MarketplaceLine(Base):
    def test_r5_the_line_to_paste_holds_the_full_path(self):
        from forever import installer
        toolkit = installer.toolkit_dir()
        lines = []
        with mock.patch.dict(os.environ, {'HOME': os.path.dirname(toolkit)}):  # the toolkit lies under the home
            installer.next_steps(lines.append, 'python forever')
        line = next(ln for ln in lines if '/plugin marketplace add' in ln)
        self.assertEqual(line.split('/plugin marketplace add', 1)[1].strip(), toolkit)
        self.assertTrue(os.path.isabs(toolkit))

    def test_r5_the_other_setup_paths_stay_masked(self):
        home = self.t.env['HOME']
        game = os.path.join(home, 'Games', 'World of Warcraft', '_forever_')
        shutil.copytree(self.game, game)
        env = {'FOREVER_CACHE_DIR': os.path.join(home, 'cache'), 'FOREVER_CONFIG_DIR': os.path.join(home, 'config')}
        with mock.patch.dict(os.environ, env):
            rc, text = self.run_cli('setup', '--no-download', '--game', game, game=False)
        self.assertEqual(rc, 0, text)
        for prefix in ('game folder:', 'add-on:', 'config:', 'cache:', 'launcher note'):
            line = next(ln for ln in text.splitlines() if ln.startswith(prefix))
            self.assertNotIn(self.t.env['HOME'], line)
            self.assertIn('~', line, line)


if __name__ == '__main__':
    unittest.main()
