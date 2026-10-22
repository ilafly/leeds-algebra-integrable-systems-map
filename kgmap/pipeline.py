from __future__ import annotations

import logging
from collections import defaultdict

from .concepts import extract_concepts, related_concepts
from .connections import discover_connections
from .core import normalise, utcnow
from .http import SourceError
from .sources import (IdentityError, deduplicate, enrich_arxiv, enrich_crossref,
                      resolve_identity, retrieve_publications)

log = logging.getLogger(__name__)


def analyse(researchers, publications, metadata=None):
    title_groups = defaultdict(list)
    for p in publications:
        title_groups[normalise(p["title"])].append(p["id"])
    metadata = dict(metadata or {})
    metadata["possible_duplicate_title_groups"] = [ids for ids in title_groups.values() if len(ids) > 1]
    concepts, mentions = extract_concepts(publications, researchers)
    relations = related_concepts(concepts, mentions)
    connections = discover_connections(researchers, publications, concepts, mentions, relations)
    return {"schema_version": 1, "generated_at": utcnow(), "data_kind": "retrieved_public_metadata",
            "researchers": researchers, "publications": publications, "concepts": concepts,
            "mentions": mentions, "concept_relations": relations, "connections": connections,
            "collection": metadata}


def collect(config, http, skip_enrichment=False):
    researchers, publications, issues, counts = [], [], [], {}
    for person in config["researchers"]:
        log.info("Verifying %s", person["name"])
        try:
            identity = resolve_identity(http, person)
        except (SourceError, IdentityError) as exc:
            identity = {**person, "status": "needs_review", "openalex_id": None,
                        "verified_orcid": None, "reason": str(exc), "profile": {"sources": []}}
        researchers.append(identity)
        if identity["status"] != "verified":
            issues.append({"researcher": person["id"], "stage": "identity", "error": identity["reason"]})
            log.warning("Identity needs review: %s — %s", person["name"], identity["reason"])
            continue
        try:
            records = retrieve_publications(http, identity, config["collection"].get("max_publications", 40))
            counts[person["id"]] = len(records)
            publications.extend(records)
            log.info("Retrieved %d publication records for %s", len(records), person["name"])
        except (SourceError, IdentityError) as exc:
            issues.append({"researcher": person["id"], "stage": "publications", "error": str(exc)})
    pilot_author_ids = {r["openalex_id"]: r["id"] for r in researchers if r.get("status") == "verified"}
    for p in publications:
        p["researcher_ids"] = sorted(set(p["researcher_ids"]) |
            {pilot_author_ids[a["openalex_id"]] for a in p["authors"] if a.get("openalex_id") in pilot_author_ids})
    publications = deduplicate(publications)
    if not skip_enrichment:
        for i, p in enumerate(publications):
            for enabled, provider, method in [
                (config["collection"].get("arxiv_enrichment", True), "arXiv", enrich_arxiv),
                (config["collection"].get("crossref_enrichment", True), "Crossref", enrich_crossref),
            ]:
                if not enabled:
                    continue
                if provider == "arXiv" and not p.get("arxiv_id"):
                    continue
                if provider == "Crossref" and (not p.get("doi") or p["doi"].startswith("10.48550/arxiv.")):
                    continue
                log.info("Enriching %d/%d: %s — %s", i + 1, len(publications), provider, p["title"][:65])
                try:
                    method(http, p)
                except SourceError as exc:
                    issues.append({"publication": p["id"], "stage": provider, "error": str(exc)})
        publications = deduplicate(publications)
    return analyse(researchers, publications, {"counts_before_deduplication": counts,
        "requested_per_researcher": config["collection"].get("max_publications", 40),
        "enrichment_skipped": skip_enrichment, "issues": issues, "requests": http.events})
