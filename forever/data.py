"""The data in the user's cache: download it (politely), build the database, say how old it is.

Layout of the cache folder:
  raw/wago/<build>/<Table>.csv     the game client's tables for that build (wago.tools)
  raw/foreverdb/<file>.lua         ForeverDB.net's add-on data files, unmodified, checked against their manifest
  tips/<item|quest|npc>/<id>.json  Wowhead's Forever tooltips, fetched one at a time when a lookup needs one
  forever.db, stamp.json           the database built from the above, and what it was built from
"""
import glob
import json
import os
import pathlib
import re
import sqlite3
import time
import urllib.error
import urllib.parse

from . import CREDITS, build, net, paths
from .text import ago

WAGO = 'https://wago.tools'
FDB = 'https://foreverdb.net'
TOOLTIP = 'https://nether.wowhead.com/forever/tooltip/%s/%d'
STALE_DAYS = 7  # ForeverDB updates its files several times a day; a week-old copy is worth refreshing
# 1.60.1.71139: a build number becomes a folder name, so nothing else passes (ASCII digits only)
BUILD = re.compile(r'[0-9]+(\.[0-9]+){2,3}')
SHA256 = re.compile(r'[0-9a-f]{64}')
MAX_CAP = 256 << 20  # however large a size the manifest names, no file is taken beyond this


def valid_build(build_id):
    return isinstance(build_id, str) and bool(BUILD.fullmatch(build_id))


def parse_manifest(raw):
    """(version, {file name: entry}) from ForeverDB's manifest, or ValueError when it is not shaped as expected."""
    try:
        man = json.loads(raw.decode('utf-8', 'replace'))
    except ValueError:
        raise ValueError("ForeverDB's manifest is not JSON")
    data = man.get('data') if isinstance(man, dict) else None
    files = data.get('files') if isinstance(data, dict) else None
    if not isinstance(files, list):
        raise ValueError("ForeverDB's manifest has an unexpected shape")
    out = {}
    for f in files:
        if not (isinstance(f, dict) and isinstance(f.get('path'), str) and isinstance(f.get('url'), str)):
            raise ValueError("ForeverDB's manifest has an entry of an unexpected shape")
        out[f['path'].split('/')[-1]] = f
    version = data.get('version')
    return (version if isinstance(version, str) else None), out


