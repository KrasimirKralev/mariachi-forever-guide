import os
import sqlite3
import tempfile
import unittest

from forever import build
from tests import fixtures


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='fg-build-')
        wago, fdb = fixtures.write_raw(cls.tmp.name)
        wdb = os.path.join(cls.tmp.name, 'questcache.wdb')
        with open(wdb, 'wb') as fh:
            fh.write(fixtures.quest_cache_bytes({990001: (36, 26, 990010, 2.4), 990050: (12, 10, 0, 1.0)}))
        cls.db_path = os.path.join(cls.tmp.name, 'forever.db')
        cls.summary = build.build(wago, fdb, cls.db_path, wdb, meta={'build': '9.9.9.12345'})
        cls.con = sqlite3.connect(cls.db_path)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.tmp.cleanup()

    def one(self, sql, *args):
        return self.con.execute(sql, args).fetchone()

    def test_summary(self):
        self.assertEqual(self.summary['missing'], [])
        self.assertEqual(self.summary['forever quests'], 3)
        self.assertEqual(self.summary['classic quests'], 2)
        self.assertEqual(self.summary['quests from your game cache'], 2)

    def test_items_game_table_wins_then_foreverdb_names(self):
        self.assertEqual(self.one('SELECT name, quality, ilvl, req, inv, src FROM item WHERE id=900001'),
                         ('Mock Silk Cap', 3, 30, 25, 1, 'game'))
        self.assertEqual(self.one('SELECT name, src FROM item WHERE id=900020'), ('Server Only Gem', 'foreverdb'))
        self.assertEqual(self.one('SELECT name FROM item WHERE id=900030'), ('Quest Trinket',))
        self.assertEqual(self.one('SELECT name FROM item WHERE id=920002'), ('Vendor Only Thread',))
        self.assertIsNone(self.one('SELECT name FROM item WHERE id=900099'))  # a nameless row is not an item name

    def test_enchant_numbers_filled_in(self):
        self.assertEqual(self.one('SELECT name FROM enchant WHERE id=8002'), ('Armor +16 and Power +4',))

    def test_taxi_on_its_zone_map(self):
        self.assertEqual(self.one('SELECT uimap, x, y, horde, alliance FROM taxi WHERE id=501'), (9901, 75.0, 50.0, 2, 0))
        self.assertEqual(self.one('SELECT uimap, x, y FROM taxi WHERE id=502'), (9902, 50.0, 50.0))
        # inside a city that lies inside a zone: the city's own map, not the zone's (Mockzone holds it too)
        self.assertEqual(self.one('SELECT uimap, x, y FROM taxi WHERE id=503'), (9903, 50.0, 50.0))

    def test_quests(self):
        row = self.one('SELECT title, level, min, min_src, side, starts, ends, after, xp, next, xp_mult, new FROM quest WHERE id=990001')
        # the player's own game cache wins for the level and the minimum level
        self.assertEqual(row, ('Mock Quest', 36, 26, 'your game', 'h', 'n980001', 'n980002', 990005, 8200, 990010, 2.4, 1))
        self.assertEqual(self.one('SELECT title FROM quest WHERE id=990006'), ('Twin Quest',))
        self.assertEqual(self.one('SELECT objective FROM quest WHERE id=990006'), ('Do a "quoted" thing.',))
        self.assertEqual(self.one('SELECT title, level, min FROM quest_classic WHERE id=990002'), ('Old Classic Quest', 22, 18))
        self.assertEqual(self.one('SELECT xp FROM quest WHERE id=990002'), (900,))
        self.assertEqual(self.one('SELECT level, min FROM quest WHERE id=990050'), (12, 10))

    def test_twins_both_ways(self):
        self.assertEqual(self.con.execute('SELECT other FROM twin WHERE quest=990007').fetchall(), [(990006,)])
        self.assertEqual(self.con.execute('SELECT other FROM twin WHERE quest=990006').fetchall(), [(990007,)])

    def test_spots(self):
        self.assertEqual(self.con.execute("SELECT kind, uimap, x, y, src FROM quest_spot WHERE quest=990001 ORDER BY kind").fetchall(),
                         [('e', 9902, 12.3, 45.6, 'client'), ('s', 9901, 63.1, 44.9, 'client')])
        self.assertIn((9902, 12.3, 45.6, 'seen'), self.con.execute('SELECT uimap, x, y, src FROM npc_spot WHERE npc=980002').fetchall())
        self.assertEqual(self.con.execute('SELECT src FROM npc_spot WHERE npc=980006').fetchall(), [('classic',)])
        self.assertEqual(self.one('SELECT name, src FROM npc WHERE id=980004'), ('Classic Carl', 'classic'))
        self.assertEqual(self.one('SELECT name, title, side FROM npc WHERE id=980001'), ('Trainer Tom', 'Tailoring Trainer', 'H'))
        self.assertEqual(self.one('SELECT name FROM object WHERE id=970001'), ('Mock Chest',))

    def test_vendors_sources_loot(self):
        self.assertEqual(self.con.execute('SELECT npc, price FROM sold WHERE item=920001 ORDER BY npc').fetchall(),
                         [(980005, 50), (980006, 45)])
        self.assertEqual(self.one('SELECT n FROM sold_count WHERE item=920001'), (3,))
        self.assertIn('c^Tailoring^125', self.one('SELECT raw FROM gear_source WHERE item=900001')[0])
        self.assertEqual(self.con.execute('SELECT item, boss, inst, pct, src, kills FROM loot ORDER BY item').fetchall(),
                         [(900010, 'Boss Bramble', 'Mock Depths', 12.5, 'f', 40), (900011, 'Boss Bramble', 'Mock Depths', 3.0, 'c', None),
                          (920003, 'trash', 'Mock Depths', 0.0, 'f', None)])  # :h:kills:seen = '', '', 4

    def test_meta(self):
        meta = dict(self.con.execute('SELECT key, value FROM meta').fetchall())
        self.assertEqual(meta['foreverdb_version'], '2030-01-01.test')
        self.assertEqual(meta['build'], '9.9.9.12345')
        self.assertEqual(meta['xp_curve'], '[11, 22, 33, 44, 55]')

    def test_missing_files_are_listed_not_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            s = build.build(os.path.join(d, 'no'), os.path.join(d, 'no'), os.path.join(d, 'x.db'))
            self.assertIn('ItemSparse.csv', s['missing'])
            self.assertIn('QuestForever.lua', s['missing'])
            self.assertTrue(os.path.exists(os.path.join(d, 'x.db')))

    def test_quest_cache_rejects_other_layouts(self):
        self.assertEqual(build.quest_cache(b'NOPE' + b'\x00' * 40), {})
        self.assertEqual(build.quest_cache(b''), {})


if __name__ == '__main__':
    unittest.main()
