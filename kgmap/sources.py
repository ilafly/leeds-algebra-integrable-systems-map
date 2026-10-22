from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from .core import arxiv_key, doi_key, normalise, normalise_name, stable_id, utcnow
from .http import SourceError

OPENALEX = "https://api.openalex.org"
ORCID_RE = re.compile(r"\d{4}-\d{4}-\d{4}-[\dX]{4}")


class IdentityError(ValueError):
    pass


def strip_markup(text):
    return BeautifulSoup(text or "", "html.parser").get_text(" ", strip=True)


def abstract_from_index(index):
    if not index:
        return ""
    positions = {i: word for word, offsets in index.items() for i in offsets}
    return " ".join(positions[i] for i in sorted(positions))


def fetch_page(http, url):
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        parser = RobotFileParser()
        parser.parse(http.get(robots_url, allow_not_found=True).decode("utf-8", "replace").splitlines())
        if not parser.can_fetch("LeedsMathMap", url):
            raise SourceError("robots.txt disallows automated retrieval: " + url)
    except SourceError as exc:
        # Missing robots.txt is normal; other failures are recorded by CachedHTTP.
        if "disallows" in str(exc):
            raise
        if "404" not in str(exc):
            raise SourceError("Could not check robots.txt for " + url + ": " + str(exc)) from None
    return BeautifulSoup(http.get(url).decode("utf-8", "replace"), "html.parser")


def profile_record(http, person):
    """Read only linked public profiles. No search-engine snippet ingestion."""
    result = {"sources": [], "descriptions": [], "linked_orcids": [], "identity_confirmed": False}
    urls = list(dict.fromkeys(u for u in [person.get("profile_url"), person.get("homepage_url")] if u))
    aliases = [normalise_name(n) for n in [person["name"], *person.get("aliases", [])]]
    for url in urls:
        try:
            soup = fetch_page(http, url)
            for unwanted in soup(["script", "style", "nav", "footer", "header"]):
                unwanted.decompose()
            main = soup.find("main") or soup
            text = main.get_text(" ", strip=True)
            headings = " ".join(h.get_text(" ", strip=True) for h in soup.find_all(["title", "h1", "h2", "h3"]))
            own_name = any(alias and alias in normalise_name(headings) for alias in aliases)
            affiliation = normalise(person["affiliation"]) in normalise(text + " " + headings)
            confirmed = own_name and affiliation
            orcids = sorted(set(m.group() for a in main.find_all("a", href=True)
                                 if "orcid.org/" in a["href"] for m in ORCID_RE.finditer(a["href"])))
            result["sources"].append({"url": url, "status": "retrieved", "identity_confirmed": confirmed,
                                      "name_in_heading": own_name, "affiliation_found": affiliation,
                                      "linked_orcids": orcids, "retrieved_at": utcnow()})
            if confirmed:
                result["identity_confirmed"] = True
                result["linked_orcids"].extend(orcids)
                # Never treat a collaborator's profile as this researcher's profile.
                for a in main.find_all("a", href=True):
                    link = urljoin(url, a["href"])
                    if "eps.leeds.ac.uk/maths/staff/" in link and not person.get("profile_url"):
                        if "staff profile" in a.get_text(" ", strip=True).casefold():
                            person["profile_url"] = link
                            if link not in urls:
                                urls.append(link)
                for heading in main.find_all(["h2", "h3", "h4"]):
                    if any(k in heading.get_text(" ", strip=True).casefold() for k in ["research interest", "areas of expertise"]):
                        chunks = []
                        for sibling in heading.next_siblings:
                            if getattr(sibling, "name", "") in {"h1", "h2", "h3", "h4"}:
                                break
                            chunks.append(sibling.get_text(" ", strip=True) if hasattr(sibling, "get_text") else str(sibling).strip())
                        description = " ".join(chunks).strip()
                        if description:
                            result["descriptions"].append({"text": description[:6000], "source": url, "field": "research_description"})
        except SourceError as exc:
            result["sources"].append({"url": url, "status": "unavailable", "error": str(exc)})
    result["linked_orcids"] = sorted(set(result["linked_orcids"]))
    return result


