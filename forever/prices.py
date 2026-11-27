"""`forever price "a, b"`: auction prices from YOUR OWN Auctionator scans (its saved-variables file).

Auctionator keeps one CBOR table per realm key inside a Lua string: per item `m` the latest minimum buyout (copper),
`l` and `h` the lowest and highest low price per day, `a` how many were on offer; days count from 2020-01-01 (UTC).
Keys are an item id, `g:<id>:<item level>` or `gr:<id>:<suffix>`. Read locally; no network.
"""
import glob
import os
import time

from . import cbor
from . import luatable as lt
from . import paths
from .luatable import D
from .text import ago, money

# Auctionator numbers its days from midnight of 2020-01-01 in the player's own time zone (the game's time{...})
DAY0 = time.mktime((2020, 1, 1, 0, 0, 0, 0, 0, -1))


def day_number(ts):
    return int((ts - DAY0) // 86400)


class NoPrices(Exception):
    pass


def price_file(game):
    found = glob.glob(os.path.join(glob.escape(game or ''), 'WTF', 'Account', '*', 'SavedVariables', 'Auctionator.lua'))
    if not game or not found:
        raise NoPrices('No Auctionator prices found: install the Auctionator add-on, open the auction house and '
                       'let it scan (the file is written on /reload or logout).')
    return max(found, key=os.path.getmtime)


def text_keys(v):
    """Auctionator's encoder writes Lua strings as CBOR byte strings: make every key and string plain text."""
    if isinstance(v, bytes):
        return v.decode('utf-8', 'replace')
    if isinstance(v, dict):
        return {text_keys(k): text_keys(x) for k, x in v.items()}
    if isinstance(v, list):
        return [text_keys(x) for x in v]
    return v


def load(path):
    """{realm key: {price key: record}} from an Auctionator.lua file."""
    try:
        with open(path, 'rb') as fh:
            text = fh.read().decode('latin-1')  # keep every byte: the price tables are binary inside the strings
    except OSError as e:
        raise NoPrices('Cannot read the Auctionator file (%s). If the game is writing it right now, try again in a '
                       'moment.' % paths.describe(e))
    db = lt.parse(text).get('AUCTIONATOR_PRICE_DATABASE')
    if not isinstance(db, dict):
        raise NoPrices('Auctionator has no price database in %s yet.' % paths.show(path))
    out = {}
    for realm, raw in db.items():
        if realm == '__dbversion':
            continue
        if isinstance(raw, str):
            try:
                raw = cbor.loads(raw.encode('latin-1'))
            except cbor.CBORError:
                continue
        raw = text_keys(raw)
        if isinstance(raw, dict):
            out[str(realm)] = {str(k): v for k, v in raw.items()}
    return out


def key_item(key):
    parts = str(key).split(':')
    return parts[1] if parts[0] in ('g', 'gr') and len(parts) > 1 else parts[0]


def days(rec):
    out = []
    for sec in ('h', 'l', 'a'):
        for d in D(rec.get(sec)):
            try:
                out.append(int(d))
            except (TypeError, ValueError):
                pass
    return out


def rows_for(realms, item_id):
    """[(realm, key, record)] of every scan of this item."""
    out = []
    for realm, prices in realms.items():
        for key, rec in prices.items():
            if isinstance(rec, dict) and key_item(key) == str(item_id):
                out.append((realm, key, rec))
    return out


def describe(name, realm, key, rec, now=None, many_realms=False):
    now = time.time() if now is None else now
    ds = days(rec)
    last = max(ds) if ds else None
    age = day_number(now) - last if last is not None else None
    lows = [v for v in D(rec.get('l')).values() if isinstance(v, (int, float))] or \
           [v for v in D(rec.get('h')).values() if isinstance(v, (int, float))]
    avail = D(rec.get('a')).get(str(last)) if last is not None else None
    if avail is None and last is not None:
        avail = D(rec.get('a')).get(last)
    parts = str(key).split(':')
    label = name + (' (ilvl %s)' % parts[2] if parts[0] == 'g' and len(parts) > 2 else '')
    if many_realms:
        label += ' [%s]' % realm
    return '%-34s %-10s lowest seen %-10s seen %s%s' % (
        label, money(rec.get('m')) if rec.get('m') is not None else '?', money(min(lows)) if lows else '?',
        ('today' if age == 0 else '%d day(s) ago' % age) if age is not None else '?',
        ', %s on offer' % avail if avail else '')


def find_items(store, query):
    """[(id, name)] for a name or a number: an exact name first (highest item level first), else a part of one."""
    query = query.strip()
    if query.isdigit():
        r = store.q('SELECT name FROM item WHERE id=?', (int(query),))
        return [(int(query), r[0][0] if r and r[0][0] else 'item %s' % query)]
    rows = store.q('SELECT id, name FROM item WHERE lower(name) = ? ORDER BY ilvl DESC, id LIMIT 4', (query.lower(),))
    if not rows:
        rows = store.q('SELECT id, name FROM item WHERE lower(name) LIKE ? '
                       'ORDER BY length(name), ilvl DESC, id LIMIT 4', ('%' + query.lower() + '%',))
    return rows


def run(store, game, words, out=print):
    try:
        path = price_file(game)
        realms = load(path)
    except NoPrices as e:
        out(str(e))
        return 2
    queries = [q.strip() for q in ' '.join(words).split(',') if q.strip()]
    total = sum(len(v) for v in realms.values())
    if not queries:
        out('Usage: forever price "Item one, Item two"   (%d items priced in your Auctionator scans)' % total)
        return 2
    if store.db() is None:
        out('(no item names yet: run  forever update  once; numbers still work, e.g. forever price 12345)')
    many = len(realms) > 1
    for q in queries:
        ids = find_items(store, q)
        if not ids:
            out('%-34s not an item I know' % q)
            continue
        for iid, name in ids:
            rows = rows_for(realms, iid)
            if not rows:
                out('%-34s no auction scan of it yet' % name)
            for realm, key, rec in rows:
                out(describe(name, realm, key, rec, many_realms=many))
    out('from: your Auctionator scans (%s, written %s); a price is only as new as your last scan of that item'
        % (os.path.basename(path), ago(os.path.getmtime(path))))
    return 0
