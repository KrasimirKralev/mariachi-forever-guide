#!/usr/bin/env python3
"""scan_private.py: refuse a tree that holds private or third-party material. Run before every release:

    python3 -I scripts/scan_private.py [FOLDER] --words FILE

Every file under FOLDER (default: the repository) is checked for:
  1. private words, from a LOCAL file the owner keeps outside the repository (--words FILE, or the environment
     variable FOREVER_PRIVATE_WORDS naming it; one word or phrase per line, # for comments). Each one matches as a
     plain case-insensitive substring of every line and of every path, like `grep -i`. A hit names the file, the
     line and the word's position in the list ("private word #3"), never the word and never the line, so the
     report itself leaks nothing. Without a words file this check is NOT done, and the scan says so loudly.
  2. patterns: e-mail addresses, IPv4 addresses (loopback excepted), account ids (a long number, "#", a digit),
     absolute home paths (/home/<name>, /Users/<name>, C:\\Users\\<name>).
  3. files that must not be in the repo: binaries (a NUL byte, or not UTF-8), .pyc and __pycache__, node_modules,
     anything over 500 KB, data and asset files by their extension (databases, tables, game caches, images,
     fonts, models, archives).
  4. third-party data: the header line ForeverDB.net puts on its data files, game-table CSV headers, tooltip
     JSON, very long lines and long runs of `[id] = ...` table rows (a data dump, not code).
Two things are allowed on purpose: the copyright line of LICENSE (the author's name belongs there) and the
repository's own address KrasimirKralev/mariachi-forever-guide (the owner's public GitHub account); the same words
anywhere else, or any other "<name>/mariachi-forever-guide", are hits.
Exit code 0 when nothing was found, 1 with one line per hit.
"""
import argparse
import os
import re
import sys

LICENSE_LINE = re.compile(r'^Copyright \(c\) 2026 [A-Z][a-z]+ [A-Z][a-z]+$')
OWN_ADDRESS = re.compile(r'(?<![A-Za-z0-9-])KrasimirKralev/mariachi-forever-guide', re.I)

MAX_BYTES = 500 * 1024
DATA_EXT = {'.db', '.sqlite', '.sqlite3', '.csv', '.tsv', '.wdb', '.blp', '.m2', '.casc', '.idx', '.db2', '.dbc',
            '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tga', '.ico', '.svg', '.ttf', '.otf', '.woff',
            '.woff2', '.mp3', '.ogg', '.wav', '.mp4', '.zip', '.gz', '.tgz', '.xz', '.7z', '.rar', '.exe', '.dll',
            '.so', '.dylib', '.pyc', '.pyo', '.bak', '.wtf'}
BAD_DIRS = {'__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build', '.mypy_cache', '.pytest_cache'}
SKIP_DIRS = {'.git'}

EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}')
IPV4 = re.compile(r'(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\d.])')
ACCOUNT = re.compile(r'\b\d{6,}#\d+\b')
HOME = re.compile(r'(?:/home/|/Users/|[A-Za-z]:\\{1,2}Users\\{1,2})([A-Za-z0-9._-]+)')
HOME_OK = {'user', 'you', 'your-name', 'username', 'runner'}
SIGNATURES = [
    (re.compile(r'^-- Data: ForeverDB\.net \(https://foreverdb\.net\), build'), "a ForeverDB.net data file's header"),
    (re.compile(r'^ID,Description_lang,Display3_lang'), "the game's item table (CSV)"),
    (re.compile(r'"tooltip"\s*:\s*"<table'), 'a Wowhead tooltip (JSON)'),
    (re.compile(r'^TSQW'), "the game's quest cache"),
]
ROW = re.compile(r'\[\d+\]\s*=')
MAX_ROWS = 200
MAX_LINE = 2000


def load_words(path):
    """[word, ...] in the file's order (their positions are what a hit reports), lower-cased; [] without a file."""
    if not path:
        return []
    with open(path, encoding='utf-8-sig') as fh:  # a byte order mark (Notepad) must not hide the first word
        return [w.strip().casefold() for w in fh if w.strip() and not w.lstrip().startswith('#')]


