import struct
import unittest

from forever import cbor
from tests.fixtures import cbor_encode


class Decode(unittest.TestCase):
    def test_integers(self):
        for n in (0, 1, 23, 24, 255, 256, 65535, 65536, 2 ** 32, 2 ** 63, -1, -24, -25, -500):
            self.assertEqual(cbor.loads(cbor_encode(n)), n)

    def test_strings_arrays_maps(self):
        v = {'920001': {'m': 53, 'l': {'2511': 48}}, 'list': [1, 'two', None, True, False], 'bytes': b'\x00\xff'}
        self.assertEqual(cbor.loads(cbor_encode(v)), v)

    def test_floats(self):
        self.assertEqual(cbor.loads(b'\xf9\x3c\x00'), 1.0)  # half
        self.assertEqual(cbor.loads(b'\xfa' + struct.pack('>f', 2.5)), 2.5)
        self.assertEqual(cbor.loads(b'\xfb' + struct.pack('>d', -0.125)), -0.125)

    def test_indefinite_and_tags(self):
        self.assertEqual(cbor.loads(b'\x9f\x01\x02\xff'), [1, 2])
        self.assertEqual(cbor.loads(b'\xbf\x61a\x01\xff'), {'a': 1})
        self.assertEqual(cbor.loads(b'\x7f\x61a\x62bc\xff'), 'abc')
        self.assertEqual(cbor.loads(b'\xc1\x1a\x00\x00\x00\x10'), 16)  # a tag: its content

    def test_bad_input_raises(self):
        for bad in (b'', b'\x19\x01', b'\x62a', b'\x82\x01', b'\xff', b'\x81\xff', b'\x1c', b'\x5f\x01\xff',
                    b'\x9b' + b'\xff' * 8):
            with self.assertRaises(cbor.CBORError, msg=repr(bad)):
                cbor.loads(bad)

    def test_deep_nesting_is_refused(self):
        with self.assertRaises(cbor.CBORError):
            cbor.loads(b'\x81' * 1000 + b'\x01')


if __name__ == '__main__':
    unittest.main()
