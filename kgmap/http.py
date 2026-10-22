from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

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
        self.host_delays = {}

    def is_cached(self, url, params=None, accept=None):
        public_params = {k: v for k, v in (params or {}).items() if k != "api_key"}
        public_url = requests.Request("GET", url, params=public_params).prepare().url
        key = hashlib.sha256((public_url + (accept or "")).encode()).hexdigest()
        with self.store.connect() as db:
            row = db.execute("SELECT fetched_at FROM cache WHERE key=?", (key,)).fetchone()
        return bool(row and (self.offline or (not self.refresh and
            (datetime.now(timezone.utc) - datetime.fromisoformat(row[0])).total_seconds() < self.days * 86400)))

    def get(self, url, params=None, accept=None, allow_not_found=False, max_bytes=None, request_guard=None):
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
            if max_bytes and len(cached[1]) > max_bytes:
                raise SourceError("Cached response exceeds download size limit: " + public_url)
            self.events.append({"url": public_url, "status": "cached", "fetched_at": cached[0]})
            return cached[1]
        if self.offline:
            raise SourceError("Not in offline cache: " + public_url)
        if request_guard:
            request_guard(public_url)
        host = urlsplit(url).netloc
        interval = max(3.1 if "arxiv.org" in host else 0.4, self.host_delays.get(host, 0))
        time.sleep(max(0, interval - (time.monotonic() - self.last_request.get(host, 0))))
        for attempt in range(3):
            self.last_request[host] = time.monotonic()
            try:
                kwargs = {"headers": {"Accept": accept} if accept else {}, "timeout": self.timeout}
                if max_bytes:
                    kwargs["stream"] = True
                if request_guard:
                    kwargs["allow_redirects"] = False
                response = self.session.get(prepared.url, **kwargs)
                current_url = prepared.url
                redirects = 0
                while request_guard and response.status_code in {301, 302, 303, 307, 308}:
                    redirects += 1
                    if redirects > 5 or not response.headers.get("Location"):
                        response.close()
                        raise SourceError("Invalid or excessive PDF redirects")
                    target = urljoin(current_url, response.headers["Location"])
                    response.close()
                    request_guard(target)
                    next_host = urlsplit(target).netloc
                    delay = max(3.1 if "arxiv.org" in next_host else 0.4, self.host_delays.get(next_host, 0))
                    time.sleep(max(0, delay - (time.monotonic() - self.last_request.get(next_host, 0))))
                    self.last_request[next_host] = time.monotonic()
                    current_url = target
                    response = self.session.get(target, **kwargs)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    delay = response.headers.get("Retry-After", "")
                    if max_bytes:
                        response.close()
                    time.sleep(max(interval, min(float(delay) if delay.isdigit() else 2 ** (attempt + 1), 15)))
                    continue
                if response.status_code == 404 and allow_not_found:
                    body = b""
                    if max_bytes:
                        response.close()
                else:
                    response.raise_for_status()
                    if max_bytes:
                        chunks, size = [], 0
                        for chunk in response.iter_content(chunk_size=65536):
                            size += len(chunk)
                            if size > max_bytes:
                                response.close()
                                raise SourceError("Response exceeds download size limit: " + public_url)
                            chunks.append(chunk)
                        body = b"".join(chunks)
                        response.close()
                    else:
                        body = response.content
                with self.store.connect() as db:
                    db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?,?)",
                               (key, public_url, utcnow(), body, response.headers.get("Content-Type", "")))
                self.events.append({"url": public_url, "status": "retrieved", "fetched_at": utcnow(),
                                    **({"final_url": current_url} if request_guard else {})})
                return body
            except requests.RequestException as exc:
                message = str(exc)
                if os.environ.get("OPENALEX_API_KEY"):
                    message = message.replace(os.environ["OPENALEX_API_KEY"], "[redacted]")
                if cached:
                    if max_bytes and len(cached[1]) > max_bytes:
                        raise SourceError("Stale cached response exceeds download size limit: " + public_url) from None
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
