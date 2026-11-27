"""Read Lua table text as data. Nothing here ever runs Lua: the text is tokenised and parsed.

Two readers live here:
  * parse(text): the game's saved-variables files (`Name = { ["key"] = value, ... }`), any size, any nesting.
  * section / str_map / tbl_map: the one-entry-per-key layout of ForeverDB.net's add-on data files
    (`ns.name = { [id]="...", ... }`), read with regular expressions because those files are large and flat.
"""
import re

TOKEN = re.compile(r'''
    (?P<ws>\s+)
  | (?P<comment>--\[(?P<ceq>=*)\[.*?\](?P=ceq)\]|--[^\n]*)
  | (?P<long>\[(?P<leq>=*)\[.*?\](?P=leq)\])
  | (?P<num>(?:0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?))
  | (?P<str>"[^"\\]*(?:\\.[^"\\]*)*"|'[^'\\]*(?:\\.[^'\\]*)*')
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<neg>-)
  | (?P<sym>[{}\[\]=,;])
''', re.X | re.S)

ESCAPES = {'n': '\n', 'r': '\r', 't': '\t', 'a': '\a', 'b': '\b', 'f': '\f', 'v': '\v', '\n': '\n', '\\': '\\',
           '"': '"', "'": "'"}
NAMES = {'nil': None, 'true': True, 'false': False}


class LuaError(ValueError):
    pass


def unescape(body):
    def one(m):
        e = m.group(1)
        if e.isdigit():
            return chr(int(e))
        return ESCAPES.get(e, e)
    return re.sub(r'\\(\d{1,3}|.)', one, body, flags=re.S)


def tokens(text):
    pos, n = 0, len(text)
    while pos < n:
        m = TOKEN.match(text, pos)
        if not m:
            raise LuaError('cannot read the text at character %d' % pos)  # never echoes the file
        pos = m.end()
        kind = m.lastgroup
        if kind in ('ceq', 'leq'):
            kind = 'comment' if kind == 'ceq' else 'long'
        if kind in ('ws', 'comment'):
            continue
        yield kind, m.group(kind)


class Parser:
    def __init__(self, text):
        self.t = list(tokens(text))
        self.i = 0

    def peek(self, k=0):
        j = self.i + k
        return self.t[j] if j < len(self.t) else (None, None)

    def expect(self, sym):
        kind, val = self.peek()
        if kind != 'sym' or val != sym:
            raise LuaError('expected %r, found %r' % (sym, val))
        self.i += 1

    def value(self, depth=0):
        if depth > 200:
            raise LuaError('the tables are nested too deep')
        kind, val = self.peek()
        if kind is None:
            raise LuaError('the text ends in the middle of a value')
        self.i += 1
        if kind == 'sym' and val == '{':
            return self.table(depth + 1)
        if kind == 'num':
            if val.lower().startswith('0x'):
                return int(val, 16)
            if re.fullmatch(r'\d+', val):
                return int(val)
            return float(val)
        if kind == 'str':
            return unescape(val[1:-1])
        if kind == 'long':
            body = val[val.index('[', 1) + 1:val.rindex(']', 0, len(val) - 1)]
            return body[1:] if body.startswith('\n') else body
        if kind == 'neg':
            v = self.value(depth)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return -v
            raise LuaError('a minus sign before something that is not a number')
        if kind == 'name':
            if val in NAMES:
                return NAMES[val]
            if val in ('inf', 'nan'):
                return float(val)
            raise LuaError('a name where a value should be: %r' % val)
        raise LuaError('unexpected %r' % (val,))

    def table(self, depth):
        array, mapping = [], {}
        while True:
            kind, val = self.peek()
            if kind is None:
                raise LuaError('a table is not closed')
            if kind == 'sym' and val == '}':
                self.i += 1
                break
            if kind == 'sym' and val in ',;':
                self.i += 1
                continue
            if kind == 'sym' and val == '[':
                self.i += 1
                key = self.value(depth)
                self.expect(']')
                self.expect('=')
                mapping[key] = self.value(depth)
            elif kind == 'name' and self.peek(1) == ('sym', '='):
                self.i += 2
                mapping[val] = self.value(depth)
            else:
                array.append(self.value(depth))
        if not mapping:
            return array
        for n, v in enumerate(array, 1):
            mapping.setdefault(n, v)
        return mapping

    def assignments(self):
        out = {}
        while self.i < len(self.t):
            kind, val = self.peek()
            if kind == 'name' and self.peek(1) == ('sym', '='):
                self.i += 2
                out[val] = self.value()
            else:
                self.i += 1
        return out


