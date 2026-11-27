"""The `forever` command line. Plain text out, so that a person and Claude read the same answer.

  forever setup [--uninstall [--purge]] [--no-download]
  forever me [gear|stats|skills|recipes|trainer|vendor|rep|quests|bags|missing|xp|talents|json|status] [words]
  forever price "Item one, Item two"
  forever item <name or id> [--list]
  forever quest <name or id>
  forever where <creature | vendor title | zone | item sold by vendors>
  forever update [--check] [--force]
  forever version
Every command takes --game DIR (the _forever_ folder), --cache DIR, --offline and --side horde|alliance.
"""
import argparse
import os
import sys
import traceback

from . import CREDITS, PRODUCT, VERSION, installer, net, paths, prices, snapshot
from .data import Store
from .lookup import Lookup


def add_common(p, top):
    def d(v):
        return v if top else argparse.SUPPRESS
    p.add_argument('--game', default=d(None), metavar='DIR',
                   help='the _forever_ game folder (or the folder holding it)')
    p.add_argument('--cache', default=d(None), metavar='DIR', help='where downloaded data is kept')
    p.add_argument('--offline', action='store_true', default=d(False), help='make no network requests')
    p.add_argument('--side', default=d(None), choices=['horde', 'alliance'], help='your faction, for lists of NPCs')


def parser():
    ap = argparse.ArgumentParser(
        prog='forever', description=PRODUCT + ": your WoW Forever character and Forever's own data, as plain text.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split('\n', 1)[1])
    add_common(ap, True)
    sub = ap.add_subparsers(dest='command', metavar='command')

    p = sub.add_parser('setup', help='install the add-on, download the data, print the next steps')
    p.add_argument('--uninstall', action='store_true', help='remove the add-on and the config')
    p.add_argument('--purge', action='store_true', help='with --uninstall: also remove the downloaded data')
    p.add_argument('--no-download', action='store_true', help='do not download the data now')
    p.add_argument('--force', action='store_true', help='install into a game folder not named _forever_')
    add_common(p, False)

    p = sub.add_parser('me', help='your character, from the ForeverBridge snapshot (no network)')
    p.add_argument('sub', nargs='?', default='summary', choices=snapshot.COMMANDS, metavar='part',
                   help=' | '.join(snapshot.COMMANDS[1:]))
    p.add_argument('words', nargs='*', help='words to filter by (a quest name for `me quests`)')
    p.add_argument('--char', help='a character name (default: the newest snapshot)')
    p.add_argument('--file', help='read this saved-variables file')
    p.add_argument('--cap', type=int, default=29, help='the level cap for `me xp` (default 29)')
    p.add_argument('--all', action='store_true', help='`me json --all`: everything in the file')
    p.add_argument('--want', help='`me missing --want "A, B"`: the items you want')
    add_common(p, False)

    p = sub.add_parser('price', help='auction prices from your own Auctionator scans (no network)')
    p.add_argument('words', nargs='+')
    add_common(p, False)

    p = sub.add_parser('item', help="an item: Forever's numbers and where it comes from")
    p.add_argument('words', nargs='+')
    p.add_argument('--list', action='store_true', help='only list the matches')
    add_common(p, False)

    p = sub.add_parser('quest', help='a quest: level, who gives it, where, experience')
    p.add_argument('words', nargs='+')
    add_common(p, False)

    p = sub.add_parser('where', help='where a creature, a kind of vendor, or a zone\'s services are')
    p.add_argument('words', nargs='+')
    add_common(p, False)

    p = sub.add_parser('update', help="download or refresh Forever's data")
    p.add_argument('--check', action='store_true', help='only say whether the data is current (no network)')
    p.add_argument('--force', action='store_true', help='download everything again')
    add_common(p, False)

    p = sub.add_parser('version', help='version, data and credits')
    add_common(p, False)
    return ap


def resolve_game(args, env):
    game, how = paths.find_game(args.game, env)
    return game, how


def faction_side(game, args):
    """--side, else the faction of your newest snapshot (read locally), else none."""
    if args.side:
        return args.side
    try:
        if not game:
            return None
        db, _ = snapshot.load(game, None)
        _, c = snapshot.pick(db)
        return (c.get('faction') or '').lower() or None
    except (snapshot.NoSnapshot, OSError, ValueError):
        return None


def cmd_version(args, env, out):
    game, how = resolve_game(args, env)
    store = Store(cache=args.cache or paths.cache_dir(env), game=game, http=net.Http(offline=True), out=out)
    out('%s %s (Python %s)' % (PRODUCT, VERSION, sys.version.split()[0]))
    out('game folder: %s' % (paths.show(game, env) if game else how))
    out('cache: %s' % paths.show(store.cache, env))
    out('config: %s' % paths.show(paths.config_dir(env), env))
    out(store.data_line())
    store.close()
    out('Credits:')
    for c in CREDITS:
        out('  ' + c)
    out('Claude runs in your own Claude Code, signed in with your own account: this tool never sees that login.')
    return 0


def main(argv=None, env=None, out=None):
    env = os.environ if env is None else env
    if out is None:
        try:
            if sys.stdout.isatty():
                sys.stdout.reconfigure(errors='replace')
            else:
                # piped (to Claude Code, a file): UTF-8, whatever the console's own code page is
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass

        def out(line=''):
            print(line, flush=True)
    args = parser().parse_args(argv)
    if not args.command:
        parser().print_help()
        return 2
    store = None
    try:
        if args.command == 'setup':
            return installer.run(args, env=env, out=out)
        if args.command == 'version':
            return cmd_version(args, env, out)
        game, how = resolve_game(args, env)
        if args.command in ('me', 'price'):
            # your own files only: these never touch the network
            store = Store(cache=args.cache or paths.cache_dir(env), game=game, http=net.Http(offline=True), out=out)
            if not game and not getattr(args, 'file', None):
                out('Game folder: %s. Run  forever setup  or pass --game DIR.' % how)
                return 2
            if args.command == 'me':
                return snapshot.run(store, game, args, out=out, config_dir=paths.config_dir(env))
            return prices.run(store, game, args.words, out=out)
        store = Store(cache=args.cache or paths.cache_dir(env), game=game,
                      http=net.Http(offline=args.offline or None), out=out)
        if args.command == 'update':
            if args.check:
                rc, line = store.check()
                out(line)
                return rc
            return store.update(force=args.force)
        look = Lookup(store, out=out, fetch=not args.offline, side=faction_side(game, args))
        return getattr(look, args.command)(args.words, **({'list_only': args.list} if args.command == 'item' else {}))
    except KeyboardInterrupt:
        out('stopped (what was downloaded so far is kept: run the same command again to go on)')
        return 130
    except Exception as e:  # a friendly line for the player, the details only when asked for
        out('forever: something went wrong: %s: %s' % (type(e).__name__, paths.describe(e, env)))
        if env.get('FOREVER_DEBUG'):
            traceback.print_exc()
        else:
            out('(run again with FOREVER_DEBUG=1 for the details)')
        return 1
    finally:
        if store is not None:
            store.close()