def corroborate_orcid(http, person, profile):
    """Use public names AND employment evidence when an HTML profile is missing.

    Historical employment verifies identity, not a claim of current affiliation.
    The configured identifier on its own remains insufficient.
    """
    orcid = person.get("orcid")
    if not orcid or profile.get("linked_orcids"):
        return profile
    url = f"https://pub.orcid.org/v3.0/{orcid}"
    try:
        record = http.json(url + "/person")
        names = record.get("name") or {}
        primary = " ".join((names.get(part) or {}).get("value", "") for part in ["given-names", "family-name"])
        public_names = [primary, (names.get("credit-name") or {}).get("value", "")]
        public_names += [n.get("content", "") for n in record.get("other-names", {}).get("other-name", [])]
        configured_names = {normalise_name(n) for n in [person["name"], *person.get("aliases", [])]}
        name_match = any(normalise_name(n) in configured_names for n in public_names if n)
        employment_record = http.json(url + "/employments")
        employments = employment_record.get("employment-summary", [])[:]
        for group in employment_record.get("affiliation-group", []):
            for summary in group.get("summaries", []):
                if summary.get("employment-summary"):
                    employments.append(summary["employment-summary"])
        matches = [e for e in employments if normalise(e.get("organization", {}).get("name")) == normalise(person["affiliation"])]
        confirmed = name_match and bool(matches)
        profile["sources"].append({"url": url + "/person", "employment_url": url + "/employments",
            "status": "retrieved", "identity_confirmed": confirmed, "name_match": name_match,
            "affiliation_found": bool(matches), "method": "public_orcid_name_and_employment",
            "employment_evidence": matches, "retrieved_at": utcnow()})
        if confirmed:
            profile["identity_confirmed"] = True
            profile["linked_orcids"] = sorted(set(profile.get("linked_orcids", [])) | {orcid})
            profile["orcid_confirmation_method"] = "public_orcid_name_and_employment"
    except SourceError as exc:
        profile["sources"].append({"url": url, "status": "unavailable", "error": str(exc)})
    return profile


def candidate_matches(candidate, person, profile):
    names = {normalise_name(n) for n in [person["name"], *person.get("aliases", [])] if normalise_name(n)}
    name_match = bool(normalise_name(candidate.get("display_name"))) and normalise_name(candidate.get("display_name")) in names
    institutions = list(candidate.get("last_known_institutions") or [])
    institutions += [a.get("institution", {}) for a in candidate.get("affiliations", [])]
    leeds = any(normalise(i.get("display_name")) == normalise(person["affiliation"]) for i in institutions)
    candidate_orcid = (candidate.get("orcid") or "").rsplit("/", 1)[-1]
    linked = set(profile.get("linked_orcids", []))
    expected = person.get("orcid")
    # Conflicting identifiers must never be overridden by an affiliation match.
    if expected and candidate_orcid and expected != candidate_orcid:
        return False, "ORCID conflict"
    if linked and candidate_orcid and candidate_orcid not in linked:
        return False, "ORCID conflicts with linked profile"
    if not name_match:
        return False, "Name does not match configured aliases"
    if candidate_orcid and candidate_orcid in linked and profile.get("identity_confirmed"):
        return True, "Exact ORCID corroborated by public researcher evidence; matching name"
    if profile.get("identity_confirmed") and leeds:
        return True, "Unique exact name/alias and Leeds affiliation, corroborated by researcher page"
    return False, "Insufficient independent identity evidence"


def select_identity(candidates, person, profile):
    evaluated = []
    matching = []
    for candidate in candidates:
        ok, reason = candidate_matches(candidate, person, profile)
        evaluated.append({"id": candidate.get("id"), "name": candidate.get("display_name"),
                          "orcid": candidate.get("orcid"), "eligible": ok, "reason": reason})
        if ok:
            matching.append((candidate, reason))
    if len(matching) != 1:
        raise IdentityError(json.dumps({"message": "Ambiguous identity" if matching else "Unverified identity",
                                       "candidates": evaluated}, ensure_ascii=False))
    return matching[0][0], matching[0][1], evaluated


