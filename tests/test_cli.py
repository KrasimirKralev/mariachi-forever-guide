"""Smoke tests of the command line against a fake game folder and the synthetic data (no network, temp dirs)."""
import json
import os
import shutil
import unittest
from unittest import mock

from forever import cli, net
from forever.data import Store
from tests import fixtures
from tests.fakenet import FakeNet, forever_routes


class CLI(unittest.TestCase):
    def setUp(self):
        self.t = fixtures.TempEnv().__enter__()
        self.game = fixtures.fake_game(self.t.root)
        cache = self.t.env['FOREVER_CACHE_DIR']
        s = Store(cache=cache, game=self.game, http=net.Http(offline=False, opener=FakeNet(forever_routes()),
                                                             sleep=lambda s: None), out=lambda *_: None)
        s.update()
        s.close()
        tips = os.path.join(cache, 'tips', 'item')
        os.makedirs(tips)
        os.makedirs(os.path.join(cache, 'tips', 'quest'))
        with open(os.path.join(cache, 'tips', 'quest', '990001.json'), 'w') as fh:
            json.dump({'name': 'Mock Quest', 'tooltip': '<b>Mock Quest</b><br>Bring hides.<br>- Mock Silk (5)<br>- Mock Note'}, fh)
        with open(os.path.join(tips, '900020.json'), 'w') as fh:
            json.dump({'name': 'Server Only Gem', 'quality': 4, 'tooltip': '<b>Server Only Gem</b><br>Item Level 33<br>'
                       'Binds when equipped Neck<br>Requires Level 28'}, fh)
        with open(os.path.join(tips, '900001.json'), 'w') as fh:
            json.dump({'name': 'Mock Silk Cap', 'quality': 3, 'tooltip':
                       '<table><tr><td><b>Mock Silk Cap</b><br>Binds when equipped<br>Head<br>+8 Agility</td></tr></table>'}, fh)

    def tearDown(self):
        self.t.__exit__()

    def run_cli(self, *argv, game=True):
        lines = []
        args = list(argv) + (['--game', self.game] if game else [])
        rc = cli.main(args, env=dict(os.environ), out=lines.append)
        return rc, '\n'.join(str(x) for x in lines)

    # ---- me ----
    def test_me_summary_and_parts(self):
        rc, text = self.run_cli('me')
        self.assertEqual(rc, 0, text)
        self.assertIn('Testa-Mockrealm · level 22 Undead Warlock (Horde)', text)
        self.assertIn('XP 9,000 / 27,300 (32%)', text)
        self.assertIn('12g 34s 56c', text)
        self.assertIn('from: your snapshot ForeverBridge.lua', text)
        for part, expect in (('gear', 'Armor +16 and Power +4'), ('gear', '+8 Agi +6 Sta · 67 armor'),
                             ('stats', 'about 19.4 damage per second'), ('skills', 'Tailoring'),
                             ('recipes', 'Mock Belt'), ('trainer', 'needs Tailoring 100  price 2s 50c'),
                             ('vendor', 'Pattern: Mock Kit'), ('rep', 'Friendly'), ('bags', 'Mock Salt'),
                             ('talents', 'Mock Aim'), ('quests', '2 quests done, 3 in the log'),
                             ('status', 'auto-save off'), ('json', '"Testa-Mockrealm"')):
            rc, text = self.run_cli('me', part)
            self.assertEqual(rc, 0, part + ': ' + text)
            self.assertIn(expect, text, part)

    def test_me_quests_by_name_number_and_twin(self):
        rc, text = self.run_cli('me', 'quests', 'Mock Prelude')
        self.assertIn('990005 done', text.replace('  ', ' ').replace('  ', ' '))
        rc, text = self.run_cli('me', 'quests', 'Mock Quest')
        self.assertIn('in your quest log (ready to hand in)', text)
        rc, text = self.run_cli('me', 'quests', '990006')
        self.assertIn('done (under its twin id 990007)', text)
        rc, text = self.run_cli('me', 'quests', '990002')
        self.assertIn('Old Classic Quest: in your quest log', text)

    def test_me_xp_budget(self):
        rc, text = self.run_cli('me', 'xp')
        self.assertEqual(rc, 0, text)
        # 18,300 left at 22, then the Classic bars of 23 to 28
        self.assertIn('Room before level 29: about 230,100 XP', text)
        self.assertIn('Classic data', text)
        self.assertIn('worth about 9,100 XP in full (8,200 ready to hand in)', text)
        self.assertIn('1 quest(s) have no XP recorded', text)
        # the bar of level 22 was learned from the snapshot
        with open(os.path.join(self.t.env['FOREVER_CONFIG_DIR'], 'levels.json')) as fh:
            self.assertEqual(json.load(fh), {'22': 27300})

    def test_me_missing_with_a_wish_list(self):
        rc, text = self.run_cli('me', 'missing', '--want', 'Mock Silk Cap, Glimmer Widget, Mock Ring')
        self.assertIn('Empty slots: Neck', text)
        self.assertIn('Nearly broken: Chest 8%', text)
        self.assertIn('Mock Silk Cap', text)
        self.assertIn('worn (Head)', text)
        self.assertIn('in your bags or bank', text)
        self.assertIn('not owned yet', text)

    def test_me_and_price_make_no_network_requests(self):
        # the socket layer itself: whatever opener the code uses, a connection would have to pass through here
        os.environ.pop('FOREVER_OFFLINE', None)
        with mock.patch('socket.create_connection', side_effect=AssertionError('network used')) as connect, \
                mock.patch('socket.socket.connect', side_effect=AssertionError('network used')) as raw, \
                mock.patch('socket.getaddrinfo', side_effect=AssertionError('network used')) as lookup:
            for argv in (('me',), ('me', 'xp'), ('me', 'gear'), ('me', 'quests', 'Mock Quest'), ('price', 'Mock Salt')):
                rc, text = self.run_cli(*argv)
                self.assertEqual(rc, 0, text)
            self.assertFalse(connect.called or raw.called or lookup.called)

    def test_quest_state_is_unknown_without_a_quest_history(self):
        sv = os.path.join(self.game, 'WTF', 'Account', 'TESTACCOUNT', 'SavedVariables', 'ForeverBridge.lua')
        with open(sv, 'w', encoding='utf-8') as fh:
            fh.write(fixtures.saved_variables('ForeverBridgeDB', fixtures.snapshot(empty_at_logout=True)))
        rc, text = self.run_cli('me', 'quests', 'Mock Prelude')
        self.assertIn('done or not is unknown', text)
        self.assertNotIn(' not done', text)

    def test_logout_snapshot_without_gear_is_flagged(self):
        sv = os.path.join(self.game, 'WTF', 'Account', 'TESTACCOUNT', 'SavedVariables', 'ForeverBridge.lua')
        with open(sv, 'w', encoding='utf-8') as fh:
            fh.write(fixtures.saved_variables('ForeverBridgeDB', fixtures.snapshot(empty_at_logout=True)))
        rc, text = self.run_cli('me', 'status')
        self.assertIn('warning   no experience, stats, gear, bags, completed quests in this snapshot', text)
        rc, text = self.run_cli('me', 'gear')
        self.assertIn('No gear in this snapshot', text)
        rc, text = self.run_cli('me')
        self.assertIn('XP and gold: not in this snapshot', text)
        self.assertNotIn('Stamina 0', text)
        rc, text = self.run_cli('me', 'xp')
        self.assertIn('No experience numbers in this snapshot', text)

    def test_no_snapshot_yet(self):
        shutil.rmtree(os.path.join(self.game, 'WTF'))
        rc, text = self.run_cli('me')
        self.assertEqual(rc, 2)
        self.assertIn('No snapshot yet', text)

    # ---- price ----
    def test_price(self):
        rc, text = self.run_cli('price', 'Mock Salt, Glimmer Widget, Nothing At All')
        self.assertEqual(rc, 0, text)
        self.assertRegex(text, r'Mock Salt\s+53c\s+lowest seen 48c\s+seen today, 31 on offer')
        self.assertRegex(text, r'Glimmer Widget \(ilvl 35\)\s+2g 50s\s+lowest seen 2g 10s\s+seen 5 day\(s\) ago, 2 on offer')
        self.assertIn('Glimmer Widget                     15s', text)
        self.assertIn('Nothing At All                     not an item I know', text)
        self.assertIn('from: your Auctionator scans', text)

    # ---- item, quest, where ----
    def test_item(self):
        rc, text = self.run_cli('item', 'Mock Silk Cap')
        self.assertEqual(rc, 0, text)
        self.assertIn('900001  Mock Silk Cap  [rare, item level 30, needs level 25, Head]', text)
        self.assertIn('+8 Agility', text)
        self.assertIn('source: Crafted: Tailoring 125', text)
        self.assertIn('Data from ForeverDB.net', text)
        rc, text = self.run_cli('item', 'Mock Wand')
        self.assertIn('Quest: Mock Quest; Sold by Vera Vendor (Trade Supplies) for 2g 50s; Drops from Boss Bramble (2.5%) (Classic data)', text)
        rc, text = self.run_cli('item', '900020')
        self.assertIn('900020  Server Only Gem  [epic, item level 33, needs level 28, Neck]', text)
        rc, text = self.run_cli('item', '900004')
        self.assertIn('(no tooltip yet: offline)', text)
        rc, text = self.run_cli('item', 'Mock Salt')
        self.assertIn('sold by 3 vendor(s), e.g.: Vera Vendor (Trade Supplies), Testvale (40.0, 60.0): 50c', text)
        rc, text = self.run_cli('item', 'glimmer', '--list')
        self.assertIn('2 match(es)', text)
        rc, text = self.run_cli('item', 'Glimmer Widget')
        self.assertIn('Drops from Boss Bramble in Mock Depths (12.5% over 40 kills)', text)

    def test_quest_forever_first_classic_labelled(self):
        rc, text = self.run_cli('quest', 'Mock Quest')
        self.assertEqual(rc, 0, text)
        self.assertIn('Mock Quest (quest 990001)', text)
        self.assertIn('level 36 · from level 26 (your game cache) · Horde', text)
        self.assertIn('starts: Trainer Tom (Tailoring Trainer), Mockzone (63.1, 45.0)', text)  # 'seen' first
        self.assertIn('turn in: Ender Ella, Testvale (12.3, 45.6)', text)
        self.assertIn('after: Mock Prelude (990005)', text)
        self.assertIn('experience: 8,200', text)
        self.assertIn('needs: Mock Silk (5), Mock Note', text)
        self.assertNotIn('Classic data)', text.split('from:')[0])
        rc, text = self.run_cli('quest', 'Old Classic Quest')
        self.assertIn('Old Classic Quest (quest 990002) (Classic data)', text)
        self.assertIn('after: Mock Prelude (990005), Mock Quest (990001) (Classic data)', text)
        self.assertIn('level 22 · from level 17 (your game cache)', text)
        self.assertIn('starts: Classic Carl, Testvale (50.0, 50.0) (Classic data)', text)
        rc, text = self.run_cli('quest', 'Twin Quest')
        self.assertIn('starts: Mock Chest, Mockzone (20.0, 30.0) (Classic data)', text)
        rc, text = self.run_cli('quest', 'No Such Quest')
        self.assertEqual(rc, 1)

    def test_where(self):
        rc, text = self.run_cli('where', 'Trainer Tom')
        # seen twice a few steps apart and once in Classic data: one place, Forever's
        self.assertIn('Trainer Tom <Tailoring Trainer> [Horde]: Mockzone (63.1, 45.0)\n', text)
        self.assertNotIn('Classic data', text.split('from:')[0])
        self.assertEqual(text.count('Mockzone ('), 1)
        rc, text = self.run_cli('where', 'Mockzone')
        self.assertIn('Mock Post Mockzone', text)
        self.assertEqual(text.count('Trainer Tom'), 1)
        self.assertNotIn('Mock City Tower', text)
        rc, text = self.run_cli('where', 'Mock City')
        self.assertIn('Mock City Tower', text)
        self.assertIn('<flight point>', text)
        rc, text = self.run_cli('where', 'Mock Salt')
        self.assertIn('Mock Salt (item 920001) is sold by 3 vendor(s) (your side first)', text)
        self.assertLess(text.index('Vera Vendor'), text.index('Alice Ally'))
        rc, text = self.run_cli('where', 'trade supplies')
        self.assertIn('Vera Vendor', text)
        self.assertNotIn('Alice Ally', text)  # the snapshot says Horde
        rc, text = self.run_cli('where', 'tailoring trainer')
        self.assertIn('Trainer Tom <Tailoring Trainer>', text)
        rc, text = self.run_cli('where', 'trade supplies', '--side', 'alliance')
        self.assertIn('Alice Ally', text)
        self.assertIn('(Classic data)', text)

    # ---- update, version, setup ----
    def test_update_check_and_version(self):
        rc, text = self.run_cli('update', '--check')
        self.assertEqual(rc, 0, text)
        self.assertIn('game 9.9.9.12345: data current', text)
        rc, text = self.run_cli('version')
        self.assertIn('Data from ForeverDB.net (https://foreverdb.net)', text)
        self.assertIn('wago.tools', text)
        self.assertIn("Wowhead's public tooltip service", text)
        self.assertIn('not affiliated with or endorsed by Blizzard Entertainment or Anthropic', text.replace('Not', 'not'))

    def test_setup_and_uninstall_touch_only_their_own_files(self):
        addons = os.path.join(self.game, 'Interface', 'AddOns')
        before = sorted(os.listdir(os.path.join(self.game, 'WTF', 'Account', 'TESTACCOUNT', 'SavedVariables')))
        rc, text = self.run_cli('setup', '--no-download')
        self.assertEqual(rc, 0, text)
        self.assertEqual(sorted(os.listdir(os.path.join(addons, 'ForeverBridge'))), ['ForeverBridge.lua', 'ForeverBridge.toc'])
        self.assertIn('/fbridge save', text)
        note = os.path.join(self.t.env['FOREVER_CONFIG_DIR'], 'launcher.txt')
        with open(note) as fh:
            py, toolkit = fh.read().splitlines()
        self.assertTrue(os.path.isfile(os.path.join(toolkit, 'forever', '__main__.py')))
        with open(os.path.join(addons, 'ForeverBridge', 'mine.txt'), 'w') as fh:
            fh.write('a file the player put there')
        rc, text = self.run_cli('setup', '--uninstall')
        self.assertEqual(rc, 0, text)
        self.assertEqual(os.listdir(os.path.join(addons, 'ForeverBridge')), ['mine.txt'])
        self.assertTrue(os.path.isfile(os.path.join(addons, 'SomeoneElsesAddon', 'Other.toc')))
        self.assertEqual(sorted(os.listdir(os.path.join(self.game, 'WTF', 'Account', 'TESTACCOUNT', 'SavedVariables'))), before)
        self.assertFalse(os.path.exists(note))

    def test_setup_without_a_game_asks_or_explains(self):
        with mock.patch('sys.stdin') as stdin:
            stdin.isatty.return_value = False
            rc, text = self.run_cli('setup', '--no-download', game=False)
        self.assertEqual(rc, 2)
        self.assertIn('setup --game', text)

    def test_friendly_error_line(self):
        with mock.patch('forever.lookup.Lookup.item', side_effect=RuntimeError('boom')):
            rc, text = self.run_cli('item', 'x')
        self.assertEqual(rc, 1)
        self.assertIn('something went wrong: RuntimeError: boom', text)


if __name__ == '__main__':
    unittest.main()
