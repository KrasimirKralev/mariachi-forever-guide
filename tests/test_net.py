import hashlib
import os
import tempfile
import unittest
import urllib.error

from forever import USER_AGENT, net
from tests.fakenet import FakeNet


class Clock:
    def __init__(self):
        self.t = 100.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


class Polite(unittest.TestCase):
    def test_at_most_two_a_second_per_host_and_a_plain_user_agent(self):
        fake = FakeNet({'https://a.example/1': b'x', 'https://a.example/2': b'y', 'https://b.example/1': b'z'})
        clock = Clock()
        http = net.Http(offline=False, opener=fake, sleep=clock.sleep, clock=clock.now)
        for url in ('https://a.example/1', 'https://a.example/2', 'https://b.example/1', 'https://a.example/1'):
            http.get(url)
        self.assertEqual(len(fake.requests), 4)
        # the second request to a.example waited half a second; b.example did not wait for a.example
        self.assertEqual(clock.slept, [0.5, 0.5])
        for _, headers in fake.requests:
            self.assertEqual(headers.get('User-agent'), USER_AGENT)
        self.assertTrue(USER_AGENT.startswith('mariachi-forever-guide/'))

    def test_offline_never_opens(self):
        fake = FakeNet({'https://a.example/1': b'x'})
        http = net.Http(offline=True, opener=fake)
        with self.assertRaises(net.Offline):
            http.get('https://a.example/1')
        self.assertEqual(fake.requests, [])

    def test_404_is_not_retried_and_drops_are(self):
        clock = Clock()
        fake = FakeNet({'https://a.example/ok': b'fine'})
        http = net.Http(offline=False, opener=fake, sleep=clock.sleep, clock=clock.now)
        with self.assertRaises(urllib.error.HTTPError):
            http.get('https://a.example/missing')
        self.assertEqual(len(fake.requests), 1)
        fake.fail_once.add('https://a.example/ok')
        self.assertEqual(http.get('https://a.example/ok'), b'fine')
        self.assertEqual(len(fake.requests), 3)


class Download(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fg-net-')
        self.dest = os.path.join(self.tmp.name, 'sub', 'file.lua')
        self.body = b'0123456789' * 1000
        self.clock = Clock()

    def tearDown(self):
        self.tmp.cleanup()

    def http(self, fake):
        return net.Http(offline=False, opener=fake, sleep=self.clock.sleep, clock=self.clock.now)

    def test_resume_with_range(self):
        fake = FakeNet({'https://a.example/f': self.body})
        os.makedirs(os.path.dirname(self.dest))
        with open(self.dest + '.part', 'wb') as fh:
            fh.write(self.body[:4000])  # a stopped run left this
        self.http(fake).download('https://a.example/f', self.dest, sha256=hashlib.sha256(self.body).hexdigest())
        with open(self.dest, 'rb') as fh:
            self.assertEqual(fh.read(), self.body)
        self.assertEqual(fake.requests[0][1].get('Range'), 'bytes=4000-')
        self.assertFalse(os.path.exists(self.dest + '.part'))

    def test_server_without_range_sends_it_whole(self):
        fake = FakeNet({'https://a.example/f': self.body}, ranges=False)
        os.makedirs(os.path.dirname(self.dest))
        with open(self.dest + '.part', 'wb') as fh:
            fh.write(b'garbage')
        self.http(fake).download('https://a.example/f', self.dest)
        with open(self.dest, 'rb') as fh:
            self.assertEqual(fh.read(), self.body)

    def test_checksum_mismatch_keeps_nothing(self):
        fake = FakeNet({'https://a.example/f': self.body})
        with self.assertRaises(ValueError):
            self.http(fake).download('https://a.example/f', self.dest, sha256='0' * 64)
        self.assertFalse(os.path.exists(self.dest))
        self.assertFalse(os.path.exists(self.dest + '.part'))


if __name__ == '__main__':
    unittest.main()