def resolve_identity(http, person):
    person = dict(person)
    profile = corroborate_orcid(http, person, profile_record(http, person))
    candidates = {}
    linked = profile["linked_orcids"]
    # Query by confirmed ORCID first; name search handles missing or split clusters.
    if len(linked) == 1:
        try:
            candidate = http.json(f"{OPENALEX}/authors/https://orcid.org/{linked[0]}")
            candidates[candidate["id"]] = candidate
        except SourceError:
            pass
    for name in dict.fromkeys([person["name"], *person.get("aliases", [])]):
        if len(normalise(name).split()) < 2 or re.search(r"\b[A-Z]\.", name):
            continue
        data = http.json(f"{OPENALEX}/authors", {"search": name, "per-page": 25})
        for candidate in data.get("results", []):
            candidates[candidate["id"]] = candidate
    try:
        candidate, basis, evaluated = select_identity(list(candidates.values()), person, profile)
    except IdentityError as exc:
        return {**person, "status": "needs_review", "reason": str(exc), "profile": profile,
                "openalex_id": None, "verified_orcid": None}
    orcid = (candidate.get("orcid") or "").rsplit("/", 1)[-1] or None
    orcid_status = "not_available"
    if orcid:
        try:
            http.get(f"https://pub.orcid.org/v3.0/{orcid}/person", accept="application/json")
            orcid_status = "retrieved"
        except SourceError as exc:
            orcid_status = "unavailable: " + str(exc)
    work_ids = {"doi": [], "arxiv": []}
    if person.get("require_publication_corroboration") and orcid in linked:
        url = f"https://pub.orcid.org/v3.0/{orcid}/works"
        try:
            works = http.json(url)
            dois, arxiv_ids = set(), set()
            for group in works.get("group", []):
                containers = [group.get("external-ids", {})]
                containers += [w.get("external-ids", {}) for w in group.get("work-summary", [])]
                for container in containers:
                    for identifier in container.get("external-id", []):
                        if identifier.get("external-id-relationship") == "part-of":
                            continue
                        value = identifier.get("external-id-value", "")
                        if identifier.get("external-id-type", "").lower() == "doi" and doi_key(value):
                            dois.add(doi_key(value))
                        if arxiv_key(value):
                            arxiv_ids.add(arxiv_key(value))
            work_ids = {"doi": sorted(dois), "arxiv": sorted(arxiv_ids)}
            profile["sources"].append({"url": url, "status": "retrieved", "method": "public_orcid_bibliography",
                "doi_count": len(dois), "arxiv_count": len(arxiv_ids), "retrieved_at": utcnow()})
        except SourceError as exc:
            profile["sources"].append({"url": url, "status": "unavailable", "error": str(exc)})
    return {**person, "status": "verified", "reason": basis, "profile": profile,
            "openalex_id": candidate["id"], "verified_orcid": orcid if orcid in linked else None,
            "reported_orcid": orcid,
            "orcid_basis": profile.get("orcid_confirmation_method", "linked_from_confirmed_researcher_page") if orcid in linked else "OpenAlex_reported_not_independently_corroborated",
            "orcid_status": orcid_status, "candidates": evaluated,
            "openalex_works_count": candidate.get("works_count"), "corroborated_work_ids": work_ids,
            "verified_at": utcnow()}


def openalex_publication(work, researcher_id):
    abstract = abstract_from_index(work.get("abstract_inverted_index"))
    doi = doi_key(work.get("doi"))
    urls = [loc.get("landing_page_url") for loc in work.get("locations", []) if loc.get("landing_page_url")]
    arxiv = next((arxiv_key(u) for u in urls if arxiv_key(u)), None) or arxiv_key(work.get("doi"))
    pid = "doi:" + doi if doi else ("arxiv:" + arxiv if arxiv else work["id"])
    return {"id": pid, "title": work.get("title") or work.get("display_name") or "[Untitled]",
            "abstract": abstract, "authors": [{"name": a["author"].get("display_name", ""),
                "openalex_id": a["author"].get("id"), "orcid": a["author"].get("orcid"),
                "affiliations": [i.get("display_name") for i in a.get("institutions", [])]} for a in work.get("authorships", [])],
            "date": work.get("publication_date"), "year": work.get("publication_year"),
            "doi": doi, "doi_aliases": [doi] if doi else [], "arxiv_id": arxiv, "openalex_ids": [work["id"]],
            "full_text_locations": [{"url": loc["pdf_url"], "license": loc.get("license"), "version": loc.get("version"),
                "is_oa": True, "metadata_source": work["id"]} for loc in work.get("locations", []) if loc.get("is_oa") and loc.get("pdf_url")],
            "url": "https://doi.org/" + doi if doi else (urls[0] if urls else work["id"]),
            "urls": list(dict.fromkeys([work["id"], *urls])), "researcher_ids": [researcher_id],
            "type": work.get("type"), "is_retracted": work.get("is_retracted", False),
            "licenses": list({loc["license"] for loc in work.get("locations", []) if loc.get("license")}),
            "provenance": [{"source": work["id"], "provider": "OpenAlex", "retrieved_at": utcnow(),
                            "fields": ["title", "abstract", "authors", "date", "doi", "urls"],
                            "method": "author_id_filtered_metadata", "metadata_license": "CC0"}]}