class Store:
    def __init__(self, cache=None, game=None, http=None, out=print):
        self.cache = cache or paths.cache_dir()
        self.game = game
        self.http = http or net.Http()
        self.out = out
        self._db = None

    # ---- places ---------------------------------------------------------------------------------------------
    def p(self, *parts):
        return os.path.join(self.cache, *parts)

    @property
    def db_path(self):
        return self.p('forever.db')

    def stamp(self):
        try:
            with open(self.p('stamp.json'), encoding='utf-8') as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def db(self):
        """A read-only connection to forever.db, or None when there is no data yet."""
        if self._db is None and os.path.exists(self.db_path):
            # a file: URI built by pathlib, so that '#', '%', spaces or a Windows drive in the folder are safe
            uri = pathlib.Path(self.db_path).resolve().as_uri() + '?mode=ro'
            self._db = sqlite3.connect(uri, uri=True)
        return self._db

    def close(self):
        if self._db is not None:
            self._db.close()
            self._db = None

    def q(self, sql, args=()):
        con = self.db()
        if con is None:
            return []
        try:
            return con.execute(sql, args).fetchall()
        except sqlite3.Error:
            return []

    def installed_build(self):
        """The game's build from its .build.info, when it is a build number (anything else is not used)."""
        found = paths.build_info(self.game)
        return found if valid_build(found) else None

    def quest_cache_path(self):
        if not self.game:
            return None
        found = glob.glob(os.path.join(glob.escape(self.game), 'Cache', 'WDB', '*', 'questcache.wdb'))
        return max(found, key=os.path.getmtime) if found else None

    # ---- what the data is and how old ----------------------------------------------------------------------
    def data_line(self):
        st = self.stamp()
        if not st:
            return 'data: none yet (run: forever update)'
        return ('data: ForeverDB.net %s, downloaded %s; game tables %s (wago.tools). Data from ForeverDB.net '
                '(https://foreverdb.net)' % (st.get('foreverdb') or '?', ago(st.get('updated')),
                                            st.get('build') or '?'))

    def check(self):
        """(exit code, one line): 0 current, 1 something is stale, 2 cannot tell (no data yet)."""
        st = self.stamp()
        if not st or not os.path.exists(self.db_path):
            return 2, 'no data yet: run  forever update'
        want = self.installed_build()
        problems = []
        if want and st.get('build') != want:
            problems.append('the game is %s, the tables are for %s' % (want, st.get('build')))
        age_days = (time.time() - float(st.get('updated') or 0)) / 86400
        if age_days > STALE_DAYS:
            problems.append('the ForeverDB copy is %d days old' % age_days)
        wdb = self.quest_cache_path()
        note = ''
        if wdb and os.path.getmtime(wdb) > float(st.get('updated') or 0):
            note = '; your game has cached quests since (forever update reads them)'
        head = 'game %s: ' % (want or 'build unknown')
        if problems:
            return 1, head + 'stale: ' + '; '.join(problems) + note
        return 0, head + 'data current (%s)' % self.data_line() + note

    # ---- downloading ----------------------------------------------------------------------------------------
    def latest_build(self):
        data = json.loads(self.http.get(WAGO + '/api/builds', timeout=60).decode('utf-8', 'replace'))
        rows = data.get('wowf') if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            raise ValueError('wago.tools lists no WoW Forever build')
        version = rows[0].get('version') if isinstance(rows[0], dict) else None
        if not valid_build(version):
            raise ValueError('wago.tools gave no usable build number')
        return version

    def _download_wago(self, build_id, force):
        """(folder, files got, failures, why the network failed or None). A connection that fails (refused, timed
        out, reset) stops the rest of the tables: the network is down, and what is cached is used instead."""
        if not valid_build(build_id):
            raise ValueError('not a build number')
        folder = self.p('raw', 'wago', build_id)
        got, failed, down = 0, [], None
        for n, table in enumerate(build.WAGO_TABLES, 1):
            dest = os.path.join(folder, table + '.csv')
            if os.path.exists(dest) and not force:
                continue
            if os.path.exists(dest + '.part'):
                # a game table has no published checksum: an old part could belong to another version of the
                # file, so it is never continued; the table is fetched again from the start
                os.remove(dest + '.part')
            url = '%s/db2/%s/csv?build=%s' % (WAGO, table, urllib.parse.quote(build_id, safe='.'))
            self.out('  game table %d/%d: %s' % (n, len(build.WAGO_TABLES), table))
            try:
                self.http.download(url, dest, progress=net.progress_printer(table))
            except urllib.error.HTTPError as e:
                e.close()
                failed.append('%s (HTTP %s)' % (table, e.code))
                continue
            except ValueError as e:  # refused, too large, an address that cannot be sent
                failed.append('%s (%s)' % (table, e))
                continue
            except (urllib.error.URLError, OSError) as e:
                down = getattr(e, 'reason', None) or e
                break
            with open(dest, 'rb') as fh:
                head = fh.read(400)
            if b'ID' not in head or b',' not in head:
                os.replace(dest, dest + '.bad')
                failed.append('%s (not a table)' % table)
                continue
            got += 1
        return folder, got, failed, down

    def _download_foreverdb(self, force):
        folder = self.p('raw', 'foreverdb')
        os.makedirs(folder, exist_ok=True)
        raw = self.http.get(FDB + '/downloads/addon-manifest.json', timeout=60)
        version, files = parse_manifest(raw)
        got, failed = 0, []
        for n, name in enumerate(build.FDB_FILES, 1):
            f = files.get(name)
            if not f:
                failed.append('%s (not in the manifest)' % name)
                continue
            sha = f.get('sha256')
            sha = sha.strip().lower() if isinstance(sha, str) else None
            if not (sha and SHA256.fullmatch(sha)):
                # every file is checked against its published checksum, or it is not taken at all
                failed.append('%s (no valid checksum in the manifest: not downloaded)' % name)
                continue
            dest = os.path.join(folder, name)
            if not force and os.path.exists(dest) and net.file_sha256(dest) == sha:
                continue
            raw_size = f.get('bytes')  # the real manifest gives a number; a digit string is accepted too
            if isinstance(raw_size, bool):
                size = 0
            elif isinstance(raw_size, int):
                size = max(0, raw_size)
            elif isinstance(raw_size, str) and raw_size.strip().isdigit() and raw_size.strip().isascii():
                size = int(raw_size.strip())
            else:
                size = 0
            shown = '%d KB' % (size // 1024) if size <= MAX_CAP else 'more than %d MB' % (MAX_CAP >> 20)
            self.out('  ForeverDB file %d/%d: %s (%s)' % (n, len(build.FDB_FILES), name, shown))
            try:
                # the published size plus a margin, never under the usual cap and never over the ceiling
                cap = min(MAX_CAP, max(net.MAX_DOWNLOAD, size + (1 << 20)))
                self.http.download(FDB + '/' + f['url'].lstrip('/'), dest, sha256=sha,
                                   progress=net.progress_printer(name), max_bytes=cap)
                got += 1
            except urllib.error.HTTPError as e:
                e.close()
                failed.append('%s (HTTP %s)' % (name, e.code))
            except ValueError as e:  # a checksum that does not match, a refused redirect, a file too large
                failed.append('%s (%s)' % (name, paths.mask(e)))
        tmp = os.path.join(folder, 'manifest.json.tmp')
        with open(tmp, 'wb') as fh:
            fh.write(raw)
        os.replace(tmp, os.path.join(folder, 'manifest.json'))
        return folder, version, got, failed

    def update(self, force=False):
        """Download what is missing or changed, then build the database. Returns an exit code."""
        try:
            paths.claim(self.cache, paths.CACHE_NAMES)
        except paths.NotOurs as e:
            self.out(str(e))
            return 2
        except OSError as e:
            self.out('The cache folder %s cannot be written (%s). Point FOREVER_CACHE_DIR at a folder you can write.'
                     % (paths.show(self.cache), paths.describe(e)))
            return 2
        st = self.stamp()
        build_id = self.installed_build()
        if build_id:
            self.out('game: WoW Forever %s (from your game folder)' % build_id)
        else:
            if self.game and paths.build_info(self.game):
                self.out("note: the game's build file names no usable build number; asking wago.tools instead")
            try:
                build_id = self.latest_build()
                self.out('game: WoW Forever %s (the newest build wago.tools lists; no game folder to read)' % build_id)
            except (OSError, ValueError, RuntimeError, net.Offline) as e:
                build_id = st.get('build') if valid_build(st.get('build')) else None
                if not build_id:
                    self.out('Cannot tell which game build to download for (%s). Point me at the game with --game.' % e)
                    return 2
                self.out('game: %s (kept from the last update; wago.tools did not answer)' % build_id)
        problems = []
        try:
            wago_dir, got, failed, down = self._download_wago(build_id, force)
            problems += ['game table ' + f for f in failed]
            if down is not None:
                problems.append('game tables not downloaded: %s' % paths.describe(down))
        except net.Offline as e:
            wago_dir = self.p('raw', 'wago', build_id)
            problems.append(str(e))
        if not os.path.exists(os.path.join(wago_dir, 'ItemSparse.csv')):
            older = sorted(glob.glob(os.path.join(glob.escape(self.cache), 'raw', 'wago', '*', 'ItemSparse.csv')),
                           key=os.path.getmtime)
            if older:
                wago_dir = os.path.dirname(older[-1])
                problems.append('using the game tables of %s until %s can be downloaded' %
                                (os.path.basename(wago_dir), build_id))
        try:
            fdb_dir, fdb_version, got, failed = self._download_foreverdb(force)
            problems += ['ForeverDB ' + f for f in failed]
        except (OSError, ValueError, net.Offline) as e:
            fdb_dir, fdb_version = self.p('raw', 'foreverdb'), st.get('foreverdb')
            problems.append('ForeverDB not refreshed (%s); the copy from %s stays' % (paths.describe(e),
                                                                                     fdb_version or 'nowhere'))
        if not os.path.exists(os.path.join(fdb_dir, 'QuestForever.lua')) and \
                not os.path.exists(os.path.join(wago_dir, 'ItemSparse.csv')):
            for p in problems:
                self.out('  ' + p)
            self.out('No data could be downloaded. Check the connection and run  forever update  again '
                     '(what was already downloaded is kept).')
            return 2
        self.out('building the database ...')
        self.close()  # the file is about to be replaced
        wdb = self.quest_cache_path()
        if wdb and not os.access(wdb, os.R_OK):
            # optional: without it the levels come from ForeverDB; "cannot be written" is kept for write errors
            problems.append(build.QUEST_CACHE_UNREADABLE)
            wdb = None
        try:
            summary = build.build(wago_dir, fdb_dir, self.db_path, wdb,
                                  meta={'build': os.path.basename(wago_dir), 'foreverdb_manifest': fdb_version or ''})
        except (OSError, sqlite3.Error) as e:
            for p in problems:
                self.out('  note: ' + p)
            self.out('The database in %s cannot be written (%s). Check that the folder can be written, then run  '
                     'forever update  again.' % (paths.show(self.cache), paths.describe(e)))
            return 2
        self.close()
        problems += summary.pop('notes', [])  # one that passed the check and still could not be opened
        stamp = {'build': os.path.basename(wago_dir), 'updated': int(time.time()), 'foreverdb': fdb_version,
                 'counts': {k: v for k, v in summary.items() if k != 'missing'}, 'missing': summary['missing'],
                 'problems': problems}
        tmp = self.p('stamp.json.tmp')
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(stamp, fh, indent=1)
        os.replace(tmp, self.p('stamp.json'))
        self.out('done: ' + ', '.join('%s %s' % (v, k) for k, v in stamp['counts'].items()))
        for p in problems + ['missing: ' + m for m in summary['missing']]:
            self.out('  note: ' + p)
        self.out(self.data_line())
        self.out(CREDITS[0])
        return 1 if summary['missing'] else 0

    # ---- tooltips, one at a time, when a lookup needs one ---------------------------------------------------
    def tooltip(self, kind, ident, fetch=True):
        """Wowhead's Forever tooltip (dict) for an item, quest or npc, cached; None when not available."""
        path = self.p('tips', kind, '%d.json' % int(ident))
        try:
            with open(path, encoding='utf-8') as fh:
                return json.load(fh)
        except (OSError, ValueError):
            pass
        if not fetch:
            return None
        try:
            # one try: a lookup should not wait for retries on a dead connection
            data = json.loads(self.http.get(TOOLTIP % (kind, int(ident)), timeout=20, tries=1)
                              .decode('utf-8', 'replace'))
        except urllib.error.HTTPError as e:
            e.close()
            data = {'error': e.code} if e.code in (404, 410) else None
        except (OSError, ValueError, net.Offline):
            data = None
        if data is None or not isinstance(data, dict):
            return None
        try:
            paths.claim(self.cache, paths.CACHE_NAMES)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(data, fh)
            os.replace(tmp, path)
        except (paths.NotOurs, OSError):
            pass  # answered, just not kept: someone else's cache folder, a read-only one, a full disk
        return data
