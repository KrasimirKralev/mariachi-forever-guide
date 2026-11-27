"""A small CBOR (RFC 8949) decoder: Auctionator keeps its price tables as CBOR bytes inside a Lua string.

Decoding only, data only. Text strings become str, byte strings bytes, maps dict, arrays list; tags are read
and dropped (their content is returned). Truncated or malformed input raises CBORError, never loops.
"""
import struct


class CBORError(ValueError):
    pass


_BREAK = object()
MAX_DEPTH = 256


def loads(data):
    """The first CBOR item in `data` (bytes)."""
    value, _ = decode(bytes(data), 0)
    if value is _BREAK:
        raise CBORError('a stray break code')
    return value


def decode(b, pos, depth=0):
    """(value, position after it)."""
    if depth > MAX_DEPTH:
        raise CBORError('nested too deep')
    if pos >= len(b):
        raise CBORError('the data ends early')
    ib = b[pos]
    pos += 1
    major, ai = ib >> 5, ib & 31

    if major == 7:
        if ai < 20:
            return ai, pos  # an unassigned simple value: keep its number
        if ai == 20:
            return False, pos
        if ai == 21:
            return True, pos
        if ai in (22, 23):
            return None, pos
        if ai == 24:
            _need(b, pos, 1)
            return b[pos], pos + 1
        if ai == 25:
            _need(b, pos, 2)
            return struct.unpack('>e', b[pos:pos + 2])[0], pos + 2
        if ai == 26:
            _need(b, pos, 4)
            return struct.unpack('>f', b[pos:pos + 4])[0], pos + 4
        if ai == 27:
            _need(b, pos, 8)
            return struct.unpack('>d', b[pos:pos + 8])[0], pos + 8
        if ai == 31:
            return _BREAK, pos
        raise CBORError('reserved simple value %d' % ai)

    if ai == 31:  # indefinite length
        if major in (2, 3):
            chunks = []
            while True:
                item, pos = decode(b, pos, depth + 1)
                if item is _BREAK:
                    break
                if not isinstance(item, (bytes, str)):
                    raise CBORError('a broken indefinite string')
                chunks.append(item)
            if major == 2:
                return b''.join(c if isinstance(c, bytes) else c.encode() for c in chunks), pos
            return ''.join(c if isinstance(c, str) else c.decode('utf-8', 'replace') for c in chunks), pos
        if major == 4:
            out = []
            while True:
                item, pos = decode(b, pos, depth + 1)
                if item is _BREAK:
                    return out, pos
                out.append(item)
        if major == 5:
            out = {}
            while True:
                key, pos = decode(b, pos, depth + 1)
                if key is _BREAK:
                    return out, pos
                val, pos = decode(b, pos, depth + 1)
                if val is _BREAK:
                    raise CBORError('a map key without a value')
                out[_hashable(key)] = val
        raise CBORError('indefinite length on type %d' % major)

    n, pos = _argument(b, pos, ai)
    if major == 0:
        return n, pos
    if major == 1:
        return -1 - n, pos
    if major == 2:
        _need(b, pos, n)
        return bytes(b[pos:pos + n]), pos + n
    if major == 3:
        _need(b, pos, n)
        return b[pos:pos + n].decode('utf-8', 'replace'), pos + n
    if major == 4:
        if n > len(b) - pos:
            raise CBORError('an array longer than the data')
        out = []
        for _ in range(n):
            item, pos = decode(b, pos, depth + 1)
            if item is _BREAK:
                raise CBORError('a stray break code')
            out.append(item)
        return out, pos
    if major == 5:
        if n > len(b) - pos:
            raise CBORError('a map longer than the data')
        out = {}
        for _ in range(n):
            key, pos = decode(b, pos, depth + 1)
            val, pos = decode(b, pos, depth + 1)
            if key is _BREAK or val is _BREAK:
                raise CBORError('a stray break code')
            out[_hashable(key)] = val
        return out, pos
    # major 6: a tag; its content is what matters here
    return decode(b, pos, depth + 1)


def _argument(b, pos, ai):
    if ai < 24:
        return ai, pos
    size = {24: 1, 25: 2, 26: 4, 27: 8}.get(ai)
    if size is None:
        raise CBORError('reserved length code %d' % ai)
    _need(b, pos, size)
    return int.from_bytes(b[pos:pos + size], 'big'), pos + size


def _need(b, pos, n):
    if pos + n > len(b):
        raise CBORError('the data ends early')


def _hashable(key):
    if isinstance(key, list):
        return tuple(_hashable(k) for k in key)
    if isinstance(key, dict):
        return tuple(sorted((str(k), str(v)) for k, v in key.items()))
    return key