def retrieve_publications(http, identity, limit=40):
    if identity.get("status") != "verified":
        raise IdentityError("Publication collection requires a verified identity")
    records = []
    cursor = "*"
    while len(records) < limit:
        data = http.json(f"{OPENALEX}/works", {"filter": "author.id:" + identity["openalex_id"],
            "sort": "publication_date:desc", "per-page": min(200, limit - len(records)), "cursor": cursor})
        works = data.get("results", [])
        if not works:
            break
        for work in works:
            if identity["openalex_id"] not in [a.get("author", {}).get("id") for a in work.get("authorships", [])]:
                raise IdentityError("OpenAlex returned a publication without the verified author ID")
            records.append(openalex_publication(work, identity["id"]))
        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
    return records[:limit]


def enrich_crossref(http, publication):
    if not publication.get("doi"):
        return
    from urllib.parse import quote
    url = "https://api.crossref.org/works/" + quote(publication["doi"], safe="")
    message = http.json(url)["message"]
    if doi_key(message.get("DOI")) != publication["doi"]:
        raise SourceError("Crossref DOI mismatch: " + url)
    fields = []
    if not publication["abstract"] and message.get("abstract"):
        publication["abstract"] = strip_markup(message["abstract"])
        fields.append("abstract")
    publication["crossref"] = {"title": message.get("title", []), "type": message.get("type"),
        "publisher": message.get("publisher"), "licenses": message.get("license", []),
        "authors": message.get("author", [])}
    publication["provenance"].append({"source": url, "provider": "Crossref", "fields": ["crossref", *fields],
                                      "method": "exact_doi_lookup", "retrieved_at": utcnow()})


def prefetch_arxiv(http, publications, batch_size=25):
    """Batch uncached exact IDs, retaining the existing individual-response cache."""
    url = "https://export.arxiv.org/api/query"
    ids = sorted({p["arxiv_id"] for p in publications if p.get("arxiv_id")
                  and not http.is_cached(url, {"id_list": p["arxiv_id"]}, "application/atom+xml")})
    responses, issues = {}, []
    for start in range(0, len(ids), batch_size):
        batch = ids[start:start + batch_size]
        try:
            body = http.get(url, {"id_list": ",".join(batch), "max_results": len(batch)}, "application/atom+xml")
            root = ET.fromstring(body)
            found = {arxiv_key(entry.findtext("{http://www.w3.org/2005/Atom}id", ""))
                     for entry in root.findall("{http://www.w3.org/2005/Atom}entry")}
            for aid in batch:
                responses[aid] = body if aid in found else None
                if aid not in found:
                    issues.append({"stage": "arXiv", "arxiv_id": aid, "error": "Exact identifier missing from batch response"})
        except (SourceError, ET.ParseError) as exc:
            issues.append({"stage": "arXiv", "arxiv_ids": batch, "error": str(exc)})
            responses.update({aid: None for aid in batch})
    return responses, issues


def enrich_arxiv(http, publication, response_xml=None):
    aid = publication.get("arxiv_id")
    # Only use a source-supplied exact identifier, never an author-name search.
    if not aid:
        return
    url = "https://export.arxiv.org/api/query"
    body = response_xml if response_xml is not None else http.get(url, {"id_list": aid}, "application/atom+xml")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise SourceError("Invalid arXiv XML: " + str(exc)) from None
    ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
    for entry in root.findall("a:entry", ns):
        if arxiv_key(entry.findtext("a:id", "", ns)) != aid:
            continue
        abstract = " ".join(entry.findtext("a:summary", "", ns).split())
        fields = ["arxiv"]
        if not publication["abstract"] and abstract:
            publication["abstract"] = abstract
            fields.append("abstract")
        publication["arxiv"] = {"id": aid, "published": entry.findtext("a:published", "", ns),
                                 "doi": doi_key(entry.findtext("x:doi", "", ns))}
        journal_doi = publication["arxiv"]["doi"]
        if journal_doi:
            publication["doi_aliases"] = sorted(set(publication.get("doi_aliases", [])) | {journal_doi})
            fields.append("doi_aliases")
            if not publication.get("doi") or publication["doi"].startswith("10.48550/arxiv."):
                publication["doi"] = journal_doi
                publication["url"] = "https://doi.org/" + journal_doi
                fields.append("doi")
        publication["provenance"].append({"source": f"https://arxiv.org/abs/{aid}", "provider": "arXiv",
            "fields": fields, "method": "exact_arxiv_id_lookup", "retrieved_at": utcnow()})


