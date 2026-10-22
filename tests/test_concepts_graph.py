import networkx as nx
import pytest

from kgmap.concepts import cosine, extract_concepts, tfidf_vectors
from kgmap.core import stable_id
from kgmap.graph import build_graph, filtered_snapshot, graph_view, researcher_path
from kgmap.pipeline import analyse
from conftest import paper


def test_normalisation_preserves_distinct_concepts(researchers):
    records = [paper("p1", ["test-a"], "Skew braces and braces; matched pairs of groups and matched products of groups"),
               paper("p2", ["test-b"], "Mapping class groups and mapping class groupoids")]
    concepts, mentions = extract_concepts(records, researchers)
    labels = {c["label"] for c in concepts.values()}
    assert {"skew braces", "braces", "matched pairs of groups", "matched products of groups", "mapping class groups", "mapping class groupoids"} <= labels


def test_skew_brace_does_not_invent_brace_mention(researchers):
    concepts, _ = extract_concepts([paper("p1", ["test-a"], "Skew braces", abstract="")], researchers)
    assert {c["label"] for c in concepts.values()} == {"skew braces"}


def test_generic_terms_not_topics(researchers):
    concepts, _ = extract_concepts([paper("p1", ["test-a"], "A mathematical model and its structure", abstract="")], researchers)
    assert not concepts


def test_data_driven_recurring_phrase_is_marked_unvalidated(researchers):
    records = [paper("p1", ["test-a"], "Virtual braid groups", abstract=""), paper("p2", ["test-b"], "Virtual braid groups and invariants", abstract="")]
    concepts, mentions = extract_concepts(records, researchers)
    assert any(c["label"] == "virtual braid groups" and c["terminology_status"] == "unvalidated_extracted_phrase" for c in concepts.values())
    assert all(m["source"] and m["evidence"] and m["method"] and "review_status" in m for m in mentions)


def test_tfidf_zero_and_identical_vectors():
    a, b, c = tfidf_vectors(["Hopf algebra braid invariants", "Hopf algebra braid invariants", ""])
    assert cosine(a, b) == pytest.approx(1)
    assert cosine(a, c) == 0


def test_noncollaborators_receive_candidates(researchers):
    snapshot = analyse(researchers[:2], [paper("p1", ["test-a"]), paper("p2", ["test-b"])])
    c = snapshot["connections"][0]
    assert c["score"] > 0.3
    assert c["joint_publications"] == []
    graph = build_graph(snapshot)
    types = {d["type"] for _, _, d in graph.edges(data=True)}
    assert "THEMATIC_PROXIMITY" in types
    assert "COAUTHORED_WITH" not in types
    assert not {"GENERALISES", "SPECIAL_CASE_OF", "USES_METHOD"} & types


def test_joint_abstract_not_compared_with_itself(researchers):
    snapshot = analyse(researchers[:2], [paper("p1", ["test-a", "test-b"])])
    c = snapshot["connections"][0]
    assert c["components"]["abstract_similarity"] == 0
    assert len(c["joint_publications"]) == 1
    assert "COAUTHORED_WITH" in {d["type"] for _, _, d in build_graph(snapshot).edges(data=True)}


def test_every_edge_has_audit_fields(researchers):
    graph = build_graph(analyse(researchers[:2], [paper("p1", ["test-a"]), paper("p2", ["test-b"])]))
    for _, _, edge in graph.edges(data=True):
        assert {"source", "method", "evidence", "confidence", "review_status", "status"} <= edge.keys()


def test_date_filter_recomputes_scores(researchers):
    original = analyse(researchers[:2], [paper("p1", ["test-a"], year=2024), paper("p2", ["test-b"], year=2025)])
    visible = filtered_snapshot(original, (2025, 2025))
    assert len(visible["publications"]) == 1
    assert visible["connections"][0]["score"] == 0


def test_rejected_mentions_affect_scoring(researchers):
    original = analyse(researchers[:2], [paper("p1", ["test-a"]), paper("p2", ["test-b"])])
    decisions = {stable_id("mention", m["owner"], m["concept"], m["field"]): {"status": "rejected"}
                 for m in original["mentions"] if m["owner"] == "p1"}
    visible = filtered_snapshot(original, reviews=decisions)
    assert visible["connections"][0]["components"]["shared_concepts"] == 0


def test_path_has_evidence_nodes_and_respects_threshold(researchers):
    snapshot = analyse(researchers[:2], [paper("p1", ["test-a"]), paper("p2", ["test-b"])])
    graph = build_graph(snapshot)
    path = researcher_path(graph, "test-a", "test-b")
    assert len(path) >= 5  # researcher -> paper -> topic -> paper -> researcher
    assert "p1" in path and "p2" in path
    only_proximity = graph_view(graph, "integrated", types=["THEMATIC_PROXIMITY"])
    assert not researcher_path(only_proximity, "test-a", "test-b")


def test_views_and_rejected_connection(researchers):
    snapshot = analyse(researchers[:2], [paper("p1", ["test-a"]), paper("p2", ["test-b"])])
    cid = snapshot["connections"][0]["id"]
    graph = build_graph(snapshot, {cid: {"status": "rejected"}})
    view = graph_view(graph, "researchers")
    assert all(d["kind"] == "researcher" for _, d in view.nodes(data=True))
    assert view.number_of_edges() == 0
    assert graph_view(build_graph(snapshot), "researchers", threshold=1).number_of_edges() == 0


def test_retracted_publication_cannot_create_candidates(researchers):
    p = paper("p1", ["test-a", "test-b"])
    p["is_retracted"] = True
    snapshot = analyse(researchers[:2], [p])
    assert snapshot["connections"][0]["score"] == 0
    assert snapshot["connections"][0]["joint_publications"] == []


def test_quarantined_publication_does_not_create_concepts_or_collaboration(researchers):
    p = paper("quarantined", ["test-a", "test-b"])
    p["quarantined"] = True
    snapshot = analyse(researchers[:2], [p])
    assert not snapshot["concepts"]
    assert snapshot["connections"][0]["score"] == 0
    assert snapshot["connections"][0]["joint_publications"] == []
    assert not filtered_snapshot(snapshot)["publications"]


def test_quarantined_titles_do_not_seed_recurring_terms(researchers):
    records = [paper("held-1", ["test-a"], title="Unusual zebra algebras", abstract=""),
               paper("held-2", ["test-a"], title="Unusual zebra algebras", abstract=""),
               paper("active", ["test-b"], title="Zebra algebras", abstract="")]
    records[0]["quarantined"] = records[1]["quarantined"] = True
    concepts, _ = extract_concepts(records, researchers, vocabulary={})
    assert not concepts
