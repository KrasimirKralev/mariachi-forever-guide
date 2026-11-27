"""`forever setup`: find the game, put the ForeverBridge add-on in place, download the data, say what is next.

It writes only: <game>/Interface/AddOns/ForeverBridge/ (two files, never through a link), this tool's own config
folder and its own cache folder (each marked with a .mariachi-forever-guide file). It never touches other add-ons,
accounts or WTF files. `forever setup --uninstall` removes the add-on's two files (and its folder when it is then
empty) and the tool's own files in its marked config folder; `--purge` also its own files in the marked cache.
"""
import glob
import os
import shutil
import sys
import tempfile

from . import PRODUCT, net, paths
from .data import Store

ADDON = 'ForeverBridge'
ADDON_FILES = ('ForeverBridge.toc', 'ForeverBridge.lua')
LAUNCHER_NOTE = 'launcher.txt'


def toolkit_dir():
    """The unzipped folder: the one that holds the `forever` package and the `addon` folder."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def addon_source():
    return os.path.join(toolkit_dir(), 'addon', ADDON)


class Refused(Exception):
    """A place the installer will not write to or delete from; the message is for the player."""


def addon_dest(game):
    """Interface/AddOns/ForeverBridge, but never through a link: a link there may point at anything (another
    folder, a checkout of this repository), and writing or deleting through it would hit that instead."""
    addons = os.path.join(game, 'Interface', 'AddOns')
    dest = os.path.join(addons, ADDON)
    if os.path.islink(dest):
        raise Refused('%s is a link to another folder: not touching it (remove the link, then run setup again)'
                      % paths.show(dest))
    if os.path.exists(dest) and os.path.realpath(dest) != os.path.join(os.path.realpath(addons), ADDON):
        raise Refused('%s does not lead where it says: not touching it' % paths.show(dest))
    if os.path.realpath(dest) == os.path.realpath(addon_source()):
        raise Refused("%s is this toolkit's own add-on folder (the source the add-on is copied from): not touching "
                      'it' % paths.show(dest))
    return dest


def outside_game(game):
    """(the folder, where it leads) when Interface or Interface/AddOns is a link that leaves the game folder."""
    real_game = os.path.realpath(game)
    for rel in ('Interface', os.path.join('Interface', 'AddOns')):
        p = os.path.join(game, rel)
        if os.path.exists(p):
            target = os.path.realpath(p)
            try:
                inside = os.path.commonpath([target, real_game]) == real_game
            except ValueError:  # another drive
                inside = False
            if not inside:
                return p, target
    return None


def links_ok(game, args, out, ask, doing):
    """A linked Interface or AddOns folder that leaves the game folder may be right (a second drive) or not (a
    checkout, another game): say where it leads and go on only with --force or the player's yes."""
    for rel in ('Interface', os.path.join('Interface', 'AddOns'), os.path.join('Interface', 'AddOns', ADDON)):
        p = os.path.join(game, rel)
        if os.path.islink(p) and not os.path.exists(p):
            out('%s is a link to a folder that does not exist: remove it or point it at a real folder, then run '
                'setup again.' % paths.show(p))
            return False
    away = outside_game(game)
    if not away:
        return True
    out('%s leads to %s, outside the game folder.' % (paths.show(away[0]), paths.show(away[1])))
    if getattr(args, 'force', False):
        out('going on (--force)')
        return True
    if sys.stdin and sys.stdin.isatty():
        try:
            return ask('%s the add-on there anyway? [y/N] ' % doing).strip().lower() in ('y', 'yes')
        except EOFError:
            return False
    out('Not touching it. Run again with --force if that really is where your add-ons live.')
    return False


def drop_leftovers(dest):
    """Temporary files a stopped setup can leave (".ForeverBridge.lua.<random>.tmp"): only those names."""
    for f in ADDON_FILES:
        for p in glob.glob(os.path.join(glob.escape(dest), '.' + glob.escape(f) + '.*.tmp')):
            if os.path.isfile(p) or os.path.islink(p):
                os.remove(p)


def install_addon(game):
    src, dest = addon_source(), addon_dest(game)
    missing = [f for f in ADDON_FILES if not os.path.isfile(os.path.join(src, f))]
    if missing:
        raise FileNotFoundError('the add-on files are missing from %s: %s' % (paths.show(src), ', '.join(missing)))
    os.makedirs(dest, exist_ok=True)
    addon_dest(game)  # again, now that the folder exists
    drop_leftovers(dest)
    for f in ADDON_FILES:
        # a fresh temporary file of our own (created exclusively: never an existing name, never through a link),
        # then renamed over the old one
        fd, tmp = tempfile.mkstemp(dir=dest, prefix='.' + f + '.', suffix='.tmp')
        try:
            with os.fdopen(fd, 'wb') as out, open(os.path.join(src, f), 'rb') as inp:
                shutil.copyfileobj(inp, out)
            os.chmod(tmp, 0o644)
            os.replace(tmp, os.path.join(dest, f))
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
    return dest