def deduplicate(records):
    """Transitive identifier union; title equality alone never merges publications."""
    parent = list(range(len(records)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen = {}
    for i, p in enumerate(records):
        keys = ["doi:" + doi_key(p["doi"])] if doi_key(p.get("doi")) else []
        keys.extend("doi:" + doi_key(d) for d in p.get("doi_aliases", []) if doi_key(d))
        if p.get("arxiv_id"):
            keys.append("arxiv:" + p["arxiv_id"])
        keys.extend(p.get("openalex_ids", []))
        keys.append(p["id"])
        for key in keys:
            if key in seen:
                parent[find(i)] = find(seen[key])
            seen[key] = i
    groups = {}
    for i, p in enumerate(records):
        groups.setdefault(find(i), []).append(p)
    merged = []
    for group in groups.values():
        p = json.loads(json.dumps(group[0]))
        p["doi"] = doi_key(p.get("doi"))
        p["doi_aliases"] = sorted({doi_key(d) for item in group for d in [item.get("doi"), *item.get("doi_aliases", [])] if doi_key(d)})
        journal_dois = [d for d in p["doi_aliases"] if not d.startswith("10.48550/arxiv.")]
        if journal_dois and (not p["doi"] or p["doi"].startswith("10.48550/arxiv.")):
            p["doi"] = journal_dois[0]
            p["url"] = "https://doi.org/" + p["doi"]
        p["manifestations"] = []
        for item in group:
            versions = item.get("manifestations") or [{k: item.get(k) for k in ("id", "title", "date", "doi", "arxiv_id", "url")}]
            p["manifestations"].extend(v for v in versions if v not in p["manifestations"])
        for other in group[1:]:
            for loc in other.get("full_text_locations", []):
                if loc not in p.setdefault("full_text_locations", []):
                    p["full_text_locations"].append(loc)
            for field in ["researcher_ids", "openalex_ids", "urls"]:
                p[field] = list(dict.fromkeys([*p.get(field, []), *other.get(field, [])]))
            p["provenance"].extend(e for e in other.get("provenance", []) if e not in p["provenance"])
            for field in ["abstract", "doi", "arxiv_id"]:
                if not p.get(field) and other.get(field):
                    p[field] = doi_key(other[field]) if field == "doi" else other[field]
        p["id"] = "doi:" + p["doi"] if p.get("doi") else ("arxiv:" + p["arxiv_id"] if p.get("arxiv_id") else p["id"])
        merged.append(p)
    return sorted(merged, key=lambda p: (p.get("date") or "", p["id"]), reverse=True)


def corroborate_authorships(publications, researchers):
    """Quarantine assignments in explicitly flagged, contaminated author clusters.

    Absence from a bibliography is uncertainty, never proof of non-authorship.
    Other independently resolved pilot authors on the same work are retained.
    """
    strict = {r["id"]: r for r in researchers if r.get("require_publication_corroboration")}
    issues = []
    for p in publications:
        reviews = []
        for rid in list(p["researcher_ids"]):
            if rid not in strict:
                continue
            r = strict[rid]
            corroborated = r.get("corroborated_work_ids", {})
            dois = {doi_key(d) for d in [p.get("doi"), *p.get("doi_aliases", [])] if doi_key(d)}
            orcid = r.get("verified_orcid")
            bibliography = bool(dois & set(corroborated.get("doi", []))) or bool(p.get("arxiv_id") and p["arxiv_id"] in corroborated.get("arxiv", []))
            publisher = bool(orcid and any((a.get("ORCID") or "").rsplit("/", 1)[-1] == orcid for a in p.get("crossref", {}).get("authors", [])))
            if bibliography or publisher:
                reviews.append({"researcher_id": rid, "status": "corroborated",
                    "method": "public_ORCID_bibliography" if bibliography else "exact_publisher_ORCID",
                    "source": f"https://pub.orcid.org/v3.0/{orcid}/works" if bibliography else p["url"]})
            else:
                note = "Author cluster is flagged for namesake contamination; this assignment has no matching public ORCID work identifier or exact publisher ORCID. Awaiting authorship review; not proof of non-authorship."
                p["researcher_ids"].remove(rid)
                p.setdefault("unverified_researcher_ids", []).append(rid)
                reviews.append({"researcher_id": rid, "status": "needs_review", "method": "contaminated_cluster_authorship_check",
                                "source": p["url"], "evidence": note})
                issues.append({"stage": "publication_authorship_review", "researcher": rid,
                               "publication": p["id"], "source": p["url"], "error": note})
        if reviews:
            p["authorship_reviews"] = reviews
        p["quarantined"] = not bool(p["researcher_ids"])
    return issues
