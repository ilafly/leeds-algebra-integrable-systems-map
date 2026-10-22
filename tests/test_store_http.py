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