def uninstall_addon(game):
    """Remove exactly the two files the installer writes, by name; the folder goes only when it is then empty."""
    dest = addon_dest(game)
    removed = []
    if os.path.isdir(dest):
        drop_leftovers(dest)
    for f in ADDON_FILES:
        p = os.path.join(dest, f)
        if os.path.isfile(p) or os.path.islink(p):
            os.remove(p)
            removed.append(p)
    try:
        if os.path.isdir(dest) and not os.listdir(dest):
            os.rmdir(dest)
    except OSError:
        pass
    return removed


def write_launcher_note(config_dir):
    """Two lines the Claude plugin's `forever` command reads: which Python, and where this folder is."""
    paths.claim(config_dir, paths.CONFIG_NAMES)
    path = os.path.join(config_dir, LAUNCHER_NOTE)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(sys.executable + '\n' + toolkit_dir() + '\n')
    os.replace(tmp, path)
    return path


# what the tool itself makes in its cache and config folders: nothing else there is ever removed
CACHE_DIRS = (('raw', 'wago'), ('raw', 'foreverdb'), ('tips', 'item'), ('tips', 'quest'), ('tips', 'npc'))
CACHE_FILES = ('forever.db', 'forever.db.tmp', 'forever.db.tmp-journal', 'stamp.json', 'stamp.json.tmp')
CONFIG_FILES = ('config.json', 'config.json.tmp', LAUNCHER_NOTE, LAUNCHER_NOTE + '.tmp', 'levels.json',
                'levels.json.tmp')


def remove_own(folder, dirs, files, out):
    """Remove the tool's own files from a folder that carries its marker; report a folder that does not."""
    if not os.path.isdir(folder):
        return
    if not paths.owns(folder):
        out('left alone: %s (not this tool\'s folder: it has no %s marker)' % (paths.show(folder), paths.MARKER))
        return
    linked = set()
    for parts in dirs:
        # never follow a link out of the folder: not at raw/wago, and not at raw/ or tips/ above it either
        for n in range(1, len(parts) + 1):
            p = os.path.join(folder, *parts[:n])
            if os.path.islink(p):
                if p not in linked:
                    linked.add(p)
                    out('left alone: %s is a link to another folder' % paths.show(p))
                break
        else:
            p = os.path.join(folder, *parts)
            if os.path.isdir(p):
                shutil.rmtree(p)
    for parts in dirs:  # raw/ and tips/ themselves only when nothing else is in them
        parent = os.path.join(folder, parts[0])
        if os.path.isdir(parent) and not os.path.islink(parent) and not os.listdir(parent):
            os.rmdir(parent)
    for name in files:
        p = os.path.join(folder, name)
        if os.path.isfile(p) or os.path.islink(p):
            os.remove(p)
    out('removed this tool\'s files from %s' % paths.show(folder))


def drop_marker(folder):
    """The marker goes last, and only when none of the tool's names is left: one folder may serve both roles, and
    its other role's files keep it the tool's. An empty folder goes too."""
    if not paths.owns(folder):
        return
    if any(os.path.lexists(os.path.join(folder, n)) for n in paths.ALL_NAMES):
        return
    os.remove(os.path.join(folder, paths.MARKER))
    if not os.listdir(folder):
        try:
            os.rmdir(folder)
        except OSError:  # a folder given as a link: the link stays, and what it points to is left empty
            pass


def ask_for_game(ask, out, tries=3):
    out('Where is World of Warcraft installed? Paste the folder that holds _forever_ (or _forever_ itself).')
    for _ in range(tries):
        try:
            answer = ask('game folder: ').strip().strip('"\'')
        except EOFError:
            return None
        if not answer:
            return None
        path = paths.normalize_game_dir(answer)
        if paths.is_game_dir(path):
            return path
        out('That is not a WoW Forever folder (it needs WTF, Interface or Wow.exe inside): %s' % paths.show(path))
    return None


def next_steps(out, cmd):
    # every path printed is shortened (~, <account>) except the folder in the marketplace line: the player pastes
    # that line into Claude Code, which may not expand ~, so it must be the full path
    out('')
    out('Next:')
    out('  1. Start WoW Forever (a full restart if it was running: new add-ons load only then). On the character')
    out('     screen, AddOns: ForeverBridge must be ticked; tick "Load out of date AddOns" if the list says so.')
    out('  2. In the game type  /fbridge save  (it reloads the UI, and the game writes the file).')
    out('  3. Check here:  %s me status' % cmd)
    out('  4. For Claude: install Claude Code, sign in with your own Claude account (claude login), then in Claude')
    out('     Code add this folder as a plugin marketplace and install the plugin (see README.md):')
    out('       /plugin marketplace add %s' % toolkit_dir())
    out('       /plugin install forever-guide@mariachi-forever-guide')
    out('     and ask, for example: "what does my quest log give me before level 29?"')


