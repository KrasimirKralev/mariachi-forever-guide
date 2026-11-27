import os
import tempfile
import time
import unittest

from forever import paths


def mkgame(path, marker='WTF'):
    os.makedirs(os.path.join(path, marker) if marker in ('WTF', 'Interface') else path, exist_ok=True)
    if marker not in ('WTF', 'Interface'):
        open(os.path.join(path, marker), 'w').close()
    return path


class Dirs(unittest.TestCase):
    def test_linux(self):
        j = os.path.join
        env = {}
        self.assertEqual(paths.cache_dir(env, 'Linux', 'h'), j('h', '.cache', 'mariachi-forever-guide'))
        self.assertEqual(paths.config_dir(env, 'Linux', 'h'), j('h', '.config', 'mariachi-forever-guide'))
        env = {'XDG_CACHE_HOME': 'xc', 'XDG_CONFIG_HOME': 'xf'}
        self.assertEqual(paths.cache_dir(env, 'Linux', 'h'), j('xc', 'mariachi-forever-guide'))
        self.assertEqual(paths.config_dir(env, 'Linux', 'h'), j('xf', 'mariachi-forever-guide'))

    def test_macos(self):
        j = os.path.join
        self.assertEqual(paths.cache_dir({}, 'Darwin', 'U'), j('U', 'Library', 'Caches', 'mariachi-forever-guide'))
        self.assertEqual(paths.config_dir({}, 'Darwin', 'U'),
                         j('U', 'Library', 'Application Support', 'mariachi-forever-guide'))

    def test_windows(self):
        env = {'LOCALAPPDATA': 'L', 'APPDATA': 'R'}
        self.assertEqual(paths.cache_dir(env, 'Windows', 'H'), os.path.join('L', 'mariachi-forever-guide', 'Cache'))
        self.assertEqual(paths.config_dir(env, 'Windows', 'H'), os.path.join('R', 'mariachi-forever-guide'))

    def test_overrides_win(self):
        env = {'FOREVER_CACHE_DIR': 'c', 'FOREVER_CONFIG_DIR': 'f'}
        for system in ('Linux', 'Darwin', 'Windows'):
            self.assertEqual(paths.cache_dir(env, system, 'h'), 'c')
            self.assertEqual(paths.config_dir(env, system, 'h'), 'f')


class Detect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fg-paths-')
        self.root = self.tmp.name
        self.home = os.path.join(self.root, 'home')
        os.makedirs(self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def test_windows_program_files_and_registry(self):
        c = os.path.join(self.root, 'C')
        pf = mkgame(os.path.join(c, 'Program Files (x86)', 'World of Warcraft', '_forever_'), 'Wow.exe')
        self.assertEqual(paths.detect('Windows', self.home, {}, roots=[c], registry=[]), [pf])
        d = os.path.join(self.root, 'D', 'Games', 'World of Warcraft')
        reg = mkgame(os.path.join(d, '_forever_'))
        # the registry names a flavour folder: its parent is the World of Warcraft folder
        found = paths.detect('Windows', self.home, {}, roots=[c], registry=[os.path.join(d, '_retail_') + '\\'])
        self.assertEqual(set(found), {pf, reg})

    def test_macos_applications(self):
        apps = os.path.join(self.root, 'Applications')
        game = mkgame(os.path.join(apps, 'World of Warcraft', '_forever_'), 'Interface')
        self.assertEqual(paths.detect('Darwin', self.home, {}, roots=[apps]), [game])

    def test_linux_prefixes(self):
        made = [
            mkgame(os.path.join(self.home, '.wine', 'drive_c', 'Program Files (x86)', 'World of Warcraft', '_forever_')),
            mkgame(os.path.join(self.home, 'Games', 'battle-net', 'drive_c', 'Program Files', 'World of Warcraft', '_forever_')),
            mkgame(os.path.join(self.home, '.local', 'share', 'bottles', 'bottles', 'Gaming', 'drive_c',
                                'Program Files (x86)', 'World of Warcraft', '_forever_')),
            mkgame(os.path.join(self.home, '.steam', 'steam', 'steamapps', 'compatdata', '123', 'pfx', 'drive_c',
                                'Program Files (x86)', 'World of Warcraft', '_forever_')),
            mkgame(os.path.join(self.home, 'Games', 'my', 'odd', 'place', 'World of Warcraft', '_forever_')),
        ]
        self.assertEqual(set(paths.detect('Linux', self.home, {})), set(made))

    def test_newest_played_first(self):
        old = mkgame(os.path.join(self.home, '.wine', 'drive_c', 'Program Files (x86)', 'World of Warcraft', '_forever_'))
        new = mkgame(os.path.join(self.home, 'Games', 'b', 'drive_c', 'Program Files (x86)', 'World of Warcraft', '_forever_'))
        t = time.time()
        os.utime(os.path.join(old, 'WTF'), (t - 1000, t - 1000))
        os.utime(os.path.join(new, 'WTF'), (t, t))
        self.assertEqual(paths.detect('Linux', self.home, {})[0], new)

    def test_nothing_found(self):
        self.assertEqual(paths.detect('Linux', self.home, {}), [])

    def test_explicit_folder_wins_and_parent_is_accepted(self):
        game = mkgame(os.path.join(self.root, 'x', 'World of Warcraft', '_forever_'))
        auto = mkgame(os.path.join(self.home, '.wine', 'drive_c', 'Program Files', 'World of Warcraft', '_forever_'))
        env = {'HOME': self.home}
        self.assertEqual(paths.find_game(os.path.dirname(game), env, {}), (game, '--game'))
        self.assertEqual(paths.find_game(None, dict(env, FOREVER_GAME_DIR=game), {})[0], game)
        self.assertEqual(paths.find_game(None, env, {'game': game})[0], game)
        self.assertEqual(paths.find_game(None, env, {}, system='Linux', home=self.home)[0], auto)
        self.assertEqual(paths.find_game(None, {'HOME': self.home}, {}, system='Linux')[0], auto)  # HOME is used

    def test_wrong_explicit_folder_is_not_second_guessed(self):
        mkgame(os.path.join(self.home, '.wine', 'drive_c', 'Program Files', 'World of Warcraft', '_forever_'))
        game, why = paths.find_game(os.path.join(self.root, 'nope'), {'HOME': self.home}, {})
        self.assertIsNone(game)
        self.assertIn('not a WoW Forever folder', why)

    def test_build_info(self):
        game = mkgame(os.path.join(self.root, 'World of Warcraft', '_forever_'))
        with open(os.path.join(self.root, 'World of Warcraft', '.build.info'), 'w') as fh:
            fh.write('Branch!STRING:0|Active!DEC:1|Version!STRING:0|Product!STRING:0\n'
                     'eu|0|1.0.0.10001|wowf\neu|1|1.2.3.45678|wowf\neu|1|9.0.0.10000|wow\n')
        self.assertEqual(paths.build_info(game), '1.2.3.45678')
        self.assertIsNone(paths.build_info(os.path.join(self.root, 'none')))

    def test_config_roundtrip(self):
        env = {'FOREVER_CONFIG_DIR': os.path.join(self.root, 'cfg')}
        self.assertEqual(paths.load_config(env), {})
        paths.save_config({'game': '/g'}, env)
        self.assertEqual(paths.load_config(env), {'game': '/g'})


if __name__ == '__main__':
    unittest.main()
