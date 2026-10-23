"""Local PDF uploads, with immutable files and explicit source provenance."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from . import fulltext
from .core import ROOT, dump_json, utcnow

UPLOAD_ROOT = ROOT / "data/uploads"


def prepare_pdf(body, filename, publication, options=None, for_review=False):
    options = {**(options or {}), "allow_unmatched_title": for_review}
    if not isinstance(body, bytes) or not body:
        raise ValueError("Choose a non-empty PDF file.")
    if len(body) > options.get("max_pdf_mb", 20) * 1024 * 1024:
        raise ValueError("PDF exceeds the configured upload size limit.")
    name = str(filename).replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(c for c in name if ord(c) >= 32).strip()[:180] or "paper.pdf"
    data = fulltext.extract_pdf(body, publication, options)
    sha = hashlib.sha256(body).hexdigest()
    data.update({"origin": "upload", "filename": name, "sha256": sha, "size_bytes": len(body),
                 "source_url": "upload:" + sha, "uploaded_at": utcnow(),
                 "version": "user-supplied; version not independently checked", "license": None,
                 "limitations": "PDF extraction can lose formulas and reading order. Detected references and subsequent content are omitted; no OCR or theorem inference."})
    return data


def save_pdf(body, metadata):
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    target = UPLOAD_ROOT / (metadata["sha256"] + ".pdf")
    with tempfile.NamedTemporaryFile(dir=UPLOAD_ROOT, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(body)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def read_pdf(metadata):
    sha = metadata.get("sha256", "")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
        return None
    try:
        body = (UPLOAD_ROOT / (sha + ".pdf")).read_bytes()
        return body if hashlib.sha256(body).hexdigest() == sha else None
    except OSError:
        return None


def publication_pdf(publication):
    meta = publication.get("full_text", {})
    if meta.get("origin") == "upload":
        return read_pdf(meta)
    if meta.get("cache_key") != fulltext.artifact_key(publication):
        return None
    try:
        body = (fulltext.CACHE_ROOT / (meta["cache_key"] + ".pdf")).read_bytes()
        return body if hashlib.sha256(body).hexdigest() == meta.get("sha256") else None
    except OSError:
        return None


def needs_pdf(publication):
    return not fulltext.document(publication) or publication_pdf(publication) is None


def summary(document):
    return {k: v for k, v in document.items() if k != "pages"}


def ingest_pdf(store, publication_id, body, filename, options=None):
    """Check a supplied paper and rebuild analysis without changing authorship."""
    from .pipeline import analyse
    from .report import write_reports
    original = store.load()
    p = next((p for p in (original or {}).get("publications", []) if p["id"] == publication_id), None)
    if not p or not fulltext.eligible(p):
        raise ValueError("Choose a publication with corroborated authorship that is eligible for analysis.")
    expected_title = p["title"]
    data = prepare_pdf(body, filename, p, options)
    key = fulltext.artifact_key(p)
    data.update(cache_key=key, metadata_source=p["url"])
    path = fulltext.CACHE_ROOT / (key + ".json")
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT payload FROM snapshots WHERE id=1").fetchone()
        current = json.loads(row[0]) if row else original
        p = next((p for p in current["publications"] if p["id"] == publication_id), None)
        if not p or not fulltext.eligible(p) or p["title"] != expected_title:
            raise ValueError("The publication changed while uploading. Select it again.")
        if fulltext.document(p):
            if p["full_text"].get("sha256") == data["sha256"]:
                if p["full_text"].get("origin") == "upload":
                    save_pdf(body, p["full_text"])
                else:
                    fulltext.CACHE_ROOT.mkdir(parents=True, exist_ok=True)
                    (fulltext.CACHE_ROOT / (key + ".pdf")).write_bytes(body)
                return p["full_text"]
            if publication_pdf(p) is not None:
                raise ValueError("This paper already has usable full text. Choose a paper whose PDF is missing.")
        old = path.read_bytes() if path.exists() else None
        try:
            save_pdf(body, data)
            dump_json(path, data)
            p["full_text"] = summary(data)
            metadata = dict(current.get("collection", {}))
            metadata["uploads"] = [*metadata.get("uploads", []), {"publication_id": publication_id,
                "sha256": data["sha256"], "filename": data["filename"], "status": data["status"], "at": data["uploaded_at"]}]
            updated = analyse(current["researchers"], current["publications"], metadata,
                              current.get("analysis", {}).get("include_full_text", True))
            db.execute("INSERT OR REPLACE INTO snapshots VALUES (1,?,?)", (json.dumps(updated, ensure_ascii=False), utcnow()))
        except BaseException:
            if old is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old)
            fulltext._read_artifact.cache_clear()
            raise
    # Export the latest committed snapshot under the same writer lock, so another
    # upload cannot cause an older portable snapshot to overwrite a newer one.
    try:
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            latest = json.loads(db.execute("SELECT payload FROM snapshots WHERE id=1").fetchone()[0])
            dump_json(store.path.parent / "snapshot.json", latest)
            write_reports(latest, store.reviews(), store.path.parent.parent / "reports")
    except OSError as exc:
        return {**summary(data), "export_warning": f"PDF saved and analysed; report export failed: {exc}"}
    return summary(data)
