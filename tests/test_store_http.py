import json

import pytest
import requests

from kgmap.http import CachedHTTP, SourceError
from kgmap.store import Store


class Response:
    status_code = 200
    content = b'{"value": 1}'
    headers = {"Content-Type": "application/json"}

    def raise_for_status(self):
        pass


def test_http_cache_avoids_repeat_requests(tmp_path, monkeypatch):
    store = Store(tmp_path / "cache.sqlite")
    http = CachedHTTP(store)
    calls = []
    monkeypatch.setattr(http.session, "get", lambda *a, **kw: calls.append(a) or Response())
    assert http.json("https://example.org/metadata")["value"] == 1
    assert http.json("https://example.org/metadata")["value"] == 1
    assert len(calls) == 1
    assert http.events[-1]["status"] == "cached"


def test_offline_cache_miss_is_explicit(tmp_path):
    with pytest.raises(SourceError, match="Not in offline cache"):
        CachedHTTP(Store(tmp_path / "cache.sqlite"), offline=True).get("https://example.org/uncached")


def test_stale_fallback_is_recorded(tmp_path, monkeypatch):
    http = CachedHTTP(Store(tmp_path / "cache.sqlite"))
    monkeypatch.setattr(http.session, "get", lambda *a, **kw: Response())
    http.get("https://example.org/metadata")
    http.refresh = True
    def fail(*args, **kwargs):
        raise requests.ConnectionError("unavailable")
    monkeypatch.setattr(http.session, "get", fail)
    assert http.get("https://example.org/metadata")
    assert http.events[-1]["status"] == "stale_cache"


def test_reviews_survive_snapshot_replacement(tmp_path):
    store = Store(tmp_path / "map.sqlite")
    store.review("connection:stable", "accepted", "Useful candidate")
    store.save({"publications": [1]})
    store.save({"publications": [2]})
    assert Store(tmp_path / "map.sqlite").reviews()["connection:stable"]["status"] == "accepted"


def test_import_validation_is_atomic(tmp_path):
    store = Store(tmp_path / "map.sqlite")
    with pytest.raises(ValueError):
        store.import_reviews({"good": {"status": "accepted"}, "bad": {"status": "wrong"}})
    assert store.reviews() == {}
    with pytest.raises(ValueError, match="note"):
        store.review("x", "corrected", "")


class StreamResponse(Response):
    def __init__(self, body=b'', status=200, location=None):
        self.content, self.status_code, self.closed = body, status, False
        self.headers = {'Content-Type': 'application/pdf', **({'Location': location} if location else {})}

    def iter_content(self, chunk_size):
        yield self.content[:4]
        yield self.content[4:]

    def close(self):
        self.closed = True


def test_pdf_download_limits_bytes_and_does_not_cache_overflow(tmp_path, monkeypatch):
    http = CachedHTTP(Store(tmp_path / 'cache.sqlite'))
    response = StreamResponse(b'%PDF-exceeds-limit')
    monkeypatch.setattr(http.session, 'get', lambda *a, **kw: response)
    with pytest.raises(SourceError, match='download size limit'):
        http.get('https://example.org/paper.pdf', max_bytes=5)
    assert response.closed
    assert not http.is_cached('https://example.org/paper.pdf')


def test_pdf_redirect_is_checked_before_destination_request(tmp_path, monkeypatch):
    http = CachedHTTP(Store(tmp_path / 'cache.sqlite'))
    calls, checked = [], []
    response = StreamResponse(status=302, location='http://localhost/private.pdf')
    def get(url, **kwargs):
        calls.append(url)
        assert kwargs['allow_redirects'] is False
        return response
    def guard(url):
        checked.append(url)
        if 'localhost' in url:
            raise SourceError('destination denied')
    monkeypatch.setattr(http.session, 'get', get)
    with pytest.raises(SourceError, match='destination denied'):
        http.get('https://example.org/paper.pdf', max_bytes=100, request_guard=guard)
    assert len(calls) == 1 and len(checked) == 2 and response.closed
