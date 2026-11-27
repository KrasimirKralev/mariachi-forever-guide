import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import scan_private  # noqa: E402


def j(*parts):
    """Planted test values are put together at run time, so that this file itself stays clean for the scan."""
    return ''.join(parts)


class Scan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fg-scan-')
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, rel, data):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as fh:
            fh.write(data if isinstance(data, bytes) else data.encode('utf-8'))

    def test_clean_tree(self):
        self.put('a.py', 'print("hello")\n')
        self.put('LICENSE', 'MIT License\n\nCopyright (c) 2026 Some Body\n')
        self.assertEqual(scan_private.scan(self.root), [])

    def test_every_kind_of_hit_is_found(self):
        word = 'zebrafinch'  # stands in for a private word: given through --words, as the owner would
        outside = tempfile.TemporaryDirectory(prefix='fg-words-')  # the word list lives outside the scanned tree
        self.addCleanup(outside.cleanup)
        words = os.path.join(outside.name, 'words.txt')
        with open(words, 'w') as fh:
            fh.write(word + '\n')
        self.put('a.txt', 'the ZebrafinchBridge add-on\n')
        self.put('b.txt', 'a camel ' + 'Zebrafinch'.upper() + '\n')
        self.put('zebrafinch-notes.md', 'x\n')
        self.put('c.txt', j('mail me: some', 'one', '@', 'example.org\n'))
        self.put('d.txt', j('host 10.', '1.2.3 here\n'))
        self.put('e.txt', j('account 12345', '67890', '#1\n'))
        self.put('f.txt', j('/ho', 'me/', 'somebody/game\n'))
        self.put('g.txt', j('-- Data: Forever', 'DB.net (https://foreverdb.net), build 1\n'))
        self.put('h.txt', 'x' * 2500 + '\n')
        self.put('i.lua', ''.join('[%d]=1,\n' % n for n in range(300)))
        self.put('big.txt', 'a\n' * 300000)
        self.put('bin.dat', b'\x00\x01\x02')
        self.put('table.csv', 'ID,x\n1,2\n')
        self.put('m.pyc', b'')
        self.put('node_modules/x.js', 'x\n')
        self.put('__pycache__/y.txt', 'x\n')
        hits = scan_private.scan(self.root, scan_private.load_words(words))
        text = '\n'.join(hits)
        for expect in ('a.txt:1: private word #1', 'b.txt:1: private word #1', '[#1]-notes.md: private word #1 in the path',
                       'c.txt:1: an e-mail address', 'd.txt:1: an IP address', 'e.txt:1: an account id',
                       'f.txt:1: an absolute home path', "g.txt:1: a ForeverDB.net data file's header",
                       'h.txt:1: a 2500-character line', 'i.lua: 300 table rows', 'big.txt: 585 KB',
                       'bin.dat: a binary file', 'table.csv: a data, asset or binary file', 'm.pyc: a data',
                       'node_modules: a node_modules folder', '__pycache__: a __pycache__ folder'):
            self.assertIn(expect, text)

    def test_words_from_the_environment(self):
        outside = tempfile.TemporaryDirectory(prefix='fg-words-')
        self.addCleanup(outside.cleanup)
        words = os.path.join(outside.name, 'words.txt')
        with open(words, 'w') as fh:
            fh.write('# a comment\nquokkaland\n')
        self.put('a.txt', 'see QuokkalandHost\n')
        r = subprocess.run([sys.executable, '-B', '-I', os.path.join(ROOT, 'scripts', 'scan_private.py'), self.root],
                           capture_output=True, text=True, env=dict(os.environ, FOREVER_PRIVATE_WORDS=words))
        self.assertEqual(r.returncode, 1)
        self.assertIn('a.txt:1: private word #1', r.stdout)

    def test_version_numbers_are_not_ip_addresses(self):
        self.put('v.txt', 'build 1.60.1.71139 and 9.9.9.12345\n')
        self.assertEqual(scan_private.scan(self.root), [])

    def test_the_repository_is_clean(self):
        r = subprocess.run([sys.executable, '-B', '-I', os.path.join(ROOT, 'scripts', 'scan_private.py'), ROOT],
                           capture_output=True, text=True)
        lines = r.stdout.splitlines()
        # a test run itself may leave byte code behind (python without -B): that is not part of the release;
        # without the owner's words file the scan says that the private words were not checked
        # and the zips of scripts/package.py in dist/ (never committed: .gitignore) are not part of the tree either
        hits = [ln for ln in lines if '__pycache__' not in ln and not ln.startswith(('private words:', 'scan_private:'))
                and not re.match(r'(\./)?dist[/:\\]', ln)]
        self.assertEqual(hits, [])
        self.assertIn('private words: NOT CHECKED (no --words file)', lines)


