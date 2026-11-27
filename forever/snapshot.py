"""`forever me`: what the game itself says about YOUR character, read from the ForeverBridge add-on's file.

The game writes WTF/Account/<account>/SavedVariables/ForeverBridge.lua on /reload and on logout (`/fbridge save` in
the game does both). The file is parsed as data, never run, and nothing is sent anywhere: these commands make no
network requests at all.
"""
import glob
import json
import os

from . import luatable as lt
from . import paths
from .luatable import D, L
from .text import ago, money, num

NEW_FILE, NEW_VAR = 'ForeverBridge.lua', 'ForeverBridgeDB'
DIFF = {0: 'orange', 1: 'yellow', 2: 'green', 3: 'grey'}
STANDING = {1: 'Hated', 2: 'Hostile', 3: 'Unfriendly', 4: 'Neutral', 5: 'Friendly', 6: 'Honored', 7: 'Revered',
            8: 'Exalted'}
WORN_SLOTS = ('Head', 'Neck', 'Shoulder', 'Back', 'Chest', 'Wrist', 'Hands', 'Waist', 'Legs', 'Feet', 'Finger1',
              'Finger2', 'Trinket1', 'Trinket2', 'MainHand', 'Ranged')
STATS = {'ITEM_MOD_STRENGTH_SHORT': 'Str', 'ITEM_MOD_AGILITY_SHORT': 'Agi', 'ITEM_MOD_STAMINA_SHORT': 'Sta',
         'ITEM_MOD_INTELLECT_SHORT': 'Int', 'ITEM_MOD_SPIRIT_SHORT': 'Spi', 'ITEM_MOD_ATTACK_POWER_SHORT': 'AP',
         'ITEM_MOD_RANGED_ATTACK_POWER_SHORT': 'RAP', 'ITEM_MOD_CRIT_RATING_SHORT': 'crit',
         'ITEM_MOD_HIT_RATING_SHORT': 'hit', 'RESISTANCE0_NAME': 'armor'}

# Experience from one level to the next, from the Classic table (Classic data): only levels 20 to 30, the ones a
# low-level twink plans with. Every level your own snapshots show is remembered and replaces these numbers.
CLASSIC = 'Classic data'
CLASSIC_XP = {20: 23200, 21: 25200, 22: 27300, 23: 29400, 24: 31700, 25: 34000, 26: 36400, 27: 38900, 28: 41400,
              29: 44300, 30: 47400}


class NoSnapshot(Exception):
    pass


# ---- finding and reading the file ---------------------------------------------------------------------------

def snapshot_files(game):
    """Every ForeverBridge.lua of the game folder's accounts, the newest first. No other add-on's file is opened."""
    if not game:
        return []
    base = os.path.join(glob.escape(game), 'WTF', 'Account', '*', 'SavedVariables')
    return sorted(glob.glob(os.path.join(base, NEW_FILE)), key=os.path.getmtime, reverse=True)


def read_db(path):
    """The add-on's table (ForeverBridgeDB) from a saved-variables file, or None."""
    if os.path.getsize(path) > 64 * 1024 * 1024:
        return None
    with open(path, 'rb') as fh:
        text = fh.read().decode('utf-8', errors='replace')
    db = lt.parse(text).get(NEW_VAR)
    if isinstance(db, dict) and isinstance(db.get('chars'), dict) and 'schema' in db:
        return db
    return None


def read_or_say(path):
    """read_db, with a line for the player when the file cannot be read (a lock while the game writes it, a folder
    of that name, missing rights)."""
    try:
        return read_db(path)
    except OSError as e:
        raise NoSnapshot('Cannot read the snapshot file (%s). If the game is writing it right now, try again in a '
                         'moment.' % paths.describe(e))


