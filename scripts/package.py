#!/usr/bin/env python3
"""package.py: make dist/mariachi-forever-guide-<version>.zip, the one download for players, plus a byte-identical
dist/mariachi-forever-guide.zip (so that releases/latest/download/mariachi-forever-guide.zip is a fixed one-link
download) and dist/SHA256SUMS listing both.

    python3 -I scripts/package.py [--out DIR]

The zip holds only what a player needs, listed below by name (nothing else can slip in): the command line, the
add-on, the Claude Code plugin and its marketplace file, and the README, licence, notices and security policy.
Not in it: tests, scripts, the CI workflow, contributor notes, caches. The zip is reproducible: sorted names, one
fixed timestamp, fixed permissions (the plugin's `forever` launcher keeps its executable bit).
"""
import argparse
import glob
import hashlib
import os
import shutil
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INCLUDE = ['README.md', 'LICENSE', 'NOTICE.md', 'SECURITY.md', '.claude-plugin/marketplace.json', 'forever/*.py',
           'addon/ForeverBridge/ForeverBridge.toc', 'addon/ForeverBridge/ForeverBridge.lua',
           'plugin/.claude-plugin/plugin.json', 'plugin/README.md', 'plugin/bin/forever',
           'plugin/skills/forever-guide/SKILL.md']
EXECUTABLE = {'plugin/bin/forever'}
STAMP = (2026, 1, 1, 0, 0, 0)


def version():
    with open(os.path.join(ROOT, 'forever', '__init__.py'), encoding='utf-8') as fh:
        m = re.search(r"^VERSION = '([^']+)'", fh.read(), re.M)
    if not m:
        raise SystemExit('package.py: no VERSION in forever/__init__.py')
    return m.group(1)


def files():
    out = []
    for pattern in INCLUDE:
        found = sorted(glob.glob(os.path.join(ROOT, pattern)))
        if not found:
            raise SystemExit('package.py: %s is missing' % pattern)
        out += [os.path.relpath(p, ROOT).replace(os.sep, '/') for p in found if os.path.isfile(p)]
    return sorted(set(out))


def build(out_dir):
    ver = version()
    os.makedirs(out_dir, exist_ok=True)
    name = 'mariachi-forever-guide-%s' % ver
    path = os.path.join(out_dir, name + '.zip')
    tmp = path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for rel in files():
            info = zipfile.ZipInfo(name + '/' + rel, date_time=STAMP)
            info.create_system = 3  # unix: the permission bits below are kept by unzip
            info.external_attr = ((0o100755 if rel in EXECUTABLE else 0o100644) << 16)
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(os.path.join(ROOT, rel), 'rb') as fh:
                z.writestr(info, fh.read())
    os.replace(tmp, path)
    fixed = os.path.join(out_dir, 'mariachi-forever-guide.zip')
    shutil.copyfile(path, fixed)
    with open(path, 'rb') as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    with open(os.path.join(out_dir, 'SHA256SUMS'), 'w', encoding='utf-8', newline='\n') as fh:
        for p in (path, fixed):
            fh.write('%s  %s\n' % (digest, os.path.basename(p)))
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', default=os.path.join(ROOT, 'dist'), help='where the zip goes (default: dist/)')
    args = ap.parse_args(argv)
    path = build(args.out)
    print('%s (%d KB, %d files), mariachi-forever-guide.zip (the same bytes), SHA256SUMS'
          % (path, (os.path.getsize(path) + 1023) // 1024, len(files())))
    return 0


if __name__ == '__main__':
    sys.exit(main())
