import pytest

from kgmap.core import arxiv_key, doi_key, normalise_name
from kgmap.sources import (IdentityError, abstract_from_index, corroborate_authorships, corroborate_orcid, deduplicate,
                           enrich_arxiv, openalex_publication, prefetch_arxiv, retrieve_publications, select_identity)
from conftest import paper


PERSON = {"id": "test", "name": "Paul Martin", "aliases": ["Paul Purdon Martin"],
          "affiliation": "University of Leeds", "orcid": "0000-0000-0000-0001"}
PROFILE = {"identity_confirmed": True, "linked_orcids": ["0000-0000-0000-0001"]}


def candidate(aid="A1", orcid="0000-0000-0000-0001", institution="University of Leeds"):
    return {"id": aid, "display_name": "Paul Martin", "orcid": "https://orcid.org/" + orcid,
            "last_known_institutions": [{"display_name": institution}]}


def test_exact_orcid_excludes_namesake():
    selected, reason, evaluations = select_identity([candidate(), candidate("A2", "0000-0000-0000-0002")], PERSON, PROFILE)
    assert selected["id"] == "A1"
    assert not evaluations[1]["eligible"]


def test_ambiguous_identity_stops():
    with pytest.raises(IdentityError, match="Ambiguous"):
        select_identity([candidate(), candidate("A2")], PERSON, PROFILE)


def test_explicit_cyrillic_alias_is_distinct_from_other_names():
    person = {**PERSON, "name": "Alexander Mikhailov", "aliases": ["А. В. Михайлов"]}
    correct, wrong = candidate(), candidate("A2")
    correct["display_name"], wrong["display_name"] = "А. В. Михайлов", "Б. Б. Другой"
    selected, _, evaluations = select_identity([correct, wrong], person, PROFILE)
    assert selected["id"] == "A1"
    assert not evaluations[1]["eligible"]
    assert normalise_name("А. В. Михайлов")
    assert normalise_name("А. В. Михайлов") != normalise_name("Б. Б. Другой")


def test_configured_id_alone_is_not_verification():
    with pytest.raises(IdentityError, match="Unverified"):
        select_identity([candidate()], PERSON, {"identity_confirmed": False, "linked_orcids": []})


@pytest.mark.parametrize("name,institution,confirmed", [
    ("Paul Martin", "University of Leeds", True),
    ("Different Person", "University of Leeds", False),
    ("Paul Martin", "Different University", False),
])
def test_public_orcid_fallback_requires_name_and_employment(name, institution, confirmed):
    class FakeHTTP:
        def json(self, url):
            if url.endswith("/person"):
                given, family = name.split(" ", 1)
                return {"name": {"given-names": {"value": given}, "family-name": {"value": family}}}
            return {"affiliation-group": [{"summaries": [{"employment-summary": {
                "organization": {"name": institution}, "end-date": {"year": {"value": "2024"}}}}]}]}
    profile = corroborate_orcid(FakeHTTP(), PERSON, {"identity_confirmed": False, "linked_orcids": [], "sources": []})
    assert profile["identity_confirmed"] is confirmed
    assert bool(profile["linked_orcids"]) is confirmed
    if institution == "University of Leeds":
        assert profile["sources"][0]["employment_evidence"][0]["end-date"]["year"]["value"] == "2024"
    if confirmed:
        assert profile["orcid_confirmation_method"] == "public_orcid_name_and_employment"


def test_wrong_affiliation_and_no_corroborated_orcid():
    p = {k: v for k, v in PERSON.items() if k != "orcid"}
    with pytest.raises(IdentityError):
        select_identity([candidate(institution="Different University")], p, {"identity_confirmed": True, "linked_orcids": []})


def test_abstract_positions_not_dict_order():
    assert abstract_from_index({"equation": [2], "Yang": [0], "Baxter": [1]}) == "Yang Baxter equation"
    assert abstract_from_index(None) == ""


def test_identifier_normalisation():
    assert doi_key("https://doi.org/10.1234/TEST") == "10.1234/test"
    assert doi_key("not-a-doi") is None
    assert arxiv_key("https://arxiv.org/abs/2305.03182v2") == "2305.03182"
    assert arxiv_key("https://arxiv.org/abs/math/0309162") == "math/0309162"
    assert arxiv_key("https://doi.org/10.48550/arXiv.2512.17830") == "2512.17830"


