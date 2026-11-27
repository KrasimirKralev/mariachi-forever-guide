"""Build the local SQLite database from the downloaded files (all data, never run).

Inputs, all in the user's cache:
  wago/<build>/<Table>.csv   the WoW Forever client's own tables for one build, from wago.tools
  foreverdb/*.lua            ForeverDB.net's add-on data files, unmodified (Data from ForeverDB.net)
  questcache.wdb             optional: the player's own client cache of the Forever server's quest records
Output: forever.db, rebuilt whole and swapped in atomically.
"""
import csv
import io
import json
import os
import re
import sqlite3
import struct
import time

from . import luatable as lt

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE item (id INTEGER PRIMARY KEY, name TEXT, quality INT, ilvl INT, req INT, inv INT, src TEXT);
CREATE TABLE enchant (id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE spell (id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE uimap (id INTEGER PRIMARY KEY, name TEXT, parent INT, type INT);
CREATE TABLE quest (id INTEGER PRIMARY KEY, title TEXT, level INT, min INT, min_src TEXT, objective TEXT,
  starts TEXT, ends TEXT, players INT, new INT, after INT, side TEXT, xp INT, next INT, xp_mult REAL, src TEXT);
CREATE TABLE quest_classic (id INTEGER PRIMARY KEY, title TEXT, level INT, min INT, side TEXT, starts TEXT,
  ends TEXT, flags TEXT, need_all TEXT, need_one TEXT);
CREATE TABLE twin (quest INT, other INT);
CREATE TABLE quest_spot (quest INT, kind TEXT, uimap INT, x REAL, y REAL, src TEXT);
CREATE TABLE npc (id INTEGER PRIMARY KEY, name TEXT, title TEXT, side TEXT, src TEXT);
CREATE TABLE npc_spot (npc INT, uimap INT, x REAL, y REAL, src TEXT);
CREATE TABLE object (id INTEGER PRIMARY KEY, name TEXT, spots TEXT);
CREATE TABLE sold (item INT, npc INT, price INT, stack INT, limited INT);
CREATE TABLE sold_count (item INTEGER PRIMARY KEY, n INT);
CREATE TABLE gear_source (item INTEGER PRIMARY KEY, raw TEXT);
CREATE TABLE loot (item INT, boss TEXT, inst TEXT, pct REAL, src TEXT, kills INT);
CREATE TABLE taxi (id INTEGER PRIMARY KEY, name TEXT, horde INT, alliance INT, uimap INT, x REAL, y REAL);
"""
INDEXES = """
CREATE INDEX item_name ON item (name COLLATE NOCASE);
CREATE INDEX quest_title ON quest (title COLLATE NOCASE);
CREATE INDEX qc_title ON quest_classic (title COLLATE NOCASE);
CREATE INDEX npc_name ON npc (name COLLATE NOCASE);
CREATE INDEX qs ON quest_spot (quest);
CREATE INDEX ns ON npc_spot (npc);
CREATE INDEX sold_item ON sold (item);
CREATE INDEX sold_npc ON sold (npc);
CREATE INDEX loot_item ON loot (item);
"""

WAGO_TABLES = ('ItemSparse', 'SpellName', 'SpellItemEnchantment', 'UiMap', 'UiMapAssignment', 'TaxiNodes')
FDB_FILES = ('Meta.lua', 'QuestForever.lua', 'QuestClassic.lua', 'QuestXP.lua', 'NPCs.lua', 'GearSources.lua',
             'Loot.lua', 'SearchNames.lua')
QUEST_CACHE_UNREADABLE = ("your game's quest cache could not be read (it is optional; the levels come from "
                          'ForeverDB then)')


def _int(v, default=None):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _float(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def read_text(path):
    with open(path, encoding='utf-8', errors='replace') as fh:
        return fh.read()


def csv_rows(path):
    with open(path, encoding='utf-8', errors='replace', newline='') as fh:
        return list(csv.DictReader(fh))


# ---- wago.tools tables (the game client's own) -------------------------------------------------------------

def load_items(con, rows):
    con.executemany('INSERT OR REPLACE INTO item VALUES (?,?,?,?,?,?,?)', (
        (_int(r.get('ID')), r.get('Display_lang') or None, _int(r.get('OverallQualityID')), _int(r.get('ItemLevel')),
         _int(r.get('RequiredLevel')), _int(r.get('InventoryType')), 'game')
        for r in rows if _int(r.get('ID')) is not None and r.get('Display_lang')))


def load_spells(con, rows):
    con.executemany('INSERT OR REPLACE INTO spell VALUES (?,?)',
                    ((_int(r.get('ID')), r.get('Name_lang')) for r in rows if _int(r.get('ID')) is not None))


def enchant_text(r):
    """The game's own enchant name with its $k1..$k3 numbers filled in ('Agility +$k1' -> 'Agility +4')."""
    name = r.get('Name_lang') or ''
    for k in (1, 2, 3):
        name = name.replace('$k%d' % k, str(r.get('EffectPointsMin_%d' % (k - 1)) or ''))
    return name


def load_enchants(con, rows):
    con.executemany('INSERT OR REPLACE INTO enchant VALUES (?,?)',
                    ((_int(r.get('ID')), enchant_text(r)) for r in rows if _int(r.get('ID')) is not None))


def load_uimaps(con, rows):
    con.executemany('INSERT OR REPLACE INTO uimap VALUES (?,?,?,?)', (
        (_int(r.get('ID')), r.get('Name_lang'), _int(r.get('ParentUiMapID')), _int(r.get('Type')))
        for r in rows if _int(r.get('ID')) is not None))


def world_to_map(assignments, uimap, continent, wx, wy):
    """(x %, y %) of a world position on one map, or None when that map does not show it."""
    for r in assignments:
        if _int(r.get('UiMapID')) != uimap or _int(r.get('MapID')) != continent:
            continue
        x0, y0 = _float(r.get('Region_0')), _float(r.get('Region_1'))
        x1, y1 = _float(r.get('Region_3')), _float(r.get('Region_4'))
        if None in (x0, y0, x1, y1) or not (x0 <= wx <= x1 and y0 <= wy <= y1) or x1 == x0 or y1 == y0:
            continue
        u0, v0 = _float(r.get('UiMin_0'), 0), _float(r.get('UiMin_1'), 0)
        u1, v1 = _float(r.get('UiMax_0'), 1), _float(r.get('UiMax_1'), 1)
        # the map's x runs against the world's y and the map's y against the world's x
        return (round(100 * (u0 + (y1 - wy) / (y1 - y0) * (u1 - u0)), 1),
                round(100 * (v0 + (x1 - wx) / (x1 - x0) * (v1 - v0)), 1))
    return None


def load_taxis(con, nodes, assignments, uimaps):
    """Flight masters, zeppelin towers and docks on their zone's map (zone maps are UiMap type 3)."""
    zones = {_int(r.get('ID')) for r in uimaps if _int(r.get('Type')) == 3}
    by_continent = {}
    for r in assignments:
        if _int(r.get('UiMapID')) in zones:
            by_continent.setdefault(_int(r.get('MapID')), []).append(r)
    for r in nodes:
        tid, flags = _int(r.get('ID')), _int(r.get('Flags'), 0)
        wx, wy, cont = _float(r.get('Pos_0')), _float(r.get('Pos_1')), _int(r.get('ContinentID'))
        if tid is None or wx is None or wy is None:
            continue
        spot, best = None, None
        for a in by_continent.get(cont, []):
            hit = world_to_map([a], _int(a.get('UiMapID')), cont, wx, wy)
            if hit:
                # the most specific map wins: a city's flight master belongs on the city map, not the zone around it
                area = abs((_float(a.get('Region_3'), 0) - _float(a.get('Region_0'), 0)) *
                           (_float(a.get('Region_4'), 0) - _float(a.get('Region_1'), 0)))
                if best is None or area < best:
                    spot, best = (_int(a.get('UiMapID')),) + hit, area
        con.execute('INSERT OR REPLACE INTO taxi VALUES (?,?,?,?,?,?,?)',
                    (tid, r.get('Name_lang'), flags & 2, flags & 1, *(spot or (None, None, None))))


# ---- ForeverDB.net's add-on data files ---------------------------------------------------------------------

QF_FIELDS = ('title', 'level', 'min', 'objective', 'starts', 'ends', 'players', 'new', 'after', 'seen_min', 'side',
             'offer_floor', 'classes')
QC_FIELDS = ('title', 'level', 'min', 'side', 'classes', 'races', 'need_all', 'need_one', 'excl', 'starts', 'ends',
             'objectives', 'skill', 'flags', 'rep', 'breadcrumb')


def load_quest_forever(con, text):
    quests = {k: dict(zip(QF_FIELDS, v.split('|'))) for k, v in lt.str_map(text, 'qfQuests').items()}
    for q, d in quests.items():
        con.execute('INSERT OR REPLACE INTO quest (id, title, level, min, min_src, objective, starts, ends, players, '
                    'new, after, side, src) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (q, d.get('title') or None, _int(d.get('level')) or None, _int(d.get('min')) or None,
                     'ForeverDB' if _int(d.get('min')) else None, d.get('objective') or None,
                     d.get('starts') or None, d.get('ends') or None, _int(d.get('players'), 0),
                     _int(d.get('new'), 0), _int(d.get('after')) or None, (d.get('side') or '').lower() or None,
                     'forever'))
    for src, name in (('client', 'qfPoi'), ('seen', 'qfSeen')):
        for q, body in lt.tbl_map(text, name).items():
            for kind, toks in re.findall(r'\b([se])\s*=\s*"([^"]*)"', body):
                for m, x, y in lt.spots(toks):
                    con.execute('INSERT INTO quest_spot VALUES (?,?,?,?,?,?)', (q, kind, m, x, y, src))
    for npc, name in lt.str_map(text, 'qfNpcNames').items():
        con.execute('INSERT INTO npc (id, name, src) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name',
                    (npc, name, 'forever'))
    for npc, toks in lt.str_map(text, 'qfNpcSpots').items():
        for m, x, y in lt.spots(toks):
            con.execute('INSERT INTO npc_spot VALUES (?,?,?,?,?)', (npc, m, x, y, 'seen'))
    for item, name in lt.str_map(text, 'qfItems').items():
        con.execute('INSERT OR IGNORE INTO item (id, name, src) VALUES (?,?,?)', (item, name, 'foreverdb'))
    for a, b in lt.str_map(text, 'qfTwin').items():
        for other in re.findall(r'\d+', b):
            con.execute('INSERT INTO twin VALUES (?,?)', (a, int(other)))
            con.execute('INSERT INTO twin VALUES (?,?)', (int(other), a))
    return len(quests)


def load_quest_classic(con, text):
    """Classic data (CMaNGOS classic-db via ForeverDB.net): used only where Forever's own data says nothing."""
    quests = {k: dict(zip(QC_FIELDS, v.split('|'))) for k, v in lt.str_map(text, 'qcQuests').items()}
    con.executemany('INSERT OR REPLACE INTO quest_classic VALUES (?,?,?,?,?,?,?,?,?,?)', (
        (q, d.get('title') or None, _int(d.get('level')) or None, _int(d.get('min')) or None,
         (d.get('side') or '').lower() or None, d.get('starts') or None, d.get('ends') or None, d.get('flags') or None,
         d.get('need_all') or None, d.get('need_one') or None)
        for q, d in quests.items()))
    for npc, body in lt.str_map(text, 'qcNpc').items():
        name, _, toks = body.partition('|')
        con.execute('INSERT INTO npc (id, name, src) VALUES (?,?,?) ON CONFLICT(id) DO NOTHING', (npc, name, 'classic'))
        for m, x, y in lt.spots(toks):
            con.execute('INSERT INTO npc_spot VALUES (?,?,?,?,?)', (npc, m, x, y, 'classic'))
    for obj, body in lt.str_map(text, 'qcObj').items():
        name, _, toks = body.partition('|')
        con.execute('INSERT OR REPLACE INTO object VALUES (?,?,?)', (obj, name, toks))
    return len(quests)


def load_quest_xp(con, text):
    """The full experience Forever players' add-ons captured per quest, and ForeverDB's per-level curve."""
    body = lt.section(text, 'qxp')
    m = re.search(r'\bq\s*=\s*\{(.*?)\}', body, re.S)
    n = 0
    for k, v in lt.NUM_ENTRY.findall(m.group(1) if m else ''):
        con.execute('INSERT INTO quest (id, xp) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET xp=excluded.xp',
                    (int(k), _int(v)))
        n += 1
    c = re.search(r'\bcurve\s*=\s*\{([^}]*)\}', body)
    curve = [_int(x) for x in re.findall(r'-?\d+', c.group(1))] if c else []
    d = re.search(r'\bdmul\s*=\s*([\d.]+)', body)
    con.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', ('xp_curve', json.dumps(curve)))
    con.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', ('xp_dmul', d.group(1) if d else ''))
    return n


def load_npcs(con, text):
    """Vendors and trainers ({name, title, map, x, y, side, seen}) and what vendors sell, for how much."""
    n = 0
    for npc, body in lt.tbl_map(text, 'npcs').items():
        f = lt.fields(body)
        if len(f) < 7:
            continue
        name, title, m, x, y, side, seen = f[:7]
        con.execute('INSERT INTO npc (id, name, title, side, src) VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
                    'title=excluded.title, side=excluded.side, name=COALESCE(npc.name, excluded.name)',
                    (npc, name or None, title or None, (side or '').upper() or None, 'forever'))
        if m:
            con.execute('INSERT INTO npc_spot VALUES (?,?,?,?,?)',
                        (npc, _int(m), _float(x), _float(y), 'vendor-seen' if seen == 1 else 'classic'))
        n += 1
    for item, body in lt.tbl_map(text, 'sold').items():
        nums = [_int(v, 0) for v in re.findall(r'-?\d+', body)]
        for i in range(0, len(nums) - 3, 4):
            con.execute('INSERT INTO sold VALUES (?,?,?,?,?)', (item, nums[i], nums[i + 1], nums[i + 2], nums[i + 3]))
    for item, name in lt.str_map(text, 'soldNames').items():
        con.execute('INSERT OR IGNORE INTO item (id, name, src) VALUES (?,?,?)', (item, name, 'foreverdb'))
    for k, v in lt.NUM_ENTRY.findall(lt.section(text, 'soldCount')):
        con.execute('INSERT OR REPLACE INTO sold_count VALUES (?,?)', (int(k), _int(v)))
    return n


def load_gear_sources(con, text):
    """The gear finder's lines: 'id (base 36)|name|groups|flags|side|twin|limit|sources'."""
    a, b = text.find('[==['), text.find(']==]')
    body = text[a + 4:b] if a >= 0 and b > a else ''
    n = 0
    for line in body.split('\n'):
        parts = line.split('|')
        if len(parts) < 8:
            continue
        try:
            item = int(parts[0], 36)
        except ValueError:
            continue
        if parts[1]:
            con.execute('INSERT OR IGNORE INTO item (id, name, src) VALUES (?,?,?)', (item, parts[1], 'foreverdb'))
        con.execute('INSERT OR REPLACE INTO gear_source VALUES (?,?)', (item, '|'.join(parts[7:])))
        n += 1
    return n


LOOT_ENTRY = re.compile(r'(\d+):([\d.]+):([fc])(?::([^:;"]*))?(?::(\d*))?')


def load_loot(con, text):
    """Boss loot of dungeons and raids: `loot = "item:pct:src[:h[:kills[:seen]]];..."` per boss line."""
    inst, n = None, 0
    for line in text.split('\n'):
        m = re.search(r'\{\s*id\s*=\s*\d+\s*,\s*name\s*=\s*"((?:[^"\\]|\\.)*)"', line)
        if m:
            inst = lt.unescape(m.group(1))
        for field, boss in (('loot', None), ('trash', 'trash')):
            lm = re.search(r'\b' + field + r'\s*=\s*"([^"]*)"', line)
            if not lm:
                continue
            if boss is None:
                bm = re.search(r'\bname\s*=\s*"((?:[^"\\]|\\.)*)"', line)
                who = lt.unescape(bm.group(1)) if bm else '?'
            else:
                who = 'trash'
            for entry in lm.group(1).split(';'):
                e = LOOT_ENTRY.match(entry)
                if e:
                    con.execute('INSERT INTO loot VALUES (?,?,?,?,?,?)',
                                (int(e.group(1)), who, inst, _float(e.group(2), 0), e.group(3), _int(e.group(5))))
                    n += 1
    return n


def load_search_names(con, text):
    n = 0
    for item, name in lt.str_map(text, 'searchItemNames').items():
        con.execute('INSERT OR IGNORE INTO item (id, name, src) VALUES (?,?,?)', (item, name, 'foreverdb'))
        n += 1
    return n


def foreverdb_meta(text):
    out = {}
    for k in ('version', 'build', 'built', 'site'):
        m = re.search(r'\b' + k + r'\s*=\s*"?([^",}]+)"?', lt.section(text, 'meta'))
        if m:
            out[k] = m.group(1)
    return out


# ---- the player's own client cache of the Forever server's quest records -----------------------------------

def quest_cache(data):
    """{quest: (level, min level, next quest, xp multiplier)} from questcache.wdb bytes. Only records that fit the
    layout below are used (the first int32 is the record's own id, levels 1-70); anything else is skipped."""
    out = {}
    if len(data) < 24 or data[:4] != b'TSQW':
        return out
    off = 24
    while off + 8 <= len(data):
        rid, ln = struct.unpack_from('<II', data, off)
        off += 8
        if ln == 0 or off + ln > len(data):
            break
        r = data[off:off + ln]
        off += ln
        if len(r) < 48:
            continue
        f = struct.unpack_from('<12i', r, 0)
        if f[0] != rid or not (0 < f[2] <= 70) or not (0 <= f[4] <= 70):
            continue
        mult = struct.unpack_from('<f', r, 44)[0]
        out[rid] = (f[2], f[4], f[9], round(mult, 3) if mult == mult else None)
    return out


def load_quest_cache(con, data):
    rows = quest_cache(data)
    for q, (lv, mn, nxt, mult) in rows.items():
        con.execute('INSERT INTO quest (id, src) VALUES (?, ?) ON CONFLICT(id) DO NOTHING', (q, 'forever'))
        con.execute("UPDATE quest SET level=?, min=?, min_src='your game', next=?, xp_mult=? WHERE id=?",
                    (lv, mn, nxt or None, mult, q))
    return len(rows)


# ---- everything ---------------------------------------------------------------------------------------------

def build(wago_dir, fdb_dir, out_path, wdb_path=None, meta=None):
    """Make out_path from what is in the two folders (missing files are skipped and listed). Returns a summary."""
    tmp = out_path + '.tmp'
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    summary, missing = {}, []

    def wago(table):
        p = os.path.join(wago_dir, table + '.csv')
        if os.path.exists(p):
            return csv_rows(p)
        missing.append(table + '.csv')
        return []

    def fdb(name):
        p = os.path.join(fdb_dir, name)
        if os.path.exists(p):
            return read_text(p)
        missing.append(name)
        return ''

    load_items(con, wago('ItemSparse'))
    load_spells(con, wago('SpellName'))
    load_enchants(con, wago('SpellItemEnchantment'))
    uimaps = wago('UiMap')
    load_uimaps(con, uimaps)
    load_taxis(con, wago('TaxiNodes'), wago('UiMapAssignment'), uimaps)
    summary['forever quests'] = load_quest_forever(con, fdb('QuestForever.lua'))
    summary['classic quests'] = load_quest_classic(con, fdb('QuestClassic.lua'))
    summary['quest xp'] = load_quest_xp(con, fdb('QuestXP.lua'))
    summary['vendors and trainers'] = load_npcs(con, fdb('NPCs.lua'))
    summary['gear sources'] = load_gear_sources(con, fdb('GearSources.lua'))
    summary['loot'] = load_loot(con, fdb('Loot.lua'))
    load_search_names(con, fdb('SearchNames.lua'))
    fmeta = foreverdb_meta(fdb('Meta.lua'))
    if wdb_path and os.path.exists(wdb_path):
        try:
            with open(wdb_path, 'rb') as fh:
                cache_bytes = fh.read()
        except OSError:  # optional: the game may hold it, or it is not a file; a note, not a missing download
            summary['notes'] = [QUEST_CACHE_UNREADABLE]
            cache_bytes = None
        if cache_bytes is not None:
            summary['quests from your game cache'] = load_quest_cache(con, cache_bytes)
    summary['items'] = con.execute('SELECT COUNT(*) FROM item').fetchone()[0]
    rows = dict(meta or {})
    rows.update({'built': str(int(time.time())), 'foreverdb_version': fmeta.get('version', ''),
                 'foreverdb_build': fmeta.get('build', ''), 'missing': json.dumps(missing)})
    con.executemany('INSERT OR REPLACE INTO meta VALUES (?,?)', [(k, str(v)) for k, v in rows.items()])
    con.executescript(INDEXES)
    con.commit()
    con.close()
    os.replace(tmp, out_path)
    summary['missing'] = missing
    return summary


def csv_text_rows(text):
    """For tests and small tables: CSV text -> list of dict rows."""
    return list(csv.DictReader(io.StringIO(text)))
