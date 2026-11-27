"""Where things live: the cache and config folders of each OS, and the WoW Forever game folder.

The game folder is found in this order: --game DIR, the environment variable FOREVER_GAME_DIR, the config file,
then a search of the usual places (Windows, macOS, Linux with Wine, Proton, Lutris, Bottles or Steam).
An explicit folder that is wrong is reported as wrong; the search is never used to second-guess it.
"""
import json
import os
import platform
import re

from . import APP

FLAVOR = '_forever_'
GAME_MARKERS = ('Wow.exe', 'Wow-64.exe', 'WowT.exe', 'World of Warcraft.app', 'WTF', 'Interface')
WOW = 'World of Warcraft'
PROGRAM_DIRS = ('Program Files (x86)', 'Program Files')


def _system(system):
    return system or platform.system()


def _home(home, env=None):
    env = os.environ if env is None else env
    return home or env.get('HOME') or env.get('USERPROFILE') or os.path.expanduser('~')


def cache_dir(env=None, system=None, home=None):
    env = os.environ if env is None else env
    system, home = _system(system), _home(home, env)
    if env.get('FOREVER_CACHE_DIR'):
        return env['FOREVER_CACHE_DIR']
    if system == 'Windows':
        return os.path.join(env.get('LOCALAPPDATA') or os.path.join(home, 'AppData', 'Local'), APP, 'Cache')
    if system == 'Darwin':
        return os.path.join(home, 'Library', 'Caches', APP)
    return os.path.join(env.get('XDG_CACHE_HOME') or os.path.join(home, '.cache'), APP)


def config_dir(env=None, system=None, home=None):
    env = os.environ if env is None else env
    system, home = _system(system), _home(home, env)
    if env.get('FOREVER_CONFIG_DIR'):
        return env['FOREVER_CONFIG_DIR']
    if system == 'Windows':
        return os.path.join(env.get('APPDATA') or os.path.join(home, 'AppData', 'Roaming'), APP)
    if system == 'Darwin':
        return os.path.join(home, 'Library', 'Application Support', APP)
    return os.path.join(env.get('XDG_CONFIG_HOME') or os.path.join(home, '.config'), APP)


# ---- folders this tool owns ----------------------------------------------------------------------------------
# A marker file says "this tool made or used this folder". Uninstall and purge touch only folders that hold it,
# and in them only the tool's own files by name, so a folder shared with other things (FOREVER_CACHE_DIR,
# FOREVER_CONFIG_DIR, --cache) never loses anything that is not the tool's.
MARKER = '.mariachi-forever-guide'


class NotOurs(Exception):
    """A file of the same name is in the folder, and the folder is not this tool's: it is left alone."""


def owns(folder):
    return bool(folder) and os.path.isfile(os.path.join(folder, MARKER))


# the names the tool itself makes in each folder: a folder that already holds one of them without the marker is
# someone else's, and the tool neither marks it nor writes into it
CONFIG_NAMES = ('config.json', 'launcher.txt', 'levels.json')
CACHE_NAMES = ('forever.db', 'stamp.json', os.path.join('raw', 'wago'), os.path.join('raw', 'foreverdb'),
               os.path.join('tips', 'item'), os.path.join('tips', 'quest'), os.path.join('tips', 'npc'))


ALL_NAMES = CONFIG_NAMES + CACHE_NAMES


def check_free(folder, own_names=()):
    """NotOurs when the folder is not the tool's and already holds one of its names; nothing is written."""
    if owns(folder):
        return
    present = [n for n in ALL_NAMES + tuple(own_names) if os.path.lexists(os.path.join(folder, n))]
    if present:
        raise NotOurs('%s already holds %s, and it is not this tool\'s folder (it has no %s marker): nothing '
                      'changed. Point the tool at an empty folder.' % (show(folder), present[0], MARKER))


def claim(folder, own_names=()):
    """The one gate every writer goes through: a folder with the marker is the tool's; a folder without it becomes
    the tool's (marker written) only when NONE of the tool's names is in it already, the config's and the cache's
    alike, whoever asks (one folder may serve both roles). Else NotOurs."""
    if owns(folder):
        return folder
    check_free(folder, own_names)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, MARKER), 'w', encoding='utf-8') as fh:
        fh.write('This folder is used by ' + APP + '. `forever setup --uninstall` removes only its own '
                 'files here.\n')
    return folder


# ---- printing paths -------------------------------------------------------------------------------------------
# a WoW account folder in any path, with one or two separators (an error's text on Windows doubles backslashes)
ACCOUNT = re.compile(r'([/\\]{1,2}WTF[/\\]{1,2}Account[/\\]{1,2})[^/\\\'"]+', re.I)