class Round1(unittest.TestCase):
    """S9 and N10 of the first audit: no silent 'clean', plain substrings, positions instead of words."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fg-scan-')
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, 'tree')
        os.makedirs(self.root)
        self.words = os.path.join(self.tmp.name, 'words.txt')
        with open(self.words, 'w', encoding='utf-8') as fh:
            fh.write('# invented words only\nzebra-finch\nblue whale\nGröße\naveryveryverylongprivateword\nab\n')

    def put(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(text)

    def run_scan(self, *extra):
        r = subprocess.run([sys.executable, '-B', '-I', os.path.join(ROOT, 'scripts', 'scan_private.py'), self.root]
                           + list(extra), capture_output=True, text=True, env=dict(os.environ, FOREVER_PRIVATE_WORDS=''))
        return r.returncode, r.stdout

    def test_s9_no_words_file_never_says_clean(self):
        self.put('a.txt', 'nothing here\n')
        rc, out = self.run_scan()
        self.assertIn('private words: NOT CHECKED (no --words file)', out)
        self.assertNotIn('clean', out)

    def test_s9_words_are_plain_substrings_anywhere(self):
        self.put('a.txt', 'the ZEBRA-FINCH flew\n')
        self.put('b.txt', 'a Blue Whale passed\n')
        self.put('c.txt', 'die größe zählt\n')
        self.put('d.txt', 'xxAVeryVeryVeryLongPrivateWordxx\n')
        self.put('zebra-finch-notes/e.txt', 'x\n')
        rc, out = self.run_scan('--words', self.words)
        self.assertEqual(rc, 1)
        for expect in ('a.txt:1: private word #1', 'b.txt:1: private word #2', 'c.txt:1: private word #3',
                       'd.txt:1: private word #4',
                       os.path.join('[#1]-notes', 'e.txt') + ': private word #1 in the path'):
            self.assertIn(expect, out)
        for secret in ('zebra', 'whale', 'größe', 'longprivate', 'flew', 'passed'):
            self.assertNotIn(secret, out.lower())

    def test_n10_exactly_the_lines_that_hold_a_word(self):
        self.put('a.txt', 'one ab two\nno match here\ncab\n')
        rc, out = self.run_scan('--words', self.words)
        lines = [ln for ln in out.splitlines() if ln.startswith('a.txt:')]
        self.assertEqual(lines, ['a.txt:1: private word #5', 'a.txt:3: private word #5'])

    def test_loopback_is_not_a_private_address(self):
        self.put('a.txt', 'server on 127.0.0.1 here\n')
        rc, out = self.run_scan()
        self.assertNotIn('IP address', out)
        self.put('b.txt', 'host ' + '10.' + '1.2.3\n')
        rc, out = self.run_scan()
        self.assertIn('b.txt:1: an IP address', out)

    def test_r3_only_the_owners_own_repository_address_is_allowed(self):
        with open(self.words, 'a', encoding='utf-8') as fh:
            fh.write('imirkra\nquokkaowner\n')  # #6: a piece of the public handle; #7: an invented private word
        self.put('README.md', 'get it: https://github.com/KrasimirKralev/mariachi-forever-guide/releases/latest\n')
        self.put('b.txt', 'mail KrasimirKralev about it\n')
        self.put('c.txt', 'see QuokkaOwner/mariachi-forever-guide\n')
        rc, out = self.run_scan('--words', self.words)
        self.assertNotIn('README.md', out)
        self.assertIn('b.txt:1: private word #6', out)
        self.assertIn('c.txt:1: private word #7', out)


if __name__ == '__main__':
    unittest.main()