def load(game, file=None):
    """(db, path) of the newest snapshot. Raises NoSnapshot with a message for the player."""
    if file:
        if not os.path.exists(file):
            raise NoSnapshot('No such file: %s' % paths.show(file))
        db = read_or_say(file)
        if db is None:
            raise NoSnapshot('%s holds no ForeverBridge snapshot.' % paths.show(file))
        return db, file
    for path in snapshot_files(game):
        db = read_or_say(path)
        if db is not None and D(db.get('chars')):
            return db, path
    installed = bool(game) and os.path.isdir(os.path.join(game, 'Interface', 'AddOns', 'ForeverBridge'))
    if not game:
        raise NoSnapshot('No game folder known yet: run  forever setup  (or pass --game DIR).')
    if installed:
        raise NoSnapshot('No snapshot yet. The ForeverBridge add-on is installed: start the game (a full restart '
                         'after installing), log in and type /fbridge save (or log out once).')
    raise NoSnapshot('No snapshot yet, and the ForeverBridge add-on is not installed in %s. Run  forever setup .'
                     % paths.show(os.path.join(game, 'Interface', 'AddOns')))


def pick(db, name=None):
    chars = D(db.get('chars'))
    if not chars:
        raise NoSnapshot('The file holds no character yet. Log in with the add-on enabled and type /fbridge save.')
    if name:
        hits = [k for k in chars if str(k).lower().startswith(name.lower())]
        if not hits:
            raise NoSnapshot('No character called %r in the snapshot. Known: %s' % (name, ', '.join(sorted(chars))))
        key = hits[0]
    else:
        key = max(chars, key=lambda k: D(chars[k]).get('saved') or 0)
    return key, D(chars[key])


# ---- the commands ---------------------------------------------------------------------------------------------