def _windows_form(home):
    """A Windows home as a pattern: "/" and "\\" (one or doubled) are the same, and the drive is "C:" or, as Git
    Bash writes it, "/c"."""
    parts = re.sub(r'[/\\]+', '/', home).split('/')
    if len(parts) > 2 and parts[0] == '' and re.match(r'^[A-Za-z]$', parts[1]):
        parts = [parts[1] + ':'] + parts[2:]  # Git Bash writes the drive C: as /c
    head = re.escape(parts[0])
    if re.match(r'^[A-Za-z]:$', parts[0]):
        head = r'(?:%s:|[/\\]%s)' % (parts[0][0], parts[0][0])
    return r'[/\\]{1,2}'.join([head] + [re.escape(p) for p in parts[1:]])


def _home_pattern(homes, system):
    """The home folder as a whole folder: written as it is or with doubled backslashes (on Windows also with the
    other slash, from HOME or USERPROFILE), never inside a longer name (a home ending in "al" does not match a
    folder "alan"), and without regard to case on Windows."""
    if system == 'Windows':
        forms = {_windows_form(h) for h in homes}
    else:
        forms = {re.escape(h) for h in homes} | {re.escape(h.replace('\\', '\\\\')) for h in homes if '\\' in h}
    alternatives = '|'.join(sorted(forms, key=len, reverse=True))
    flags = re.I if system == 'Windows' else 0
    return re.compile(r'(?<![\w.~-])(?:%s)(?=[/\\]|$|[\'"\s:;,)]|\.(?=\s|$))' % alternatives, flags)


def mask(text, env=None, system=None):
    """Any text (an error's message, a path) with EVERY occurrence of the home folder shown as ~ and of a WoW
    account folder as <account>; FOREVER_DEBUG=1 leaves it as it is."""
    env = os.environ if env is None else env
    text = str(text)
    if env.get('FOREVER_DEBUG'):
        return text
    system = _system(system)
    # on Windows both may name the home, HOME (Git Bash's) perhaps with the other slash
    homes = [h for h in (env.get('HOME'), env.get('USERPROFILE')) if h] if system == 'Windows' else []
    homes = [h.rstrip('/\\') for h in homes or [_home(None, env)]]
    homes = [h for h in homes if len(h) > 1]
    if homes:
        text = _home_pattern(homes, system).sub('~', text)
    return ACCOUNT.sub(lambda m: m.group(1) + '<account>', text)


def show(path, env=None, system=None):
    """A path as it is printed: the home folder as ~ and the WoW account folder as <account>, so that what reaches
    the screen (and Claude) holds no user or account name. FOREVER_DEBUG=1 prints paths in full."""
    return mask(path, env, system)


def describe(err, env=None):
    """One line for an error: for an OSError its reason and the file it names (masked), else its masked text."""
    if isinstance(err, OSError) and err.strerror:
        return err.strerror + (': ' + mask(err.filename, env) if err.filename else '')
    return mask(err, env)


# ---- the config file ---------------------------------------------------------------------------------------

def config_path(env=None):
    return os.path.join(config_dir(env), 'config.json')