def flavour_ok(game, args, out, ask):
    """The add-on is for WoW Forever: a folder not named _forever_ (another game flavour, a copy) needs a yes."""
    if os.path.basename(game.rstrip('/\\')).lower() == paths.FLAVOR:
        return True
    out('%s is not named %s: it looks like another flavour of the game or a copy.' % (paths.show(game), paths.FLAVOR))
    if getattr(args, 'force', False):
        out('installing there anyway (--force)')
        return True
    if sys.stdin and sys.stdin.isatty():
        try:
            return ask('Install the add-on there anyway? [y/N] ').strip().lower() in ('y', 'yes')
        except EOFError:
            return False
    out('Not installing. Run again with --force if that is really your WoW Forever folder.')
    return False


def uninstall(args, env, out, game, how, ask):
    if game and not links_ok(game, args, out, ask, 'Remove'):
        out('the add-on files stay where they are; removing the rest.')
        game = None
        how = 'kept'
    elif game:
        try:
            removed = uninstall_addon(game)
            out('removed: %s' % (', '.join(paths.show(p) for p in removed) if removed
                                 else 'nothing (the add-on was not installed in %s)' % paths.show(game)))
        except Refused as e:
            out(str(e))
    elif how != 'kept':
        out('No game folder found (%s): the add-on files in it, if any, stay; removing the rest.' % how)
    conf = paths.config_dir(env)
    cache = getattr(args, 'cache', None) or paths.cache_dir(env)
    remove_own(conf, (), CONFIG_FILES, out)
    if getattr(args, 'purge', False):
        remove_own(cache, CACHE_DIRS, CACHE_FILES, out)
    else:
        out('kept the downloaded data in %s (forever setup --uninstall --purge removes it too)' % paths.show(cache))
    for folder in dict.fromkeys((conf, cache)):  # the same folder only once
        drop_marker(folder)
    out("Your snapshot file in the game's WTF folder is the game's; delete ForeverBridge.lua there by hand if "
        'you want it gone.')
    return 0


def run(args, env=None, out=print, ask=None):
    env = os.environ if env is None else env
    ask = ask or input
    cfg = paths.load_config(env)
    cmd = 'python forever'
    game, how = paths.find_game(getattr(args, 'game', None), env, cfg)
    if getattr(args, 'uninstall', False):
        return uninstall(args, env, out, game, how, ask)
    out(PRODUCT + ': setup')
    if game:
        out('game folder: %s (%s)' % (paths.show(game), how))
    else:
        out('game folder: %s' % how)
        game = ask_for_game(ask, out) if sys.stdin and sys.stdin.isatty() else None
        if not game:
            out('Run again with the folder:  %s setup --game "<folder that holds _forever_>"' % cmd)
            return 2
    if not flavour_ok(game, args, out, ask):
        return 2
    if not links_ok(game, args, out, ask, 'Install'):
        return 2
    conf = paths.config_dir(env)
    cache = getattr(args, 'cache', None) or paths.cache_dir(env)
    try:
        # both folders must pass the gate before anything is written; they are marked only once the add-on is in
        paths.check_free(conf, paths.CONFIG_NAMES)
        paths.check_free(cache, paths.CACHE_NAMES)
    except paths.NotOurs as e:
        out(str(e))
        return 2
    try:
        dest = install_addon(game)
    except Refused as e:
        out(str(e))
        return 2
    except OSError as e:
        out('The add-on could not be written (%s).' % paths.describe(e, env))
        return 2
    try:
        paths.claim(conf, paths.CONFIG_NAMES)
        paths.claim(cache, paths.CACHE_NAMES)
    except paths.NotOurs as e:
        out(str(e))
        return 2
    except OSError as e:
        out('The config or cache folder cannot be written (%s).' % paths.describe(e, env))
        return 2
    out('add-on: %s (ForeverBridge.toc, ForeverBridge.lua)' % paths.show(dest))
    cfg['game'] = game
    saved = paths.save_config(cfg, env)
    note = write_launcher_note(conf)
    out('config: %s' % paths.show(saved))
    out('launcher note for the Claude plugin: %s' % paths.show(note))
    out('cache: %s' % paths.show(cache))
    rc = 0
    if getattr(args, 'no_download', False):
        out('data: not downloaded now (run  %s update  later)' % cmd)
    else:
        out('downloading the data (about 15 files, 12 MB; at most 2 requests a second; safe to stop and run again):')
        http = net.Http(offline=True) if getattr(args, 'offline', False) else None
        store = Store(cache=cache, game=game, out=out, http=http)
        try:
            rc = store.update()
        except OSError as e:  # whatever the network or the disk did, the player still gets the next steps
            out('data: the download stopped (%s)' % paths.describe(e, env))
            rc = 2
        finally:
            store.close()
        if rc == 2:
            out('data: not downloaded yet, run  %s update  when you are online' % cmd)
        elif rc == 1:
            out('data: not all downloaded yet, run  %s update  when you are online' % cmd)
    next_steps(out, cmd)
    return 2 if rc == 2 else 0