def word_hits(text, words):
    """Positions (1-based) of the words found in text as plain case-insensitive substrings."""
    low = OWN_ADDRESS.sub('', text).casefold()
    return [n for n, w in enumerate(words, 1) if w and w in low]


def mask(path, words):
    """The path with every private word in it replaced by its position, so that printing it leaks nothing."""
    out = path
    for n, w in enumerate(words, 1):
        if w:
            out = re.sub(re.escape(w), '[#%d]' % n, out, flags=re.I)
    return out


def scan(root, words=None):
    words = list(words or [])
    hits = []
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        for d in list(dirnames):
            if d in SKIP_DIRS:
                dirnames.remove(d)
            elif d in BAD_DIRS:
                hits.append('%s: a %s folder' % (mask(os.path.join(rel_dir, d), words), d))
                dirnames.remove(d)
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            shown = mask(rel, words)
            for n in word_hits(rel, words):
                hits.append('%s: private word #%d in the path' % (shown, n))
            ext = os.path.splitext(name.lower())[1]
            if ext in DATA_EXT or name.lower().endswith('.json.gz'):
                hits.append('%s: a data, asset or binary file (%s)' % (shown, ext))
                continue
            if os.path.islink(path):
                hits.append('%s: a symbolic link' % shown)
                continue
            size = os.path.getsize(path)
            if size > MAX_BYTES:
                hits.append('%s: %d KB, over the 500 KB limit' % (shown, size // 1024))
                continue
            with open(path, 'rb') as fh:
                raw = fh.read()
            if b'\x00' in raw:
                hits.append('%s: a binary file' % shown)
                continue
            try:
                text = raw.decode('utf-8')
            except UnicodeDecodeError:
                hits.append('%s: not UTF-8 text' % shown)
                continue
            rows = len(ROW.findall(text))
            if rows > MAX_ROWS:
                hits.append('%s: %d table rows, a data dump' % (shown, rows))
            for n, line in enumerate(text.splitlines(), 1):
                if name == 'LICENSE' and LICENSE_LINE.match(line):
                    continue
                where = '%s:%d' % (shown, n)
                for k in word_hits(line, words):
                    hits.append('%s: private word #%d' % (where, k))
                for m in EMAIL.finditer(line):
                    hits.append('%s: an e-mail address' % where)
                for m in IPV4.finditer(line):
                    if not m.group(0).startswith('127.'):
                        hits.append('%s: an IP address' % where)
                for m in ACCOUNT.finditer(line):
                    hits.append('%s: an account id' % where)
                for m in HOME.finditer(line):
                    if m.group(1).lower() not in HOME_OK:
                        hits.append('%s: an absolute home path' % where)
                for sig, what in SIGNATURES:
                    if sig.search(line):
                        hits.append('%s: %s' % (where, what))
                if len(line) > MAX_LINE:
                    hits.append('%s: a %d-character line (data, not code)' % (where, len(line)))
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('root', nargs='?', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument('--words', help='a local file with the private words, one per line (never commit it)')
    args = ap.parse_args(argv)
    words_file = args.words or os.environ.get('FOREVER_PRIVATE_WORDS') or None
    words = load_words(words_file)
    hits = scan(args.root, words)
    for line in hits:
        print(line)
    if words:
        print('private words: %d checked' % len(words))
    elif words_file:
        print('private words: NOT CHECKED (the words file holds no words)')
    else:
        print('private words: NOT CHECKED (no --words file)')
    other = '%d hit(s)' % len(hits) if hits else '0 hits'
    if words:
        print('scan_private: %s in %s' % ('clean, 0 hits' if not hits else other, args.root))
    else:
        print('scan_private: %s in the other checks of %s; the private words were NOT checked'
              % (other, args.root))
    return 1 if hits else 0


if __name__ == '__main__':
    sys.exit(main())
