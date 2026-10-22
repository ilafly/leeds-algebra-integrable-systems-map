import pytest

from kgmap.core import arxiv_key, doi_key
from kgmap.sources import (IdentityError, abstract_from_index, deduplicate,
                           openalex_publication, retrieve_publications, select_identity)
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


def test_configured_id_alone_is_not_verification():
    with pytest.raises(IdentityError, match="Unverified"):
        select_identity([candidate()], PERSON, {"identity_confirmed": False, "linked_orcids": []})


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