def load_config(env=None):
    try:
        with open(config_path(env), encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(cfg, env=None):
    path = config_path(env)
    claim(os.path.dirname(path), CONFIG_NAMES)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(cfg, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)
    return path


# ---- the game folder ---------------------------------------------------------------------------------------

def is_game_dir(path):
    return bool(path) and os.path.isdir(path) and any(os.path.exists(os.path.join(path, m)) for m in GAME_MARKERS)


def normalize_game_dir(path):
    """Accept the `_forever_` folder itself or the `World of Warcraft` folder that holds it."""
    path = os.path.abspath(os.path.expanduser(str(path)))
    inner = os.path.join(path, FLAVOR)
    if os.path.basename(path.rstrip('/\\')).lower() != FLAVOR and os.path.isdir(inner):
        return inner
    return path


def windows_registry_dirs():
    """World of Warcraft folders the Windows registry knows (empty anywhere else or on any error)."""
    try:
        import winreg  # only on Windows
    except ImportError:
        return []
    keys = [
        (r'SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft', 'InstallPath'),
        (r'SOFTWARE\Blizzard Entertainment\World of Warcraft', 'InstallPath'),
        (r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\World of Warcraft', 'InstallLocation'),
    ]
    out = []
    for key, name in keys:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
                value, _ = winreg.QueryValueEx(k, name)
        except OSError:
            continue
        if isinstance(value, str) and value.strip():
            out.append(value.strip())
    return out


def _wow_root(path):
    """The registry may name a flavour folder (`...\\_retail_\\`): the World of Warcraft folder is its parent."""
    path = path.rstrip('/\\')
    base = os.path.basename(path.replace('\\', '/'))
    if base.startswith('_') and base.endswith('_'):
        return os.path.dirname(path.replace('\\', '/'))
    return path


def _windows_drives():
    return [d + ':\\' for d in 'CDEFGHIJ' if os.path.isdir(d + ':\\')]


def _walk_for(root, name, max_depth):
    """Folders called `name` under root, at most max_depth levels down (no symlinks, no Windows system tree)."""
    found = []
    if not os.path.isdir(root):
        return found
    base_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, _ in os.walk(root, followlinks=False):
        depth = dirpath.count(os.sep) - base_depth
        if os.path.basename(dirpath) == name:
            found.append(dirpath)
            dirnames[:] = []
            continue
        if depth >= max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d.lower() not in ('windows', 'users', 'proc', 'sys', 'dosdevices')
                       and not d.startswith('.')]
    return found


def candidates(system=None, home=None, env=None, roots=None, registry=None):
    """Possible game folders for this OS, most likely first. `roots` and `registry` exist for tests."""
    env = os.environ if env is None else env
    system, home = _system(system), _home(home, env)
    out = []
    if system == 'Windows':
        for p in (registry if registry is not None else windows_registry_dirs()):
            out.append(os.path.join(_wow_root(p), FLAVOR))
        for r in (roots if roots is not None else _windows_drives()):
            for rel in PROGRAM_DIRS + ('Games', 'Blizzard', ''):
                out.append(os.path.join(r, rel, WOW, FLAVOR) if rel else os.path.join(r, WOW, FLAVOR))
    elif system == 'Darwin':
        for r in (roots if roots is not None else ['/Applications', os.path.join(home, 'Applications')]):
            out.append(os.path.join(r, WOW, FLAVOR))
    else:
        prefixes = [os.path.join(home, '.wine')]
        for base in (os.path.join(home, 'Games'),
                     os.path.join(home, '.local', 'share', 'bottles', 'bottles'),
                     os.path.join(home, '.var', 'app', 'com.usebottles.bottles', 'data', 'bottles', 'bottles'),
                     os.path.join(home, '.local', 'share', 'lutris', 'prefixes')):
            if os.path.isdir(base):
                prefixes += sorted(os.path.join(base, d) for d in os.listdir(base))
        for steam in (os.path.join(home, '.steam', 'steam'), os.path.join(home, '.local', 'share', 'Steam'),
                      os.path.join(home, '.var', 'app', 'com.valvesoftware.Steam', '.local', 'share', 'Steam')):
            compat = os.path.join(steam, 'steamapps', 'compatdata')
            if os.path.isdir(compat):
                prefixes += sorted(os.path.join(compat, d, 'pfx') for d in os.listdir(compat))
        if env.get('WINEPREFIX'):
            prefixes.insert(0, env['WINEPREFIX'])
        for pre in prefixes:
            for prog in PROGRAM_DIRS:
                out.append(os.path.join(pre, 'drive_c', prog, WOW, FLAVOR))
        # anything else under ~/Games (Lutris lets people pick their own folders), a few levels deep
        for wow in _walk_for(os.path.join(home, 'Games'), WOW, 6):
            out.append(os.path.join(wow, FLAVOR))
        out.append(os.path.join(home, WOW, FLAVOR))
    seen, unique = set(), []
    for p in out:
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def detect(system=None, home=None, env=None, roots=None, registry=None):
    """Every game folder that exists, the most recently played first."""
    found = [p for p in candidates(system, home, env, roots, registry) if is_game_dir(p)]

    def played(p):
        try:
            wtf = os.path.join(p, 'WTF')
            return os.path.getmtime(wtf if os.path.isdir(wtf) else p)
        except OSError:
            return 0
    return sorted(found, key=played, reverse=True)


def find_game(cli=None, env=None, config=None, **search):
    """(folder or None, how it was found or why not)."""
    env = os.environ if env is None else env
    config = load_config(env) if config is None else config
    for value, how in ((cli, '--game'), (env.get('FOREVER_GAME_DIR'), 'FOREVER_GAME_DIR'),
                       (config.get('game'), 'the config file')):
        if value:
            path = normalize_game_dir(value)
            if is_game_dir(path):
                return path, how
            return None, ('%s names %s, which is not a WoW Forever folder (it needs WTF, Interface or Wow.exe)'
                          % (how, show(path, env)))
    found = detect(env=env, **search)
    if found:
        return found[0], 'found' + (' (also found: %s)' % ', '.join(show(p, env) for p in found[1:])
                                    if len(found) > 1 else '')
    return None, 'not found in the usual places'


def build_info(game_dir):
    """The installed client's version (`1.60.1.71139`) from the `.build.info` next to `_forever_`, or None."""
    if not game_dir:
        return None
    import csv
    parent = os.path.dirname(game_dir.rstrip('/\\'))
    for path in (os.path.join(parent, '.build.info'), os.path.join(game_dir, '.build.info')):
        try:
            with open(path, encoding='utf-8', errors='replace', newline='') as fh:
                rows = list(csv.reader(fh, delimiter='|'))
        except OSError:
            continue
        if not rows:
            continue
        head = [h.split('!')[0] for h in rows[0]]
        active = []
        for r in rows[1:]:
            d = dict(zip(head, r))
            if d.get('Product') == 'wowf':
                active.append((d.get('Active') == '1', d.get('Version')))
        active.sort(reverse=True)
        if active and active[0][1]:
            return active[0][1]
    return None
