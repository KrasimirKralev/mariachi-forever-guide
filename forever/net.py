"""Polite downloads: one request at a time, at most 2 a second per host, a plain User-Agent, retries with a pause,
files written atomically and resumed where the server allows it.

Only HTTPS, and only to the sites this tool uses (ALLOWED_HOSTS): a request or a redirect anywhere else is refused.
An answer larger than its cap is stopped (MAX_GET for a page, MAX_DOWNLOAD or the published size for a file).
FOREVER_OFFLINE=1 (or --offline) forbids every request: the commands then answer from what is cached.
"""
import hashlib
import http.client
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from . import USER_AGENT

MIN_INTERVAL = 0.5  # seconds between two requests to the same host: at most 2 a second
# the sites the downloads really use (checked in a real run: none of them redirected anywhere else)
ALLOWED_HOSTS = frozenset({'foreverdb.net', 'wago.tools', 'nether.wowhead.com'})
MAX_GET = 8 << 20        # a page: the build list, the manifest, a tooltip
MAX_DOWNLOAD = 64 << 20  # a file without a published size (the largest real one is about 5 MB)


class Offline(RuntimeError):
    pass


class Refused(ValueError):
    """A request or a redirect to a place this tool does not use."""


class TooBig(ValueError):
    """An answer larger than it can be."""


class BadURL(ValueError):
    """An address the HTTP layer refuses to send (a space or a line break in it)."""


HTTPS_PORTS = frozenset({None, 443})


def allowed(url, hosts, schemes, ports=HTTPS_PORTS):
    """True only for a plain address on an allowed host: no user part, no backslash or white space in the host part
    (the check and urllib must read the host the same way), and the default port (ports=None: any port)."""
    try:
        u = urllib.parse.urlsplit(url)
        port = u.port
    except ValueError:
        return False
    if any(c in u.netloc for c in '@\\') or any(c.isspace() for c in u.netloc):
        return False
    if u.scheme not in schemes or (u.hostname or '').lower() not in hosts:
        return False
    return ports is None or port in ports


