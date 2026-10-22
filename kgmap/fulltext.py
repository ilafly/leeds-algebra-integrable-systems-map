"""Public PDF retrieval, identity checks, page-aware extraction and local caching."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from .core import ROOT, dump_json, normalise, utcnow
from .http import SourceError

CACHE_ROOT = ROOT / "data/fulltext"
EXTRACTOR_VERSION = "pypdf-body-v1"
log = logging.getLogger(__name__)


def attach_cached_locations(publications, store):
    """Recover source-supplied OA PDF locations without re-querying metadata APIs."""
    by_work = {wid: p for p in publications for wid in p.get("openalex_ids", [])}
    with store.connect() as db:
        rows = db.execute("SELECT body FROM cache WHERE url LIKE 'https://api.openalex.org/works?%'").fetchall()
    for (body,) in rows:
        for work in json.loads(body).get("results", []):
            if work.get("id") in by_work:
                p = by_work[work["id"]]
                for loc in oa_locations(work):
                    if loc not in p.setdefault("full_text_locations", []):
                        p["full_text_locations"].append(loc)


def oa_locations(work):
    return [{"url": loc["pdf_url"], "license": loc.get("license"), "version": loc.get("version"),
             "is_oa": True, "metadata_source": work["id"]}
            for loc in work.get("locations", []) if loc.get("is_oa") and loc.get("pdf_url")]


def candidates(p):
    result = list(p.get("full_text_locations", []))
    if p.get("arxiv_id"):
        result.append({"url": "https://arxiv.org/pdf/" + p["arxiv_id"], "version": "preprint",
                       "license": None, "metadata_source": "https://arxiv.org/abs/" + p["arxiv_id"], "is_oa": True})
    seen, unique = set(), []
    for item in result:
        url = item["url"]
        if url.startswith("http://arxiv.org/") or url.startswith("http://eprints.whiterose.ac.uk/"):
            url = "https://" + url.removeprefix("http://")
        if url not in seen and item.get("is_oa"):
            seen.add(url)
            unique.append({**item, "url": url})
    # Repositories often expose author manuscripts with fewer access barriers.
    return sorted(unique, key=lambda x: (0 if "eprints.whiterose.ac.uk" in x["url"] else 1 if "arxiv.org" in x["url"] else 2, x["url"]))


def eligible(p):
    return not p.get("quarantined") and not p.get("is_retracted") and bool(p.get("researcher_ids"))


def balanced_sample(publications, researchers, limit):
    pools = {r["id"]: [p for p in publications if eligible(p) and r["id"] in p["researcher_ids"] and candidates(p)] for r in researchers}
    chosen, seen = [], set()
    while limit == 0 or len(chosen) < limit:
        progress = False
        for rid, pool in pools.items():
            while pool and pool[0]["id"] in seen:
                pool.pop(0)
            if pool and (limit == 0 or len(chosen) < limit):
                p = pool.pop(0)
                chosen.append(p)
                seen.add(p["id"])
                progress = True
        if not progress:
            break
    return chosen


def robots_guard(http):
    parsers = {}
    def check(url):
        parts = urlsplit(url)
        if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password:
            raise SourceError("Only public HTTP(S) PDF URLs are supported")
        import ipaddress
        if parts.hostname.casefold() == "localhost" or parts.hostname.endswith(".local"):
            raise SourceError("Local network URLs are not public paper sources")
        try:
            if not ipaddress.ip_address(parts.hostname).is_global:
                raise SourceError("Private network URLs are not public paper sources")
        except ValueError:
            pass
        origin = parts.scheme + "://" + parts.netloc
        if origin not in parsers:
            body = http.get(origin + "/robots.txt", allow_not_found=True, max_bytes=1024 * 1024)
            parser = RobotFileParser()
            parser.parse(body.decode("utf-8", "replace").splitlines())
            parsers[origin] = parser
        parser = parsers[origin]
        if not parser.can_fetch("LeedsMathMap", url):
            raise SourceError("robots.txt disallows retrieval: " + url)
        delay = parser.crawl_delay("LeedsMathMap") or 0
        http.host_delays[parts.netloc] = max(http.host_delays.get(parts.netloc, 0), delay)
    return check


def extract_pdf(body, publication, options=None):
    from pypdf import PdfReader
    options = options or {}
    if not body.lstrip().startswith(b"%PDF-"):
        raise SourceError("The source returned a non-PDF response")
    try:
        reader = PdfReader(io.BytesIO(body), strict=False)
        if reader.is_encrypted:
            raise SourceError("Encrypted PDFs are not extracted")
        if len(reader.pages) > options.get("max_pages", 200):
            raise SourceError("PDF exceeds configured page limit; not silently truncated")
        pages = []
        for number, page in enumerate(reader.pages, 1):
            content = page.get_contents()
            if content and len(content.get_data()) > 10 * 1024 * 1024:
                raise SourceError("PDF page content exceeds extraction size limit")
            text = page.extract_text() or ""
            pages.append({"page": number, "text": text})
    except SourceError:
        raise
    except Exception as exc:
        raise SourceError("PDF extraction failed: " + type(exc).__name__) from None
    front = normalise(" ".join(p["text"] for p in pages[:2]))
    title = {t for t in normalise(publication["title"]).split() if len(t) > 2 and t not in {"the", "and", "for", "with", "from", "mathrm", "mathfrak"}}
    match = sum(t in front.split() for t in title) / len(title) if title else 0
    if match < 0.65:
        raise SourceError(f"PDF title could not be corroborated (token coverage {match:.2f})")
    line_counts = Counter(line.strip() for page in pages for line in set(page["text"].splitlines()) if line.strip())
    repeated = {line for line, n in line_counts.items() if len(pages) >= 4 and n >= max(3, len(pages) * 0.6) and len(line) < 160}
    references, words = False, 0
    for page in pages:
        kept = []
        for line in page["text"].splitlines():
            if words >= 200 and re.fullmatch(r"\s*(?:\d+[. ]+)?(?:references|bibliography|references and notes)\s*", line, re.I):
                references = True
            if references:
                continue
            if line.strip() in repeated or re.fullmatch(r"\s*\d+\s*", line):
                continue
            kept.append(line)
            words += len(line.split())
        text = "\n".join(kept)
        page["analysis_text"] = re.sub(r"([a-z])-\s*\n\s*([a-z])", r"\1\2", text)
    body_words = sum(len(p["analysis_text"].split()) for p in pages)
    text_pages = sum(len(p["text"].strip()) >= 50 for p in pages)
    status = "ready" if body_words >= options.get("min_words", 200) and text_pages >= len(pages) * 0.7 else "needs_ocr_or_review"
    return {"publication_id": publication["id"], "pages": pages, "page_count": len(pages),
            "body_word_count": body_words, "text_pages": text_pages, "status": status,
            "title_token_coverage": round(match, 3), "references_excluded": references,
            "method": EXTRACTOR_VERSION, "extracted_at": utcnow()}


def artifact_key(p):
    return hashlib.sha256(p["id"].encode()).hexdigest()[:24]


@lru_cache(maxsize=512)
def _read_artifact(path, modified):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def document(p):
    meta = p.get("full_text", {})
    if meta.get("status") != "ready":
        return None
    key = artifact_key(p)
    if meta.get("cache_key") != key:
        return None
    path = CACHE_ROOT / (key + ".json")
    try:
        data = _read_artifact(str(path), path.stat().st_mtime_ns)
        if data.get("publication_id") != p["id"] or data.get("sha256") != meta.get("sha256") or data.get("method") != EXTRACTOR_VERSION:
            return None
        return data
    except (OSError, ValueError):
        return None


def body_text(p):
    doc = document(p)
    return "\n".join(page["analysis_text"] for page in doc["pages"]) if doc else ""


def restore_cached_text(publications):
    for p in publications:
        path = CACHE_ROOT / (artifact_key(p) + ".json")
        try:
            data = _read_artifact(str(path), path.stat().st_mtime_ns)
            if data.get("publication_id") == p["id"] and data.get("method") == EXTRACTOR_VERSION:
                p["full_text"] = {k: v for k, v in data.items() if k != "pages"}
        except (OSError, ValueError):
            continue


def retrieve_full_text(publications, researchers, http, options=None, limit=30):
    options = options or {}
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    attach_cached_locations(publications, http.store)
    chosen = balanced_sample(publications, researchers, limit)
    guard, counts = robots_guard(http), Counter()
    for i, p in enumerate(chosen, 1):
        log.info("Full text %d/%d: %s", i, len(chosen), p["title"][:85])
        key = artifact_key(p)
        path = CACHE_ROOT / (key + ".json")
        if path.exists() and not http.refresh:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            if data.get("publication_id") == p["id"] and data.get("method") == EXTRACTOR_VERSION:
                p["full_text"] = {k: v for k, v in data.items() if k != "pages"}
                counts[p["full_text"]["status"]] += 1
                continue
        attempts = []
        for location in candidates(p)[:3]:
            url = location["url"]
            try:
                body = http.get(url, accept="application/pdf", max_bytes=int(options.get("max_pdf_mb", 20) * 1024 * 1024), request_guard=guard)
                data = extract_pdf(body, p, options)
                data.update({"source_url": url, "sha256": hashlib.sha256(body).hexdigest(), "cache_key": key,
                    "license": location.get("license"), "version": location.get("version"),
                    "metadata_source": location.get("metadata_source"), "attempts": attempts,
                    "retrieval": dict(http.events[-1]) if http.events else {},
                    "limitations": "PDF text extraction can lose formulas and reading order; no OCR or theorem inference. Bibliography and content after its heading are excluded from analysis."})
                (CACHE_ROOT / (key + ".pdf")).write_bytes(body)
                dump_json(path, data)
                p["full_text"] = {k: v for k, v in data.items() if k != "pages"}
                break
            except SourceError as exc:
                attempts.append({"source": url, "status": "unavailable_or_rejected", "error": str(exc)})
        else:
            p["full_text"] = {"status": "unavailable", "attempts": attempts, "attempted_at": utcnow()}
        counts[p["full_text"]["status"]] += 1
    return {"attempted": len(chosen), "limit": limit, "status_counts": dict(counts),
            "publication_ids": [p["id"] for p in chosen],
            "selection": "round_robin_by_researcher_recent_first", "requests": http.events,
            "completed_at": utcnow()}
