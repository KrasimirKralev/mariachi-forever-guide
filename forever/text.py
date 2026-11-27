"""Small text helpers shared by every command: money, ages, numbers."""
import time


def money(copper):
    """12345 -> '1g 23s 45c' (the game's own way of writing copper)."""
    try:
        c = int(float(copper or 0))
    except (TypeError, ValueError):
        return '?'
    sign = '-' if c < 0 else ''
    g, rest = divmod(abs(c), 10000)
    s, cc = divmod(rest, 100)
    parts = [p for p in ('%dg' % g if g else '', '%ds' % s if s else '', '%dc' % cc if cc or not (g or s) else '') if p]
    return sign + ' '.join(parts)


def ago(ts, now=None):
    """A unix time -> '5 min ago', '3.2 h ago', '4 days ago'; 'never' for nothing."""
    if not ts:
        return 'never'
    now = time.time() if now is None else now
    d = max(0.0, now - float(ts))
    if d < 90:
        return '%d s ago' % d
    if d < 5400:
        return '%d min ago' % (d // 60)
    if d < 172800:
        return '%.1f h ago' % (d / 3600)
    return '%d days ago' % (d // 86400)


def num(n):
    """34000 -> '34,000'."""
    try:
        return format(int(n), ',')
    except (TypeError, ValueError):
        return str(n)


def coords(x, y):
    try:
        return '%.1f, %.1f' % (float(x), float(y))
    except (TypeError, ValueError):
        return '?'