class Redirects(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only to HTTPS on one of the allowed hosts."""

    def __init__(self, hosts, schemes, ports=HTTPS_PORTS):
        self.hosts, self.schemes, self.ports = frozenset(hosts), frozenset(schemes), ports

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed(newurl, self.hosts, self.schemes, self.ports):
            u = urllib.parse.urlsplit(newurl)
            raise Refused('refused a redirect to %s://%s (not one of the sites this tool uses)'
                          % (u.scheme, u.hostname or '?'))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Http:
    def __init__(self, offline=None, opener=None, sleep=None, clock=None, interval=MIN_INTERVAL,
                 hosts=None, schemes=('https',)):
        if offline is None:
            offline = os.environ.get('FOREVER_OFFLINE', '') not in ('', '0')
        self.offline = offline
        self.hosts, self.schemes = frozenset(hosts or ALLOWED_HOSTS), frozenset(schemes)
        # HTTPS on its default port only; the plain-http loopback servers of the tests use a port of their own
        self.ports = HTTPS_PORTS if self.schemes == {'https'} else None
        # the real opener always checks where it goes; an opener handed in by a test checks only when asked to
        self.check = opener is None or hosts is not None
        if opener is None:
            opener = urllib.request.build_opener(Redirects(self.hosts, self.schemes, self.ports)).open
        self.opener = opener
        self.sleep, self.clock, self.interval = sleep or time.sleep, clock or time.monotonic, interval
        self.last = {}
        self.count = 0

    def _wait(self, host):
        gap = self.interval - (self.clock() - self.last.get(host, -1e9))
        if gap > 0:
            self.sleep(gap)
        self.last[host] = self.clock()

    def open(self, url, headers=None, timeout=60):
        if self.offline:
            raise Offline('offline: not fetching %s' % url)
        if self.check and not allowed(url, self.hosts, self.schemes, self.ports):
            u = urllib.parse.urlsplit(url)
            raise Refused('refused %s://%s (not one of the sites this tool uses)' % (u.scheme, u.hostname or '?'))
        host = url.split('/')[2] if '://' in url else url
        self._wait(host)
        self.count += 1
        req = urllib.request.Request(url, headers=dict({'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'},
                                                       **(headers or {})))
        return self.opener(req, timeout=timeout)

    def get(self, url, timeout=60, tries=3, max_bytes=MAX_GET):
        """The body of url (bytes), at most max_bytes. A 404 or 410 is raised at once; other failures are retried
        with a pause."""
        err = None
        for n in range(tries):
            try:
                with self.open(url, timeout=timeout) as resp:
                    size = resp.headers.get('Content-Length') if getattr(resp, 'headers', None) else None
                    if size and size.isdigit() and int(size) > max_bytes:
                        raise TooBig('%s answered with %d MB, more than it can be' % (_where(url), int(size) >> 20))
                    body = resp.read(max_bytes + 1)
                    if len(body) > max_bytes:
                        raise TooBig('%s answered with more than %d MB, more than it can be'
                                     % (_where(url), max_bytes >> 20))
                    return body
            except Offline:
                raise
            except urllib.error.HTTPError as e:
                err = e
                e.close()
                if e.code in (400, 401, 403, 404, 410):
                    raise
                if n + 1 < tries:
                    self.sleep(5 * (n + 1))
            except (urllib.error.URLError, OSError) as e:
                err = e
                if n + 1 < tries:
                    self.sleep(3 * (n + 1))
            except http.client.InvalidURL as e:
                raise BadURL('%s: the address cannot be sent (%s)' % (_where(url), e))
            except http.client.HTTPException as e:  # a broken answer: like a dropped connection
                err = OSError('the connection to %s broke (%s)' % (_where(url), type(e).__name__))
                if n + 1 < tries:
                    self.sleep(3 * (n + 1))
        raise err

    def download(self, url, dest, sha256=None, progress=None, timeout=120, tries=3, max_bytes=MAX_DOWNLOAD):
        """Save url to dest, at most max_bytes. A `dest.part` left by a stopped run is continued with an HTTP Range
        request when the server supports it (else fetched again). With sha256 the file is checked before it
        replaces dest."""
        part = dest + '.part'
        os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
        err = None
        for n in range(tries):
            have = os.path.getsize(part) if os.path.exists(part) else 0
            headers = {'Range': 'bytes=%d-' % have} if have else {}
            try:
                with self.open(url, headers=headers, timeout=timeout) as resp:
                    status = getattr(resp, 'status', None) or resp.getcode()
                    if have and status != 206:
                        have = 0  # the server sent the whole file again
                    total = resp.headers.get('Content-Length')
                    total = int(total) + have if total and total.isdigit() else None
                    if total and total > max_bytes:
                        _drop(part)
                        raise TooBig('%s is %d MB, more than it can be' % (os.path.basename(dest), total >> 20))
                    with open(part, 'ab' if have else 'wb') as fh:
                        got = have
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            got += len(chunk)
                            if got > max_bytes:
                                fh.close()
                                _drop(part)
                                raise TooBig('%s grew past %d MB, more than it can be'
                                             % (os.path.basename(dest), max_bytes >> 20))
                            fh.write(chunk)
                            if progress:
                                progress(got, total)
                break
            except Offline:
                raise
            except urllib.error.HTTPError as e:
                err = e
                e.close()
                if e.code == 416 and have:  # asked past the end: start again
                    os.remove(part)
                    continue
                if e.code in (400, 401, 403, 404, 410):
                    raise
                if n + 1 < tries:
                    self.sleep(5 * (n + 1))
            except (urllib.error.URLError, OSError) as e:
                err = e  # the .part file stays: the next try (or the next run) continues it
                if n + 1 < tries:
                    self.sleep(3 * (n + 1))
            except http.client.InvalidURL as e:
                raise BadURL('%s: the address cannot be sent (%s)' % (os.path.basename(dest), e))
            except http.client.HTTPException as e:
                err = OSError('the connection broke while %s came (%s)' % (os.path.basename(dest), type(e).__name__))
                if n + 1 < tries:
                    self.sleep(3 * (n + 1))
        else:
            raise err
        if sha256:
            digest = file_sha256(part)
            if digest != sha256:
                os.remove(part)
                raise ValueError('%s: the download does not match its published checksum' % os.path.basename(dest))
        os.replace(part, dest)
        return dest


def _drop(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _where(url):
    return urllib.parse.urlsplit(url).hostname or url


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def progress_printer(label, stream=None):
    """A progress callback that prints `label 42%` on a terminal and nothing elsewhere."""
    stream = stream or sys.stdout
    if not stream.isatty():
        return None
    state = {'last': -1}

    def show(got, total):
        if total:
            pct = int(100 * got / total)
            if pct != state['last']:
                state['last'] = pct
                stream.write('\r  %s %d%%' % (label, pct) + ('\n' if got >= total else ''))
                stream.flush()
    return show
