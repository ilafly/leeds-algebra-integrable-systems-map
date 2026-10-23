"""Validation for contributed corrections and missing research evidence."""
from __future__ import annotations

from urllib.parse import quote, urlsplit

from .core import doi_key

KINDS = {"joint_work": "Joint work", "missing_paper": "Missing paper",
         "connection": "Topic or connection", "correction": "Correction", "other": "Other"}
STATUSES = {"pending": "Pending", "in_review": "Under review", "accepted": "Accepted for follow-up",
            "resolved": "Resolved", "rejected": "Rejected"}


def text_field(data, key, maximum, required=False):
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ValueError(key.replace("_", " ").capitalize() + " must be text.")
    value = value.strip()
    if required and not value:
        raise ValueError("Please provide a " + key.replace("_", " ") + ".")
    if len(value) > maximum:
        raise ValueError(key.replace("_", " ").capitalize() + f" must be at most {maximum} characters.")
    return value


def source_link(source):
    if not source:
        return "", None
    doi = doi_key(source)
    if doi:
        return "https://doi.org/" + quote(doi, safe="/():;.-_"), doi
    try:
        parsed = urlsplit(source)
        valid = parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username and not parsed.password
        valid = valid and not any(c.isspace() or ord(c) < 32 for c in source)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Use a full HTTP(S) source URL or a DOI such as 10.1234/example.")
    return source, None


def validate_suggestion(data, snapshot):
    kind = data.get("kind")
    if kind not in KINDS:
        raise ValueError("Choose a suggestion type.")
    title = text_field(data, "title", 240, required=True)
    note = text_field(data, "note", 5000, required=True)
    submitter = text_field(data, "submitter", 120)
    people = {r["id"]: r["name"] for r in snapshot.get("researchers", [])}
    ids = data.get("researcher_ids", [])
    if not isinstance(ids, list) or any(not isinstance(rid, str) or rid not in people for rid in ids):
        raise ValueError("Select researchers from this map.")
    ids = list(dict.fromkeys(ids))
    if kind == "joint_work" and len(ids) < 2:
        raise ValueError("Select at least two researchers for a joint-work suggestion.")
    if kind in {"missing_paper", "connection"} and not ids:
        raise ValueError("Select at least one researcher for this suggestion.")
    publication_id = data.get("publication_id") or None
    pubs = {p["id"]: p for p in snapshot.get("publications", [])}
    if publication_id is not None and (not isinstance(publication_id, str) or publication_id not in pubs):
        raise ValueError("The selected paper is no longer in this map.")
    publication = pubs.get(publication_id, {})
    source = text_field(data, "source", 2000) or publication.get("url", "")
    url, doi = source_link(source)
    if kind == "joint_work" and not url:
        raise ValueError("Add a source URL or DOI, or select an existing paper, for the joint work.")
    return {"kind": kind, "title": title, "note": note, "researcher_ids": ids,
            "researcher_names": {rid: people[rid] for rid in ids},
            "publication_id": publication_id, "publication_title": publication.get("title"),
            "source_url": url, "doi": doi, "submitter": submitter}
