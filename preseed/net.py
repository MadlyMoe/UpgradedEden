"""HTTP layer: keep-alive connection pooling for high-concurrency fetches.

The CDN's cost is per-request round trip (~470 ms to the S3 origin), so
throughput comes almost entirely from concurrency plus connection reuse.
Each worker thread holds its own persistent HTTPS connection.
"""
import http.client
import ssl
import threading
import time
from urllib.parse import urlsplit

from . import config

_local = threading.local()
_ssl_ctx = ssl.create_default_context()


class HttpError(Exception):
    def __init__(self, status, url):
        super().__init__(f"HTTP {status} for {url}")
        self.status = status
        self.url = url


def _connection(host):
    """Per-thread persistent connection, keyed by host."""
    conns = getattr(_local, "conns", None)
    if conns is None:
        conns = _local.conns = {}
    c = conns.get(host)
    if c is None:
        c = conns[host] = http.client.HTTPSConnection(
            host, timeout=config.TIMEOUT, context=_ssl_ctx
        )
    return c


def _drop(host):
    conns = getattr(_local, "conns", None)
    if conns and host in conns:
        try:
            conns[host].close()
        except Exception:
            pass
        del conns[host]


def get(url, retries=None):
    """GET a URL, returning bytes. Reuses this thread's connection."""
    retries = config.RETRIES if retries is None else retries
    parts = urlsplit(url)
    host = parts.netloc
    path = parts.path + (("?" + parts.query) if parts.query else "")

    last = None
    for attempt in range(retries + 1):
        try:
            conn = _connection(host)
            conn.request("GET", path, headers={
                "User-Agent": config.USER_AGENT,
                "Accept": "*/*",
                "Connection": "keep-alive",
            })
            resp = conn.getresponse()
            body = resp.read()          # must drain to keep the connection usable
            if resp.status == 200:
                return body
            # 4xx are terminal; retrying won't help
            if 400 <= resp.status < 500 and resp.status != 429:
                raise HttpError(resp.status, url)
            last = HttpError(resp.status, url)
        except HttpError:
            raise
        except Exception as e:            # connection reset, timeout, TLS error
            last = e
            _drop(host)
        if attempt < retries:
            time.sleep(min(2 ** attempt * 0.25, 4.0))
    raise last if last else RuntimeError(f"failed: {url}")


def close_all():
    conns = getattr(_local, "conns", None)
    if conns:
        for c in conns.values():
            try:
                c.close()
            except Exception:
                pass
        conns.clear()
