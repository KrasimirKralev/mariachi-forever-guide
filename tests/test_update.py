import json
import os
import unittest

from forever import net
from forever.data import Store
from tests import fixtures
from tests.fakenet import FakeNet, forever_routes


class Update(unittest.TestCase):
    def setUp(self):
        self.env = fixtures.TempEnv().__enter__()
        self.lines = []
        self.game = fixtures.fake_game(self.env.root)
        self.fake = FakeNet(forever_routes())

        self.stores = []

    def tearDown(self):
        for s in self.stores:
            s.close()
        self.env.__exit__()

    def store(self, game=None):
        http = net.Http(offline=False, opener=self.fake, sleep=lambda s: None)
        s = Store(cache=self.env.env['FOREVER_CACHE_DIR'], game=game, http=http, out=self.lines.append)
        self.stores.append(s)
        return s

    def test_first_run_downloads_builds_and_stamps(self):
        s = self.store(self.game)
        self.assertEqual(s.check()[0], 2)
        self.assertEqual(s.update(), 0, '\n'.join(self.lines))
        urls = [u for u, _ in self.fake.requests]
        self.assertEqual(len(urls), 6 + 1 + 8)  # six game tables, the manifest, eight ForeverDB files
        self.assertNotIn('https://wago.tools/api/builds', urls)  # the game folder says which build
        st = s.stamp()
        self.assertEqual(st['build'], '9.9.9.12345')
        self.assertEqual(st['foreverdb'], '2030-01-01.test')
        self.assertEqual(s.q('SELECT min_src FROM quest WHERE id=990001'), [('your game',)])
        self.assertIn('Data from ForeverDB.net (https://foreverdb.net)', s.data_line())
        self.assertEqual(s.check()[0], 0)

    def test_second_run_fetches_only_the_manifest(self):
        self.store(self.game).update()
        n = len(self.fake.requests)
        self.assertEqual(self.store(self.game).update(), 0)
        self.assertEqual([u for u, _ in self.fake.requests[n:]], ['https://foreverdb.net/downloads/addon-manifest.json'])

    def test_without_a_game_the_newest_build_is_asked(self):
        self.assertEqual(self.store(None).update(), 0)
        self.assertEqual(self.fake.requests[0][0], 'https://wago.tools/api/builds')

    def test_a_drop_midway_resumes_on_the_next_run(self):
        routes = forever_routes()
        big = [u for u in routes if 'QuestForever.lua' in u][0]
        self.fake.fail_once.add(big)
        self.fake.routes.pop(big)  # this run: that file is not reachable at all
        s = self.store(self.game)
        rc = s.update()
        self.assertEqual(rc, 1)
        self.assertTrue(any('QuestForever.lua' in ln for ln in self.lines))
        self.fake.routes[big] = routes[big]
        n = len(self.fake.requests)
        self.assertEqual(self.store(self.game).update(), 0)
        fetched = [u for u, _ in self.fake.requests[n:]]
        self.assertEqual(fetched, ['https://foreverdb.net/downloads/addon-manifest.json', big])

    def test_a_cache_folder_with_odd_characters(self):
        odd = os.path.join(self.env.root, 'my #1 cache 100% ok')
        http = net.Http(offline=False, opener=self.fake, sleep=lambda s: None)
        s = Store(cache=odd, game=self.game, http=http, out=self.lines.append)
        self.stores.append(s)
        self.assertEqual(s.update(), 0)
        self.assertEqual(s.q('SELECT name FROM item WHERE id=900001'), [('Mock Silk Cap',)])

    def test_check_says_stale_when_the_game_moves_on(self):
        s = self.store(self.game)
        s.update()
        info = os.path.join(os.path.dirname(self.game), '.build.info')
        with open(info, 'w') as fh:
            fh.write('Branch!STRING:0|Active!DEC:1|Version!STRING:0|Product!STRING:0\neu|1|9.9.10.10001|wowf\n')
        rc, line = s.check()
        self.assertEqual(rc, 1)
        self.assertIn('9.9.10.10001', line)

    def test_offline_update_keeps_what_is_there(self):
        self.store(self.game).update()
        offline = Store(cache=self.env.env['FOREVER_CACHE_DIR'], game=self.game, http=net.Http(offline=True),
                        out=self.lines.append)
        self.stores.append(offline)
        self.assertIn(offline.update(), (0, 1))
        self.assertTrue(os.path.exists(offline.db_path))
        with open(os.path.join(self.env.env['FOREVER_CACHE_DIR'], 'stamp.json')) as fh:
            self.assertTrue(json.load(fh)['problems'])

    def test_tooltips_are_cached_and_offline_safe(self):
        s = self.store(self.game)
        url = 'https://nether.wowhead.com/forever/tooltip/item/900001'
        self.fake.routes[url] = json.dumps({'name': 'Mock Silk Cap', 'tooltip': '<b>Mock Silk Cap</b><br>+8 Agility'}).encode()
        self.assertEqual(s.tooltip('item', 900001)['name'], 'Mock Silk Cap')
        n = len(self.fake.requests)
        self.assertEqual(s.tooltip('item', 900001)['name'], 'Mock Silk Cap')
        self.assertEqual(len(self.fake.requests), n)  # from the cache
        self.assertEqual(s.tooltip('item', 4242), {'error': 404})
        self.assertIsNone(Store(cache=s.cache, http=net.Http(offline=True)).tooltip('quest', 1))


if __name__ == '__main__':
    unittest.main()
