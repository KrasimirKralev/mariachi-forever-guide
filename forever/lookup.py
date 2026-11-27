"""`forever item`, `forever quest`, `forever where`: answers from Forever's own data, Classic only where labelled.

Source order for every fact: WoW Forever's own (the game client's tables, the player's own game cache, what
ForeverDB players' add-ons recorded in Forever, Wowhead's Forever tooltips), and only where none of these knows,
Classic data (CMaNGOS classic-db, as ForeverDB.net ships it), always marked "(Classic data)".
"""
import html
import re

from .luatable import spots as unpack
from .text import coords, money, num

CLASSIC = 'Classic data'
QUALITY = ['poor', 'common', 'uncommon', 'rare', 'epic', 'legendary', 'artifact', 'heirloom']
SLOT = {1: 'Head', 2: 'Neck', 3: 'Shoulder', 4: 'Shirt', 5: 'Chest', 6: 'Waist', 7: 'Legs', 8: 'Feet', 9: 'Wrist',
        10: 'Hands', 11: 'Finger', 12: 'Trinket', 13: 'One-Hand', 14: 'Shield', 15: 'Ranged', 16: 'Back',
        17: 'Two-Hand', 18: 'Bag', 20: 'Chest', 21: 'Main Hand', 22: 'Off Hand', 23: 'Held', 24: 'Ammo', 25: 'Thrown',
        26: 'Ranged', 28: 'Relic'}
LABEL = {'s': '', 'f': '', 'c': ' (a clue, unconfirmed)', 'k': ' (%s)' % CLASSIC}
SIDES = {'horde': 'H', 'h': 'H', 'alliance': 'A', 'a': 'A'}
# where a creature stands, best first: where players saw it in Forever, where they opened its window, Classic data
SPOT_ORDER = "src = 'classic', src != 'seen'"


def tooltip_lines(tip):
    """The tooltip's text, one line per row, without its markup (the first line, the name, is dropped)."""
    t = re.sub(r'<br\s*/?>|</tr>|</td>|</th>|</div>|</table>|</span>', '\n', tip.get('tooltip') or '')
    t = html.unescape(re.sub(r'<[^>]+>', ' ', t))
    lines = [x for x in (re.sub(r'\s+', ' ', ln).strip() for ln in t.split('\n')) if x and not re.fullmatch(r'\d+', x)]
    return lines[1:] if lines and lines[0] == (tip.get('name') or lines[0]) else lines