def test_doi_dedup_merges_authorship_and_keeps_provenance():
    a, b = paper("p1", ["test-a"]), paper("p2", ["test-b"])
    a["doi"], b["doi"] = "10.1234/one", "https://doi.org/10.1234/ONE"
    merged = deduplicate([a, b])
    assert len(merged) == 1
    assert set(merged[0]["researcher_ids"]) == {"test-a", "test-b"}
    assert len(merged[0]["provenance"]) == 2


def test_equal_titles_without_identifiers_remain_separate():
    assert len(deduplicate([paper("p1", ["test-a"]), paper("p2", ["test-b"])])) == 2


def test_transitive_identifiers_merge():
    a, b, c = paper("p1", ["a"]), paper("p2", ["b"]), paper("p3", ["c"])
    a["doi"] = b["doi"] = "10.1234/one"
    b["arxiv_id"] = c["arxiv_id"] = "2305.03182"
    assert len(deduplicate([a, b, c])) == 1


def test_journal_doi_alias_merges_manifestations():
    a, b = paper("p1", ["a"]), paper("p2", ["b"])
    a["doi"], b["doi"] = "10.48550/arxiv.2305.03182", "10.1234/journal"
    a["doi_aliases"] = [a["doi"], b["doi"]]
    merged = deduplicate([a, b])
    assert len(merged) == 1
    assert set(merged[0]["doi_aliases"]) == {a["doi"], b["doi"]}


def test_unverified_identity_never_queries_api():
    with pytest.raises(IdentityError):
        retrieve_publications(None, {"status": "needs_review"})


def test_wrong_author_id_in_publication_stops_collection():
    class FakeHTTP:
        def json(self, *args):
            return {"results": [{"authorships": [{"author": {"id": "wrong"}}]}]}
    with pytest.raises(IdentityError, match="without the verified author"):
        retrieve_publications(FakeHTTP(), {"status": "verified", "openalex_id": "right", "id": "test"})


def test_batched_arxiv_preserves_cached_ids_and_matches_exact_records():
    records = [paper("p1", ["a"]), paper("p2", ["b"]), paper("p3", ["c"])]
    ids = ["2301.00001", "2301.00002", "2301.00003"]
    for p, aid in zip(records, ids):
        p["arxiv_id"], p["abstract"] = aid, ""
    class FakeHTTP:
        def __init__(self):
            self.calls = []
        def is_cached(self, url, params, accept):
            return params["id_list"] == ids[0]
        def get(self, url, params, accept):
            self.calls.append(params)
            return ('<feed xmlns="http://www.w3.org/2005/Atom">' + ''.join(
                f'<entry><id>https://arxiv.org/abs/{aid}v2</id><summary>Abstract {aid}</summary></entry>'
                for aid in params["id_list"].split(',')) + '</feed>').encode()
    http = FakeHTTP()
    responses, issues = prefetch_arxiv(http, records)
    assert not issues
    assert len(http.calls) == 1
    assert http.calls[0]["id_list"] == ",".join(ids[1:])
    assert ids[0] not in responses
    for p in records[1:]:
        enrich_arxiv(http, p, responses[p["arxiv_id"]])
        assert p["abstract"] == "Abstract " + p["arxiv_id"]
    assert len(http.calls) == 1  # Applying the batched responses makes no more requests.


def test_contaminated_cluster_requires_independent_publication_evidence():
    researcher = {"id": "a", "verified_orcid": "0000-0000-0000-0001", "require_publication_corroboration": True,
                  "corroborated_work_ids": {"doi": ["10.1234/verified"], "arxiv": []}}
    supported, uncertain, coauthored, publisher = [paper(pid, owners) for pid, owners in
        [("verified", ["a"]), ("uncertain", ["a"]), ("coauthored", ["a", "b"]), ("publisher", ["a"])]]
    supported["doi"] = "10.1234/verified"
    publisher["crossref"] = {"authors": [{"ORCID": "https://orcid.org/0000-0000-0000-0001"}]}
    issues = corroborate_authorships([supported, uncertain, coauthored, publisher], [researcher])
    assert len(issues) == 2
    assert supported["researcher_ids"] == publisher["researcher_ids"] == ["a"]
    assert uncertain["quarantined"] and not uncertain["researcher_ids"]
    assert coauthored["researcher_ids"] == ["b"] and not coauthored["quarantined"]
