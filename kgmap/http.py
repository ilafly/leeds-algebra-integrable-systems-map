from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests

from .core import utcnow


class SourceError(RuntimeError):
    pass


class CachedHTTP:
    def __init__(self, store, days=30, timeout=25, refresh=False, offline=False, email=""):
        self.store, self.days, self.timeout = store, days, timeout
        self.refresh, self.offline = refresh, offline
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "LeedsMathMap/0.1 (local academic metadata prototype" + ("; mailto:" + email if email else "") + ")"
        self.last_request = {}
        self.events = []

    def get(self, url, params=None, accept=None, allow_not_found=False):
        params = dict(params or {})
        if "api.openalex.org" in url and os.environ.get("OPENALEX_API_KEY"):
            params["api_key"] = os.environ["OPENALEX_API_KEY"]
        prepared = requests.Request("GET", url, params=params).prepare()
        # Secret values are never written to cache, logs or provenance.
        public_params = {k: v for k, v in params.items() if k != "api_key"}
        public_url = requests.Request("GET", url, params=public_params).prepare().url
        key = hashlib.sha256((public_url + (accept or "")).encode()).hexdigest()
        with self.store.connect() as db:
            cached = db.execute("SELECT fetched_at,body,content_type FROM cache WHERE key=?", (key,)).fetchone()
        fresh = cached and (datetime.now(timezone.utc) - datetime.fromisoformat(cached[0])).total_seconds() < self.days * 86400
        if cached and (self.offline or (fresh and not self.refresh)):
            self.events.append({"url": public_url, "status": "cached", "fetched_at": cached[0]})
            return cached[1]
        if self.offline:
            raise SourceError("Not in offline cache: " + public_url)
        host = urlsplit(url).netloc
        interval = 3.1 if "arxiv.org" in host else 0.4
        time.sleep(max(0, interval - (time.monotonic() - self.last_request.get(host, 0))))
        for attempt in range(3):
            self.last_request[host] = time.monotonic()
            try:
                response = self.session.get(prepared.url, headers={"Accept": accept} if accept else {}, timeout=self.timeout)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    delay = response.headers.get("Retry-After", "")
                    time.sleep(min(float(delay) if delay.isdigit() else 2 ** (attempt + 1), 15))
                    continue
                if response.status_code == 404 and allow_not_found:
                    body = b""
                else:
                    response.raise_for_status()
                    body = response.content
                with self.store.connect() as db:
                    db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?,?)",
                               (key, public_url, utcnow(), body, response.headers.get("Content-Type", "")))
                self.events.append({"url": public_url, "status": "retrieved", "fetched_at": utcnow()})
                return body
            except requests.RequestException as exc:
                message = str(exc)
                if os.environ.get("OPENALEX_API_KEY"):
                    message = message.replace(os.environ["OPENALEX_API_KEY"], "[redacted]")
                if cached:
                    self.events.append({"url": public_url, "status": "stale_cache", "error": message, "fetched_at": cached[0]})
                    return cached[1]
                self.events.append({"url": public_url, "status": "unavailable", "error": message})
                raise SourceError(f"{public_url}: {message}") from None
        raise SourceError("Retry budget exceeded: " + public_url)

    def json(self, url, params=None):
        import json
        try:
            return json.loads(self.get(url, params, "application/json"))
        except ValueError as exc:
            raise SourceError(f"Invalid JSON from {url}: {exc}") from None
