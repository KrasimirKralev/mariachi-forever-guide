"""A fake network for tests: answers from a dict of URL -> bytes, records every request, never touches a socket."""
import email.message
import hashlib
import io
import json
import urllib.error

from tests import fixtures


class Response(io.BytesIO):
    def __init__(self, body, status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = email.message.Message()
        for k, v in (headers or {}).items():
            self.headers[k] = v
        self.headers['Content-Length'] = str(len(body))

    def getcode(self):
        return self.status


class FakeNet:
    def __init__(self, routes=None, ranges=True):
        self.routes = dict(routes or {})
        self.requests = []
        self.ranges = ranges
        self.fail_once = set()

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.requests.append((url, dict(req.header_items())))
        if url in self.fail_once:
            self.fail_once.discard(url)
            raise urllib.error.URLError('simulated network drop')
        if url not in self.routes:
            raise urllib.error.HTTPError(url, 404, 'Not Found', {}, io.BytesIO(b''))
        body = self.routes[url]
        rng = req.get_header('Range')
        if rng and self.ranges:
            start = int(rng.split('=')[1].rstrip('-'))
            return Response(body[start:], 206)
        return Response(body)


def forever_routes(build='9.9.9.12345'):
    """Every URL `forever update` asks for, answered with the synthetic fixtures."""
    from forever import build as b
    routes = {'https://wago.tools/api/builds': json.dumps({'wowf': [{'version': build}]}).encode()}
    for t in b.WAGO_TABLES:
        routes['https://wago.tools/db2/%s/csv?build=%s' % (t, build)] = fixtures.WAGO[t].encode()
    files = []
    for name in b.FDB_FILES:
        body = fixtures.FDB[name].encode()
        url = 'downloads/addon-data/%s?v=%s' % (name, hashlib.sha256(body).hexdigest()[:10])
        routes['https://foreverdb.net/' + url] = body
        # like the real manifest: the size is a number (the code accepts a digit string too)
        files.append({'path': 'Data/' + name, 'url': url, 'sha256': hashlib.sha256(body).hexdigest(),
                      'bytes': len(body)})
    manifest = {'data': {'version': '2030-01-01.test', 'files': files}}
    routes['https://foreverdb.net/downloads/addon-manifest.json'] = json.dumps(manifest).encode()
    return routes