class Lookup:
    def __init__(self, store, out=print, fetch=True, side=None):
        self.store, self.out, self.fetch = store, out, fetch
        self.side = SIDES.get((side or '').lower())

    def zone(self, uimap):
        r = self.store.q('SELECT name FROM uimap WHERE id=?', (uimap,))
        return r[0][0] if r and r[0][0] else 'map %s' % uimap

    def creature(self, i):
        r = self.store.q('SELECT name, title FROM npc WHERE id=?', (int(i),))
        if r and r[0][0]:
            return r[0][0] + (' (%s)' % r[0][1] if r[0][1] else '')
        tip = self.store.tooltip('npc', int(i), fetch=self.fetch)
        return (tip or {}).get('name') or 'creature %s' % i

    def need_data(self):
        if self.store.db() is None:
            self.out('No data yet: run  forever update  once (it downloads Forever\'s data into your cache).')
            return True
        return False

    # ---- items ---------------------------------------------------------------------------------------------
    def find_items(self, query):
        if query.isdigit():
            rows = self.store.q('SELECT id, name, quality, ilvl, req, inv FROM item WHERE id=?', (int(query),))
            return rows or [(int(query), None, None, None, None, None)]
        words = query.lower().split()
        sql = ('SELECT id, name, quality, ilvl, req, inv FROM item WHERE '
               + ' AND '.join(['lower(name) LIKE ?'] * len(words))
               + ' ORDER BY lower(name) = ? DESC, length(name), id LIMIT 25')
        return self.store.q(sql, ['%' + w + '%' for w in words] + [query.lower()])

    @staticmethod
    def item_line(r, tip=None):
        i, name, ql, il, rq, inv = r
        tip = tip or {}
        name = name or tip.get('name') or '(name not known yet)'
        if ql is None and isinstance(tip.get('quality'), int):
            ql = tip['quality']
        slot = SLOT.get(inv) if isinstance(inv, int) else None
        if tip.get('tooltip') and (il is None or rq is None or slot is None):
            # an item the client's static table does not hold (the server sends it): read its tooltip instead
            lines = tooltip_lines(tip)
            text = ' '.join(lines)
            m = re.search(r'Item Level (\d+)', text)
            il = il if il is not None else (int(m.group(1)) if m else None)
            m = re.search(r'Requires Level (\d+)', text)
            rq = rq if rq is not None else (int(m.group(1)) if m else None)
            if slot is None:
                names = sorted(set(SLOT.values()), key=len, reverse=True)
                slot = next((n for ln in lines[:4] for n in names if ln == n or ln.endswith(' ' + n)), None)
        bits = [QUALITY[ql] if isinstance(ql, int) and 0 <= ql < len(QUALITY) else None,
                'item level %s' % il if il else None, 'needs level %s' % rq if rq else None, slot]
        return '%7s  %s  [%s]' % (i, name, ', '.join(b for b in bits if b) or '-')

    def sources(self, item):
        """Where an item comes from in Forever: ForeverDB's gear finder, its loot tables, the tooltip's drop line."""
        out, unread = [], False
        r = self.store.q('SELECT raw FROM gear_source WHERE item=?', (item,))
        for src in (r[0][0].split('~') if r and r[0][0] else []):
            f = src.split('^')
            k = f[0]
            if k not in ('q', 'V', 'd', 'm', 'c', 'w'):
                unread = unread or bool(k)
                continue
            try:
                if k == 'q':
                    out.append('Quest: %s%s' % (f[2], LABEL.get(f[5], '')))
                elif k == 'V':
                    out.append('Sold by %s for %s%s' % (self.creature(f[1]), money(f[2]), LABEL.get(f[4], '')))
                elif k in ('d', 'm'):
                    pct = float(f[3] or 0)
                    name = f[2] if not f[2].startswith('NPC ') else self.creature(f[1])
                    label = LABEL.get(f[5] if k == 'd' else f[4], '')
                    out.append('Drops from %s%s%s' % (name, ' (%g%%)' % pct if pct else '', label))
                elif k == 'c':
                    out.append('Crafted: %s %s%s' % (f[1], f[2], LABEL.get(f[4], '')))
                elif k == 'w':
                    out.append('World drop%s' % LABEL.get(f[3], ''))
            except (IndexError, ValueError):
                continue
        if not out:
            for boss, inst, pct, src, kills in self.store.q(
                    'SELECT boss, inst, pct, src, kills FROM loot WHERE item=? ORDER BY pct DESC', (item,)):
                where = 'trash in %s' % inst if boss == 'trash' else boss + (' in %s' % inst if inst else '')
                out.append('Drops from %s%s%s' % (where, ' (%g%%%s)' % (pct, ' over %d kills' % kills if kills else '')
                                                  if pct else '', ' (%s)' % CLASSIC if src == 'c' else ''))
        if not out and unread:
            out.append('ForeverDB lists a source of a kind this tool does not read yet')
        elif unread:
            out.append('and more of kinds not read yet')
        return list(dict.fromkeys(out))

    def vendors_of(self, item, limit=6):
        rows = self.store.q('SELECT s.npc, s.price, s.limited, n.name, n.title, n.side FROM sold s LEFT JOIN npc n '
                            'ON n.id = s.npc WHERE s.item=?', (item,))
        if self.side:
            # your side first, then vendors whose side is not recorded, the other side last; cheapest first in each
            rows.sort(key=lambda r: (0 if r[5] == self.side else 1 if not r[5] else 2, r[1] or 0, r[3] or ''))
        else:
            rows.sort(key=lambda r: (r[1] or 0, r[3] or ''))
        out = []
        for npc, price, limited, name, title, side in rows[:limit]:
            spot = self.store.q('SELECT uimap, x, y, src FROM npc_spot WHERE npc=? ORDER BY ' + SPOT_ORDER + ' LIMIT 1',
                                (npc,))
            where = ''
            if spot:
                where = ', %s (%s)%s' % (self.zone(spot[0][0]), coords(spot[0][1], spot[0][2]),
                                         ' (%s)' % CLASSIC if spot[0][3] == 'classic' else '')
            out.append('%s%s%s: %s%s' % (name or 'creature %s' % npc, ' (%s)' % title if title else '', where,
                                         money(price), ', limited supply' if limited else ''))
        total = self.store.q('SELECT n FROM sold_count WHERE item=?', (item,))
        return out, max(len(rows), total[0][0] if total and total[0][0] else 0)

    def item(self, words, list_only=False):
        if self.need_data():
            return 2
        q = ' '.join(words).strip()
        rows = self.find_items(q)
        if not rows:
            self.out('No item named like: %s' % q)
            self.out(self.store.data_line())  # "none" is only as true as the data is fresh
            return 1
        if list_only or len(rows) > 1:
            self.out('%d match(es):' % len(rows))
            for r in rows:
                self.out('  ' + self.item_line(r))
            if list_only:
                self.out('from: item table of the game client (wago.tools) and ForeverDB')
                self.out(self.store.data_line())
                return 0
            self.out('')
        r = rows[0]
        tip = self.store.tooltip('item', r[0], fetch=self.fetch)
        self.out(self.item_line(r, tip))
        if tip and tip.get('tooltip'):
            for line in tooltip_lines(tip):
                self.out('  ' + line)
        elif tip and tip.get('error'):
            self.out("  (Wowhead's Forever tooltip service does not know this item)")
        else:
            self.out('  (no tooltip yet: %s)' % ('offline' if not self.fetch or self.store.http.offline
                                                 else 'the tooltip service did not answer'))
        src = self.sources(r[0])
        self.out('  source: ' + ('; '.join(src) if src else "not known in Forever's data (ForeverDB)"))
        sellers, n = self.vendors_of(r[0])
        if sellers:
            self.out('  sold by %d vendor(s), e.g.: %s' % (n, '; '.join(sellers)))
        self.out("from: item table of the game client (wago.tools), Wowhead's Forever tooltip, sources from ForeverDB")
        self.out(self.store.data_line())
        return 0

    # ---- quests --------------------------------------------------------------------------------------------
    def find_quests(self, q):
        if q.isdigit():
            return [int(q)]
        found = []
        for op, arg in (('=', q.lower()), ('LIKE', '%' + q.lower() + '%')):
            for table in ('quest', 'quest_classic'):
                sql = 'SELECT id FROM %s WHERE lower(title) %s ?' % (table, op)
                found += [r[0] for r in self.store.q(sql, (arg,)) if r[0] not in found]
            if found:
                break
        return found

    def quest_row(self, qid):
        keys = ('title', 'level', 'min', 'min_src', 'objective', 'starts', 'ends', 'players', 'new', 'after', 'side',
                'xp', 'next')
        r = self.store.q('SELECT ' + ', '.join(keys) + ' FROM quest WHERE id=?', (qid,))
        f = dict(zip(keys, r[0])) if r else {}
        ckeys = ('title', 'level', 'min', 'side', 'starts', 'ends', 'flags', 'need_all', 'need_one')
        r = self.store.q('SELECT ' + ', '.join(ckeys) + ' FROM quest_classic WHERE id=?', (qid,))
        c = dict(zip(ckeys, r[0])) if r else {}
        return f, c

    def title_of(self, qid, label=True):
        """A quest's title: Forever's, else the Classic table's, marked as such (label=False when the line that
        holds it already says Classic data)."""
        f, c = self.quest_row(qid)
        if f.get('title'):
            return f['title']
        if c.get('title'):
            return '%s (%s)' % (c['title'], CLASSIC) if label else c['title']
        return 'quest %s' % qid

    def who(self, qid, role, refs_text, classic):
        """'Name (title), Zone (x, y) · how that place is known', or None."""
        qs = self.store.q("SELECT uimap, x, y, src FROM quest_spot WHERE quest=? AND kind=? "
                          "ORDER BY src = 'client' DESC", (qid, role))
        tag = ' (%s)' % CLASSIC if classic else ''
        for kind, i in re.findall(r'([noi])(\d+)', refs_text or ''):
            i = int(i)
            spots = []
            if kind == 'n':
                name = self.creature(i)
                spots = self.store.q('SELECT uimap, x, y, src FROM npc_spot WHERE npc=? ORDER BY ' + SPOT_ORDER, (i,))
            elif kind == 'o':
                r = self.store.q('SELECT name, spots FROM object WHERE id=?', (i,))
                name = (r[0][0] if r else None) or 'an object'
                tag = ' (%s)' % CLASSIC
                spots = [(m, x, y, 'classic') for m, x, y in unpack(r[0][1] if r else '')]
            else:
                r = self.store.q('SELECT name FROM item WHERE id=?', (i,))
                name = 'an item, %s' % (r[0][0] if r and r[0][0] else i)
            forever = [s for s in spots if s[3] != 'classic']
            if forever:
                m, x, y, src = forever[0]
                return '%s%s, %s (%s)' % (name, tag, self.zone(m), coords(x, y))
            if qs:
                m, x, y, src = qs[0]
                how = "the game's quest map point" if src == 'client' else (
                    'where players took it' if role == 's' else 'where players handed it in')
                return '%s%s, %s (%s) · %s' % (name, tag, self.zone(m), coords(x, y), how)
            if spots:
                m, x, y, src = spots[0]
                return '%s, %s (%s) (%s)' % (name, self.zone(m), coords(x, y), CLASSIC)
            return name + tag
        if qs:
            m, x, y, src = qs[0]
            how = "the game's quest map point" if src == 'client' else (
                'where players took it' if role == 's' else 'where players handed it in')
            return '%s (%s) · %s' % (self.zone(m), coords(x, y), how)
        return None

    def quest(self, words):
        if self.need_data():
            return 2
        q = ' '.join(words).strip()
        found = self.find_quests(q)
        if not found:
            self.out('No quest named like: %s (searched Forever\'s quests and the Classic ones; try its number)' % q)
            self.out(self.store.data_line())
            return 1

        def side_of(i):
            f, c = self.quest_row(i)
            return (f.get('side') or c.get('side') or '').upper()
        pool = [i for i in found if not self.side or side_of(i) in (self.side, '')] or found
        pick = sorted(pool)[0]
        if len(found) > 1:
            self.out('%d quests match: %s; showing %s (pass a number for another)' % (
                len(found), ', '.join('%s %s' % (i, self.title_of(i)) for i in sorted(found)[:12]), pick))
        f, c = self.quest_row(pick)
        tip = self.store.tooltip('quest', pick, fetch=self.fetch)  # Forever's quest text: what it asks for
        tip_lines = tooltip_lines(tip) if tip and tip.get('tooltip') else []
        title = f.get('title') or (tip or {}).get('name') or c.get('title')
        classic_title = not f.get('title') and not (tip or {}).get('name') and c.get('title')
        self.out('%s (quest %s)%s' % (title or 'Quest %s' % pick, pick, ' (%s)' % CLASSIC if classic_title else ''))
        head = []
        if f.get('level'):
            head.append('level %s' % f['level'])
        elif c.get('level'):
            head.append('level %s (%s)' % (c['level'], CLASSIC))
        if f.get('min'):
            src = 'your game cache' if f.get('min_src') == 'your game' else 'ForeverDB'
            head.append('from level %s (%s)' % (f['min'], src))
        elif c.get('min'):
            head.append('from level %s (%s)' % (c['min'], CLASSIC))
        if f.get('side'):
            head.append({'h': 'Horde', 'a': 'Alliance'}.get(f['side'], f['side']))
        elif c.get('side'):
            head.append('%s (%s)' % ({'h': 'Horde', 'a': 'Alliance'}.get(c['side'], c['side']), CLASSIC))
        if head:
            self.out('  ' + ' · '.join(head))
        objective = f.get('objective') or next(
            (t for t in tip_lines if not t.startswith(('Level ', 'Requirements', '- '))), '')
        if objective:
            self.out('  ' + objective)
        needs = list(dict.fromkeys(t[2:] for t in tip_lines if t.startswith('- ')))
        if needs:
            self.out('  needs: ' + ', '.join(needs))
        start = self.who(pick, 's', f.get('starts'), False) if f.get('starts') else None
        if not start:
            start = self.who(pick, 's', c.get('starts'), True) if c.get('starts') else self.who(pick, 's', '', False)
        end = self.who(pick, 'e', f.get('ends'), False) if f.get('ends') else None
        if not end:
            end = self.who(pick, 'e', c.get('ends'), True) if c.get('ends') else self.who(pick, 'e', '', False)
        if start:
            self.out('  starts: ' + start)
        if end:
            self.out('  turn in: ' + end)
        if f.get('after'):
            self.out('  after: %s (%s)' % (self.title_of(f['after']), f['after']))
        else:
            for field, words in (('need_all', 'after'), ('need_one', 'after one of')):
                ids = [int(x) for x in re.findall(r'\d+', c.get(field) or '')]
                if ids:
                    names = ', '.join('%s (%s)' % (self.title_of(i, label=False), i) for i in ids)
                    self.out('  %s: %s (%s)' % (words, names, CLASSIC))
        if f.get('next'):
            self.out('  next: %s (%s)' % (self.title_of(f['next']), f['next']))
        if f.get('xp'):
            self.out('  experience: %s (what Forever players got, in full)' % num(f['xp']))
        if f.get('new'):
            self.out('  new in WoW Forever')
        if f.get('players'):
            self.out('  seen by %s ForeverDB players' % num(f['players']))
        if not f and not c:
            self.out("  Neither Forever's data nor the Classic data knows this quest yet.")
        self.out('from: ForeverDB (players\' records in Forever and the Forever client)%s%s' % (
            ', your game cache' if f.get('min_src') == 'your game' else '',
            '; Classic data only where marked' if c else ''))
        self.out(self.store.data_line())
        return 0

    # ---- where ---------------------------------------------------------------------------------------------
    def npc_lines(self, ids, limit=10):
        out = []
        for i in ids[:limit]:
            r = self.store.q('SELECT name, title, side FROM npc WHERE id=?', (i,))
            name, title, side = r[0] if r else ('creature %s' % i, None, None)
            spots = self.store.q('SELECT uimap, x, y, src FROM npc_spot WHERE npc=? ORDER BY ' + SPOT_ORDER, (i,))
            faction = {'H': 'Horde', 'A': 'Alliance'}.get(side, side)
            label = '%s%s%s' % (name, ' <%s>' % title if title else '', ' [%s]' % faction if side else '')
            if not spots:
                out.append('%s: no place recorded' % label)
                continue
            if any(sp[3] != 'classic' for sp in spots):
                spots = [sp for sp in spots if sp[3] != 'classic']  # Forever's own places make Classic's moot
            unique = []
            for sp in spots:  # one spot per zone within a few map units: the same NPC seen twice
                if not any(u[0] == sp[0] and abs(u[1] - sp[1]) < 2 and abs(u[2] - sp[2]) < 2 for u in unique):
                    unique.append(sp)
            spots = unique
            places = []
            for m, x, y, src in spots[:3]:
                places.append('%s (%s)%s' % (self.zone(m), coords(x, y), ' (%s)' % CLASSIC if src == 'classic' else ''))
            more = ' and %d more spots' % (len(spots) - 3) if len(spots) > 3 else ''
            sells = self.store.q('SELECT COUNT(*) FROM sold WHERE npc=?', (i,))
            out.append('%s: %s%s%s' % (label, '; '.join(places), more,
                                       ' · sells %d item(s)' % sells[0][0] if sells and sells[0][0] else ''))
        return out

    TRAINER_WORDS = ('trainer', 'journeyman', 'expert', 'artisan', 'master', 'apprentice')

    def title_clause(self, lq):
        """SQL for NPC titles holding every word: 'tailoring trainer' also finds 'Expert Tailor'."""
        parts, args = [], []
        for w in lq.split():
            variants = {w}
            for end in ('ing', 'er', 's'):
                if w.endswith(end) and len(w) - len(end) >= 4:
                    variants.add(w[:-len(end)])
            if w in ('trainer', 'trainers'):
                variants |= set(self.TRAINER_WORDS)
            parts.append('(' + ' OR '.join(['lower(title) LIKE ?'] * len(variants)) + ')')
            args += ['%' + v + '%' for v in sorted(variants)]
        return ' AND '.join(parts) or '0', args

    def side_ok(self, side):
        return not self.side or side in (self.side, None, '')

    def where(self, words):
        if self.need_data():
            return 2
        q = ' '.join(words).strip()
        lq = q.lower()
        zone = self.store.q('SELECT id, name FROM uimap WHERE lower(name) = ? ORDER BY type, id', (lq,))
        if zone:
            uimap, name = zone[0]
            self.out('%s (map %s): vendors, trainers and flight points' % (name, uimap))
            rows = self.store.q("SELECT n.id, n.name, n.title, n.side, s.x, s.y, s.src FROM npc_spot s JOIN npc n "
                                "ON n.id = s.npc WHERE s.uimap = ? AND n.title IS NOT NULL ORDER BY n.title, n.name, "
                                "s.src = 'classic', s.src != 'seen'", (uimap,))
            shown, seen = 0, set()
            for i, nm, title, side, x, y, src in rows:
                if not self.side_ok(side) or i in seen:
                    continue
                seen.add(i)
                shown += 1
                if shown <= 40:
                    tag = ' (%s)' % CLASSIC if src == 'classic' else ''
                    self.out('  %-34s %-30s %s%s' % (nm, '<%s>' % title, coords(x, y), tag))
            if shown > 40:
                self.out('  ... and %d more' % (shown - 40))
            for tid, tname, horde, alliance, x, y in self.store.q(
                    'SELECT id, name, horde, alliance, x, y FROM taxi WHERE uimap=? ORDER BY name', (uimap,)):
                if self.side == 'H' and alliance and not horde or self.side == 'A' and horde and not alliance:
                    continue
                kind = '<flight point>' if (horde or alliance) else '<transport>'
                self.out('  %-34s %-30s %s' % (tname, kind, coords(x, y)))
            self.out("from: ForeverDB (vendors and trainers players saw in Forever), the game client's maps and "
                     'flight points (wago.tools); Classic data only where marked')
            self.out(self.store.data_line())
            return 0
        npcs = [r[0] for r in self.store.q('SELECT id, side FROM npc WHERE lower(name) = ? ORDER BY id', (lq,))]
        if npcs:
            for line in self.npc_lines(npcs):
                self.out(line)
            self.out('from: ForeverDB (where players saw them in Forever); Classic data only where marked')
            self.out(self.store.data_line())
            return 0
        items = self.store.q('SELECT id, name FROM item WHERE lower(name) = ? ORDER BY id', (lq,))
        for iid, iname in items:
            sellers, n = self.vendors_of(iid, limit=12)
            if sellers:
                first = ' (your side first)' if self.side else ''
                self.out('%s (item %s) is sold by %d vendor(s)%s:' % (iname, iid, n, first))
                for s in sellers:
                    self.out('  ' + s)
                if n > len(sellers):
                    self.out('  ... and %d more (ForeverDB keeps a few per item)' % (n - len(sellers)))
                self.out('from: ForeverDB (vendors and prices players saw in Forever)')
                self.out(self.store.data_line())
                return 0
        clause, args = self.title_clause(lq)
        titled = [r for r in self.store.q('SELECT id, side FROM npc WHERE ' + clause + ' ORDER BY title, name', args)
                  if self.side_ok(r[1])]
        named = [r for r in self.store.q('SELECT id, side FROM npc WHERE lower(name) LIKE ? ORDER BY length(name), id',
                                        ('%' + lq + '%',))]
        ids = [r[0] for r in titled] or [r[0] for r in named]
        if ids:
            if len(ids) > 15:
                self.out('%d match; the first 15:' % len(ids))
            for line in self.npc_lines(ids, limit=15):
                self.out(line)
            self.out('from: ForeverDB (where players saw them in Forever); Classic data only where marked')
            self.out(self.store.data_line())
            return 0
        self.out('Nothing called %r: not a zone, a creature, a vendor title or an item sold by vendors.' % q)
        self.out(self.store.data_line())
        return 1