class Me:
    def __init__(self, store, db, path, key, char, out=print, config_dir=None):
        self.store, self.db, self.path, self.key, self.c = store, db, path, key, char
        self.out = out
        self.config_dir = config_dir or paths.config_dir()

    # names from the downloaded data (the snapshot's own names win)
    def item_name(self, i):
        r = self.store.q('SELECT name FROM item WHERE id=?', (int(i),)) if str(i).lstrip('-').isdigit() else []
        return r[0][0] if r and r[0][0] else 'item %s' % i

    def enchant_name(self, e):
        r = self.store.q('SELECT name FROM enchant WHERE id=?', (int(e),))
        return r[0][0] if r and r[0][0] else None

    def spell_name(self, s):
        r = self.store.q('SELECT name FROM spell WHERE id=?', (int(s),))
        return r[0][0] if r and r[0][0] else 'spell %s' % s

    def who(self):
        c = self.c
        return (c.get('name') or str(self.key)) + ('-' + c['realm'] if c.get('realm') else '')

    def head(self):
        c = self.c
        return '%s · level %s %s %s (%s) · snapshot %s' % (
            self.who(), c.get('level', '?'), c.get('race', '?'), c.get('classLocal') or c.get('class') or '?',
            c.get('faction', '?'), ago(c.get('saved')))

    def source(self):
        """The line every answer ends with: where this came from and how old it is."""
        return 'from: your snapshot %s, written %s (character saved %s, %s)' % (
            os.path.basename(self.path), ago(os.path.getmtime(self.path)), ago(self.c.get('saved')),
            self.c.get('reason') or '?')

    def words(self, args):
        return ' '.join(getattr(args, 'words', None) or []).strip()

    # ---- summary and the character sheet ----
    def summary(self, args):
        c = self.c
        self.out(self.head())
        if c.get('xpMax'):
            rested = ' · rested %s' % num(c['rested']) if c.get('rested') else ''
            self.out('XP %s / %s (%d%%)%s · %s' % (num(c.get('xp') or 0), num(c['xpMax']),
                                                  100 * (c.get('xp') or 0) / c['xpMax'], rested, money(c.get('money'))))
        else:
            self.out('XP and gold: not in this snapshot (see  forever me status)')
        pos = D(c.get('position'))
        if pos.get('zone'):
            self.out('Where: %s%s%s' % (pos['zone'], ', ' + pos['sub'] if pos.get('sub') else '',
                                       ' (%s, %s)' % (pos['x'], pos['y']) if pos.get('x') is not None else ''))
        profs = self.professions()
        if profs:
            self.out('Skills: ' + ', '.join(profs))
        eq = L(c.get('equipped'))
        worn = {e.get('slot') for e in eq}
        empty = [s for s in WORN_SLOTS if s not in worn]
        if eq:
            self.out('Gear: %d pieces worn%s' % (len(eq), '; empty: ' + ', '.join(empty) if empty else ''))
        else:
            self.out('Gear: none recorded in this snapshot (see  forever me status)')
        st = D(c.get('stats'))
        if st and st.get('stamina'):
            self.out('Agility %s · Stamina %s · attack power %s · ranged attack power %s' % (
                st.get('agility'), st.get('stamina'), st.get('attackPower'), st.get('rangedAttackPower')))
        self.out('More: forever me gear | stats | skills | quests | xp | missing | status')
        self.out(self.source())

    def professions(self):
        sk = D(self.c.get('skills'))
        profs = ['%s %s/%s' % (p.get('name'), p.get('rank'), p.get('max')) for p in L(sk.get('professions'))]
        if not profs:
            profs = ['%s %s/%s' % (s.get('name'), s.get('rank'), s.get('max')) for s in L(sk.get('lines'))
                     if s.get('group') in ('Professions', 'Secondary Skills')]
        return profs

    def stat_text(self, stats):
        out, armor = [], None
        for k, v in sorted(D(stats).items()):
            name = STATS.get(k) or str(k).replace('ITEM_MOD_', '').replace('_SHORT', '').replace('_', ' ').lower()
            if name == 'armor':
                armor = v
            else:
                out.append('+%s %s' % (int(v) if float(v) == int(v) else v, name))
        return ' '.join(out) + (' · %s armor' % armor if armor else '')

    def gear(self, args):
        self.out(self.head())
        eq = L(self.c.get('equipped'))
        if not eq:
            self.out('No gear in this snapshot. In the game type /fbridge save '
                     '(it reloads the UI and writes the file).')
        for e in eq:
            bits = []
            if e.get('ilvl'):
                bits.append('ilvl %s' % e['ilvl'])
            if e.get('enchant'):
                bits.append(self.enchant_name(e['enchant']) or 'enchant %s' % e['enchant'])
            if e.get('dur') is not None and e.get('durMax'):
                bits.append('durability %d%%' % (100 * e['dur'] / e['durMax']))
            stats = ('  ' + self.stat_text(e['stats'])) if e.get('stats') else ''
            self.out('%-9s %s%s%s' % (e.get('slot'), e.get('name') or self.item_name(e.get('id')),
                                      ('  (' + ', '.join(bits) + ')') if bits else '', stats))
        self.out(self.source())

    def stats(self, args):
        st = D(self.c.get('stats'))
        self.out(self.head())
        if not st.get('stamina'):
            self.out('No stats in this snapshot (a logout snapshot can come out zero): /fbridge save in the game.')
            self.out(self.source())
            return
        for k in ('strength', 'agility', 'stamina', 'intellect', 'spirit', 'armor', 'attackPower',
                  'rangedAttackPower', 'health', 'mana'):
            if st.get(k) is not None:
                self.out('%-18s %s' % (k, st[k]))
        for k in ('meleeCrit', 'rangedCrit', 'dodge', 'parry', 'block'):
            if isinstance(st.get(k), (int, float)):
                self.out('%-18s %.2f%%' % (k, st[k]))
        r = D(st.get('ranged'))
        if r.get('speed'):
            lo, hi = r.get('min', 0) or 0, r.get('max', 0) or 0
            self.out('ranged weapon      %s-%s, speed %.2f, about %.1f damage per second' % (
                round(lo), round(hi), r['speed'], ((lo + hi) / 2) / r['speed']))
        self.out(self.source())

    def skills(self, args):
        sk = D(self.c.get('skills'))
        self.out(self.head())
        for p in L(sk.get('professions')):
            self.out('profession  %-18s %s / %s' % (p.get('name'), p.get('rank'), p.get('max')))
        group = None
        for s in L(sk.get('lines')):
            if s.get('group') != group:
                group = s.get('group')
                self.out('[%s]' % group)
            self.out('  %-24s %s / %s%s' % (s.get('name'), s.get('rank'), s.get('max'),
                                           ' (+%s)' % s['plus'] if s.get('plus') else ''))
        self.out(self.source())

    # ---- windows the player opened: recipes, trainers, vendors ----
    def recipes(self, args):
        ts = D(self.c.get('tradeskills'))
        words = self.words(args).lower()
        if not ts:
            self.out('No recipe list yet: open a profession window in the game once, then /fbridge save.')
        for prof, data in ts.items():
            data = D(data)
            recipes = L(data.get('recipes'))
            if words and words not in str(prof).lower() and not any(words in (r.get('name') or '').lower()
                                                                    for r in recipes):
                continue
            learned = [r for r in recipes if r.get('learned')]
            self.out('%s %s/%s · seen %s · %d known, %d not known' % (
                prof, data.get('rank'), data.get('max'), ago(data.get('saved')), len(learned),
                len(recipes) - len(learned)))
            by = {}
            for r in learned:
                by.setdefault(r.get('diff', 3), []).append(r)
            for d in (0, 1, 2, 3):
                rows = [r for r in by.get(d) or [] if not words or words in (r.get('name') or '').lower()
                        or words in str(prof).lower()]
                if not rows or (d == 3 and not words):
                    continue
                self.out('  %s (%d)' % (DIFF[d], len(rows)))
                for r in rows[:25]:
                    mats = ', '.join('%s %s' % (z[1], self.item_name(z[0])) for z in map(L, L(r.get('reagents')))
                                     if len(z) > 1)
                    self.out('    %-32s %s' % (r.get('name'), mats))
            if words:
                for r in recipes:
                    if not r.get('learned') and words in (r.get('name') or '').lower():
                        self.out('  not known: %s  %s' % (r.get('name'), r.get('src') or ''))
        self.out("(the colours are the game's own at your skill)")
        self.out(self.source())

    def trainer(self, args):
        trainers = D(self.db.get('trainers'))
        words = self.words(args).lower()
        if not trainers:
            self.out('No trainer seen yet: open a trainer window in the game once, then /fbridge save.')
        for t in trainers.values():
            t = D(t)
            services = [s for s in L(t.get('services')) if not words or words in (s.get('name') or '').lower()
                        or words in (t.get('name') or '').lower()]
            if not services:
                continue
            spot = ' (%s, %s)' % (t.get('x'), t.get('y')) if t.get('x') is not None else ''
            where = '%s%s' % (t.get('zone') or '', spot)
            self.out('%s · %s · seen %s' % (t.get('name'), where, ago(t.get('saved'))))
            for s in services:
                req = 'needs %s %s' % (s.get('reqSkill'), s.get('reqRank')) if s.get('reqSkill') else ''
                lvl = ' level %s' % s['reqLevel'] if s.get('reqLevel') else ''
                self.out('  %-32s %s%s  price %s' % (s.get('name'), req, lvl, money(s.get('cost'))))
        self.out(self.source())

    def vendor(self, args):
        vendors = D(self.db.get('vendors'))
        words = self.words(args).lower()
        rows = []
        for v in vendors.values():
            v = D(v)
            for it in L(v.get('items')):
                if not words or words in (it.get('name') or '').lower() or words in (v.get('name') or '').lower():
                    rows.append((it.get('price') or 0, v, it))
        if not vendors:
            self.out('No vendor seen yet: open a vendor window in the game once, then /fbridge save.')
        elif not rows:
            self.out('Nothing matching in the %d vendor list(s) you have opened.' % len(vendors))
        for price, v, it in sorted(rows, key=lambda r: (r[2].get('name') or '', r[0]))[:40]:
            limited = '  limited %s' % it['limited'] if it.get('limited') else ''
            self.out('%-40s %-10s %s, %s (%s, %s)%s' % (it.get('name'), money(price), v.get('name'),
                                                       v.get('zone') or '', v.get('x'), v.get('y'), limited))
        self.out(self.source())

    def rep(self, args):
        words = self.words(args).lower()
        self.out(self.head())
        for r in L(self.c.get('reputation')):
            if words and words not in (r.get('name') or '').lower():
                continue
            lo, hi, val = r.get('min'), r.get('max'), r.get('value')
            prog = ' %s / %s' % (val - lo, hi - lo) if None not in (lo, hi, val) else ''
            self.out('%-28s %-10s%s' % (r.get('name'), STANDING.get(r.get('standing'), r.get('standing')), prog))
        self.out(self.source())

    # ---- quests ----
    def quest_ids(self, words):
        """[(id, title)] of quests whose title holds the words: Forever's titles, then Classic-only ones."""
        like = '%' + words.lower() + '%'
        rows = self.store.q('SELECT id, title FROM quest WHERE lower(title) LIKE ? ORDER BY lower(title) = ? DESC, id',
                            (like, words.lower()))
        seen = {r[0] for r in rows}
        classic = self.store.q('SELECT id, title FROM quest_classic WHERE lower(title) LIKE ? '
                               'ORDER BY lower(title) = ? DESC, id', (like, words.lower()))
        rows += [(r[0], '%s (%s)' % (r[1], CLASSIC)) for r in classic if r[0] not in seen]
        return rows

    def quest_state(self, qid, done, active):
        twins = {r[0] for r in self.store.q('SELECT other FROM twin WHERE quest=?', (qid,))}
        if qid in done or twins & done:
            twin = ' (under its twin id %s)' % ', '.join(map(str, sorted(twins & done)))
            return 'done' + ('' if qid in done else twin)
        if qid in active:
            return 'in your quest log' + (' (ready to hand in)' if active[qid].get('complete') else '')
        if not done:
            return 'not in your log; done or not is unknown (this snapshot has no quest history)'
        return 'not done'

    def quests(self, args):
        q = D(self.c.get('quests'))
        done = {int(x) for x in L(q.get('completed')) if isinstance(x, int)}
        active = {a.get('id'): a for a in L(q.get('active')) if isinstance(a, dict) and a.get('id')}
        words = self.words(args)
        if words:
            if words.isdigit():
                n = int(words)
                forever = [r[0] for r in self.store.q('SELECT title FROM quest WHERE id=?', (n,)) if r[0]]
                classic = [r[0] for r in self.store.q('SELECT title FROM quest_classic WHERE id=?', (n,)) if r[0]]
                title = (forever[0] if forever else (active.get(n) or {}).get('title')
                         or ('%s (%s)' % (classic[0], CLASSIC) if classic else None))
                self.out('%s %s: %s' % (n, title or '', self.quest_state(n, done, active)))
            else:
                hits = self.quest_ids(words)
                if not hits:
                    hits = [(a['id'], a.get('title')) for a in active.values()
                            if words.lower() in (a.get('title') or '').lower()]
                if not hits:
                    self.out('No quest named like %r in the data (try its number).' % words)
                for qid, title in hits[:12]:
                    self.out('%-36s %-6s %s' % (title, qid, self.quest_state(qid, done, active)))
            if not done:
                self.out('(this snapshot holds no completed quests: see  forever me status)')
            self.out(self.source())
            self.out(self.store.data_line())  # the titles and twins came from ForeverDB's data
            return
        self.out(self.head())
        self.out('%d quests done, %d in the log' % (len(done), len(active)))
        for a in L(q.get('active')):
            ready = '  (ready to hand in)' if a.get('complete') else ''
            self.out('  %-36s level %s%s' % (a.get('title'), a.get('level'), ready))
        self.out(self.source())

    def bags(self, args):
        words = self.words(args).lower()
        for label, field in (('bags', 'bags'), ('bank', 'bank')):
            data = D(self.c.get(field))
            if not data:
                continue
            rows = sorted(((self.item_name(i), n) for i, n in data.items()), key=lambda r: (-(r[1] or 0), r[0]))
            rows = [r for r in rows if not words or words in r[0].lower()]
            self.out('%s%s: %d kinds' % (label, ' (seen %s)' % ago(self.c.get('bankSaved')) if field == 'bank' else '',
                                         len(rows)))
            for name, n in rows[:40]:
                self.out('  %4d  %s' % (n, name))
        if not D(self.c.get('bags')):
            self.out('No bag contents in this snapshot.')
        self.out(self.source())

    def missing(self, args):
        """Empty slots, worn-out items, and a wish list: which of the items you want you already have."""
        self.out(self.head())
        eq = L(self.c.get('equipped'))
        if not eq:
            self.out('No gear in this snapshot: type /fbridge save in the game first.')
            self.out(self.source())
            return
        worn = {e.get('slot'): e for e in eq}
        empty = [s for s in WORN_SLOTS if s not in worn]
        self.out('Empty slots: %s' % (', '.join(empty) or 'none'))
        low = ['%s %d%%' % (e.get('slot'), 100 * e['dur'] / e['durMax']) for e in eq
               if e.get('durMax') and e.get('dur') is not None and e['dur'] / e['durMax'] < 0.25]
        if low:
            self.out('Nearly broken: ' + ', '.join(low))
        plain = [e.get('slot') for e in eq if not e.get('enchant') and e.get('slot') in
                 ('Back', 'Chest', 'Wrist', 'Hands', 'Legs', 'Feet', 'MainHand', 'Ranged')]
        if plain:
            self.out('No enchant or kit on: ' + ', '.join(plain))
        want = [w.strip() for w in (getattr(args, 'want', None) or '').split(',') if w.strip()]
        wish = os.path.join(self.config_dir, 'wishlist.txt')
        unreadable = False
        if not want and os.path.exists(wish):
            try:
                with open(wish, encoding='utf-8', errors='replace') as fh:
                    want = [x.strip() for x in fh if x.strip() and not x.startswith('#')]
            except OSError:
                unreadable = True
                self.out('Wish list: not readable (%s); the rest goes on' % paths.show(wish))
        if want:
            names = {(e.get('name') or self.item_name(e.get('id'))).lower(): e.get('slot') for e in eq}
            carried = {self.item_name(i).lower() for part in ('bags', 'bank') for i in D(self.c.get(part))}
            have = 0
            for w in want:
                if w.lower() in names:
                    have += 1
                    state = 'worn (%s)' % names[w.lower()]
                elif w.lower() in carried:
                    state = 'in your bags or bank'
                else:
                    state = 'not owned yet'
                self.out('  %-36s %s' % (w, state))
            self.out('Wish list: %d of %d worn' % (have, len(want)))
        elif not unreadable:
            self.out('Wish list: none (pass --want "Item A, Item B" or keep one name per line in %s)'
                     % paths.show(wish))
        self.out(self.source())

    # ---- experience ----
    def levels_path(self):
        return os.path.join(self.config_dir, 'levels.json')

    def xp_table(self):
        table = {k: (v, 'Classic data') for k, v in CLASSIC_XP.items()}
        try:
            with open(self.levels_path(), encoding='utf-8') as fh:
                table.update({int(k): (int(v), 'your game') for k, v in json.load(fh).items()})
        except (OSError, ValueError):
            pass
        return table

    def remember_level(self):
        """Each level's experience bar as the game showed it: learned once, wins over the Classic table."""
        lv, mx = self.c.get('level'), self.c.get('xpMax')
        if not isinstance(lv, int) or not isinstance(mx, int) or mx <= 0:
            return
        path = self.levels_path()
        try:
            paths.claim(self.config_dir, paths.CONFIG_NAMES)
        except (paths.NotOurs, OSError):
            return  # someone else's folder, or one that cannot be made: `me` writes nothing and still answers
        try:
            seen = {}
            if os.path.exists(path):
                with open(path, encoding='utf-8') as fh:
                    seen = json.load(fh)
            if seen.get(str(lv)) != mx:
                seen[str(lv)] = mx
                tmp = path + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as fh:
                    json.dump(seen, fh, indent=0, sort_keys=True)
                os.replace(tmp, path)
        except (OSError, ValueError):
            pass

    @staticmethod
    def after_xp(level, xp, gain, table):
        """Where a gain of experience leaves you: (level, xp into it), or (level, None) past the known table."""
        while gain > 0:
            need = table.get(level, (None,))[0]
            if not need:
                return level, None
            left = need - xp
            if gain >= left:
                gain -= left
                level += 1
                xp = 0
            else:
                xp += gain
                gain = 0
        return level, xp

    @staticmethod
    def below_factor(player_level, quest_level):
        """ForeverDB's rule for a quest below you: 6 levels below pays 80%, 7 60%, 8 40%, 9 20%, 10 or more 10%."""
        if not isinstance(quest_level, int) or not isinstance(player_level, int):
            return 1.0
        d = player_level - quest_level
        return {6: 0.8, 7: 0.6, 8: 0.4, 9: 0.2}.get(d, 1.0 if d <= 5 else 0.1)

    def xp(self, args):
        cap = getattr(args, 'cap', None) or 29
        self.out(self.head())
        level, xp, mx = self.c.get('level'), self.c.get('xp') or 0, self.c.get('xpMax')
        if not isinstance(level, int) or not mx:
            self.out('No experience numbers in this snapshot (a logout snapshot can come out empty): type '
                     '/fbridge save in the game, then ask again.')
            self.out(self.source())
            return
        table = self.xp_table()
        table[level] = (int(mx), 'your game')
        self.out('XP %s / %s (%d%%)' % (num(xp), num(mx), 100 * xp / mx))
        room = before_next = None
        if level < cap:
            room = mx - xp + sum(table.get(n, (0,))[0] for n in range(level + 1, cap))
            unknown = [n for n in range(level + 1, cap + 1) if n not in table]
            classic = [n for n in range(level + 1, cap + 1) if n in table and table[n][1] == 'Classic data']
            bar = table.get(cap, (None,))[0]
            if bar:
                before_next = room + bar
            self.out('Room before level %d: about %s XP%s%s%s' % (
                cap, num(room), '; the level-%d bar holds %s more, so about %s before level %d' % (
                    cap, num(bar), num(before_next), cap + 1) if bar else '',
                ' (partial: levels %s are not in the table)' % ', '.join(map(str, unknown)) if unknown else '',
                ' (%s for levels %s)' % (CLASSIC, ', '.join(map(str, classic))) if classic else ''))
            if classic:
                self.out('  (levels %s use the Classic table, Classic data: Forever may differ; each level you reach '
                         'is learned from your game)' % ', '.join(map(str, classic)))
        elif level == cap:
            before_next = mx - xp
            self.out('You are level %d: %s XP left in this bar before level %d.' % (cap, num(before_next), cap + 1))
        else:
            self.out('You are past level %d.' % cap)
        quests = [a for a in L(D(self.c.get('quests')).get('active')) if isinstance(a, dict)]
        full = ready = at_level = 0
        nocap = []
        for a in quests:
            row = self.store.q('SELECT xp, level FROM quest WHERE id=?', (a.get('id'),))
            qxp = row[0][0] if row and isinstance(row[0][0], (int, float)) else None
            qlevel = (row[0][1] if row and row[0][1] else None) or a.get('level')
            if qxp is None:
                nocap.append(a)
                continue
            full += qxp
            at_level += qxp * self.below_factor(level, qlevel)
            if a.get('complete'):
                ready += qxp
        if quests:
            self.out('Quest log: %d quests, worth about %s XP in full (%s ready to hand in); at your level about %s' % (
                len(quests), num(full), num(ready), num(at_level)))
            if nocap:
                self.out('  %d quest(s) have no XP recorded by Forever players yet' % len(nocap))
            lv2, xp2 = self.after_xp(level, xp, at_level, table)
            if xp2 is not None and table.get(lv2):
                used = [n for n in range(level + 1, lv2 + 1) if table.get(n, (0, ''))[1] == CLASSIC]
                self.out('  handing in all of them: level %d, %d%% of the bar%s' % (
                    lv2, 100 * xp2 / table[lv2][0], ' (%s for levels %s)' % (CLASSIC, ', '.join(map(str, used)))
                    if used else ''))
            if before_next is not None and at_level > 0:
                used = [n for n in range(level + 1, cap + 1) if table.get(n, (0, ''))[1] == CLASSIC]
                self.out('  that %s level %d%s' % ('would PASS' if at_level >= before_next else 'stays below', cap + 1,
                                                  ' (%s for levels %s)' % (CLASSIC, ', '.join(map(str, used)))
                                                  if used else ''))
            self.out('  (quest XP: what Forever players recorded, from ForeverDB.net; a quest 6+ levels below you '
                     'pays less by ForeverDB\'s rule)')
        self.out(self.source())
        self.out(self.store.data_line())

    def talents(self, args):
        tabs = L(D(self.c.get('talents')).get('tabs'))
        self.out(self.head())
        if not tabs:
            self.out('No talents recorded.')
        for t in tabs:
            rows = []
            for tl in L(t.get('talents')):
                name = tl.get('name') or (self.spell_name(tl['spell']) if tl.get('spell')
                                          else 'node %s' % tl.get('node'))
                rows.append((name, tl.get('rank') or 0, tl.get('max')))
            self.out('%s: %d points' % (t.get('name') or 'talents', sum(r[1] for r in rows)))
            for name, rank, mx in sorted(rows, key=lambda r: (-r[1], r[0])):
                self.out('  %-36s %s/%s' % (name, rank, mx))
        self.out(self.source())

    def json(self, args):
        obj = {'_from': self.source()}  # in the printed answer only: the saved file is never changed
        obj.update(self.db if getattr(args, 'all', False) else {self.key: self.c})
        self.out(json.dumps(obj, indent=1, ensure_ascii=False, default=str))

    def status(self, args):
        db, c = self.db, self.c
        diag = D(db.get('diag'))
        self.out('file      %s' % paths.show(self.path))
        self.out('written   %s' % ago(os.path.getmtime(self.path)))
        self.out('add-on    %s · schema %s' % (diag.get('addon', '?'), db.get('schema')))
        g = D(diag.get('game')) or D(c.get('game'))
        if g:
            self.out('client    %s build %s (interface %s)' % (g.get('version'), g.get('build'), g.get('toc')))
        chars = D(db.get('chars'))
        self.out('chars     %s' % ', '.join('%s (%s)' % (k, ago(D(v).get('saved'))) for k, v in chars.items()))
        self.out('snapshot  %s, saved %s, reason %s' % (self.who(), ago(c.get('saved')), c.get('reason') or '?'))
        self.out('auto-save %s' % ('on' if db.get('auto') else 'off'))
        self.out('seen      %d trainer(s), %d vendor(s)' % (len(D(db.get('trainers'))), len(D(db.get('vendors')))))
        kept = L(c.get('kept'))
        if kept:
            self.out('kept      %s (the game had emptied them at logout; the earlier values were kept)'
                     % ', '.join(map(str, kept)))
        gaps = [name for name, part in (('experience', c.get('xpMax')), ('stats', D(c.get('stats')).get('stamina')),
                                        ('gear', L(c.get('equipped'))), ('bags', D(c.get('bags'))),
                                        ('completed quests', L(D(c.get('quests')).get('completed'))),
                                        ('professions', self.professions())) if not part]
        if gaps:
            self.out('warning   no %s in this snapshot. A snapshot taken at logout can come out empty or zero '
                     '(the game has already let go of them); /fbridge save in the game writes a full one.'
                     % ', '.join(gaps))
        for k, n in D(db.get('notes')).items():
            self.out('note      %s: %s' % (k, ', '.join('%s=%s' % (a, b) for a, b in D(n).items() if a != 'sample')))
        ev = D(db.get('events'))
        if ev:
            top = sorted(ev.items(), key=lambda kv: -(D(kv[1]).get('n') or 0))[:16]
            self.out('events    ' + ', '.join('%s x%s' % (k, D(v).get('n')) for k, v in top))
        errors = D(c.get('errors'))
        self.out('problems  %s' % ('; '.join('%s: %s' % kv for kv in errors.items()) if errors else 'none'))
        missing = sorted(k for k, v in D(diag.get('has')).items() if not v)
        if missing:
            self.out('this client has no: %s' % ', '.join(missing))
        if c.get('saved'):
            self.out('age       %s: ask for /fbridge save only when a number that changes (XP, gold, quests, '
                     'gear) is needed' % ago(c.get('saved')))


COMMANDS = ('summary', 'gear', 'stats', 'skills', 'recipes', 'trainer', 'vendor', 'rep', 'quests', 'bags', 'missing',
            'xp', 'talents', 'json', 'status')


def run(store, game, args, out=print, config_dir=None):
    try:
        db, path = load(game, getattr(args, 'file', None))
        key, char = pick(db, getattr(args, 'char', None))
    except NoSnapshot as e:
        out(str(e))
        return 2
    me = Me(store, db, path, key, char, out=out, config_dir=config_dir)
    me.remember_level()
    getattr(me, args.sub or 'summary')(args)
    return 0