def parse(text):
    """`A = {...} B = 5` -> {'A': {...}, 'B': 5}. A table with only 1..n keys becomes a list."""
    return Parser(text).assignments()


def D(x):
    """x when it is a table with keys, else {}."""
    return x if isinstance(x, dict) else {}


def L(x):
    """x as a list: a list stays, a table keyed 1..n becomes its values in order, anything else is []."""
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        return [x[k] for k in sorted(k for k in x if isinstance(k, int) and not isinstance(k, bool))]
    return []


# ---- ForeverDB.net's add-on data files (flat tables, one entry per key) -----------------------------------

def section(text, name):
    """The body of `ns.<name> = { ... }` (without the outer braces), or '' when the file has no such table."""
    m = re.search(r'\bns\.' + re.escape(name) + r'\s*=\s*\{', text)
    if not m:
        return ''
    j, depth, quote = m.end(), 1, None
    while j < len(text) and depth:
        c = text[j]
        if quote:
            if c == '\\':
                j += 1
            elif c == quote:
                quote = None
        elif c in '"\'':
            quote = c
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        j += 1
    return text[m.end():j - 1]


STR_ENTRY = re.compile(r'\[(\d+)\]\s*=\s*"((?:[^"\\]|\\.)*)"')
TBL_ENTRY = re.compile(r'\[(\d+)\]\s*=\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}')
NUM_ENTRY = re.compile(r'\[(\d+)\]\s*=\s*(-?\d+(?:\.\d+)?)')


def str_map(text, name):
    """ns.name = {[1]="a", ...} -> {1: 'a'}."""
    return {int(k): unescape(v) for k, v in STR_ENTRY.findall(section(text, name))}


def tbl_map(text, name):
    """ns.name = {[1]={...}, ...} -> {1: '...the inner text...'}."""
    return {int(k): v for k, v in TBL_ENTRY.findall(section(text, name))}


def fields(body):
    """'"Name","Title",9901,12.3,45.6,"H",0' -> ['Name', 'Title', 9901, 12.3, 45.6, 'H', 0]."""
    out = []
    for s, n in re.findall(r'"((?:[^"\\]|\\.)*)"|(-?\d+(?:\.\d+)?)', body):
        if n:
            out.append(float(n) if '.' in n else int(n))
        else:
            out.append(unescape(s))
    return out


def decode_spot(word):
    """One place on a map, as the data files write it: the legend says "spots (base-36: map*1e6 + x*10*1e3 +
    y*10)", so the number holds the map id in its millions, x in tenths of a per cent in its thousands and y in
    tenths of a per cent below that. Returns (map id, x, y), or None for a word that is not base 36."""
    try:
        packed = int(word, 36)
    except ValueError:
        return None
    map_id = packed // 1000000
    tenths_x = packed // 1000 - map_id * 1000
    tenths_y = packed - (packed // 1000) * 1000
    return map_id, tenths_x / 10, tenths_y / 10


def spots(text):
    """Every place in a space-separated list of packed spots."""
    found = []
    for word in (text or '').split():
        place = decode_spot(word)
        if place:
            found.append(place)
    return found


def b36(n):
    """An item id the way ForeverDB writes it in its gear finder (base 36, lower case)."""
    digits = '0123456789abcdefghijklmnopqrstuvwxyz'
    n = int(n)
    out = ''
    while True:
        n, r = divmod(n, 36)
        out = digits[r] + out
        if not n:
            return out
