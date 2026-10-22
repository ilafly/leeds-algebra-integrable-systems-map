from __future__ import annotations

from itertools import combinations

import networkx as nx

from .core import stable_id


def build_graph(snapshot, reviews=None):
    reviews = reviews or {}
    graph = nx.MultiGraph()
    publications = {p["id"]: p for p in snapshot["publications"]}

    def add_edge(a, b, data):
        review = reviews.get(data["id"], {})
        graph.add_edge(a, b, key=data["id"], **{**data, "review": review,
                       "review_status": review.get("status", "unreviewed"),
                       "review_decision": review.get("status", "unreviewed")})

    for r in snapshot["researchers"]:
        graph.add_node("researcher:" + r["id"], kind="researcher", label=r["name"], details=r)
    for p in snapshot["publications"]:
        graph.add_node(p["id"], kind="publication", label=p["title"], details=p)
        for rid in p["researcher_ids"]:
            add_edge("researcher:" + rid, p["id"], {"id": stable_id("authored", rid, p["id"]),
                "type": "AUTHORED", "status": "verified", "method": "verified_openalex_author_id",
                "source": [s["source"] for s in p["provenance"]], "evidence": {"publication_id": p["id"]},
                "confidence": 1.0, "reliability": "verified_metadata", "review_status": "unreviewed"})
    for cid, c in snapshot["concepts"].items():
        graph.add_node(cid, **c, details=c)
    for mention in snapshot["mentions"]:
        owner, cid = mention["owner"], mention["concept"]
        add_edge(owner, cid, {**mention, "id": stable_id("mention", owner, cid, mention["field"]),
                              "type": "DISCUSSES" if owner in publications else "RESEARCHES"})
    for e in snapshot["concept_relations"]:
        add_edge(e["source_id"], e["target_id"], e)
    for c in snapshot["connections"]:
        a, b = "researcher:" + c["researcher_a"], "researcher:" + c["researcher_b"]
        if c["joint_publications"]:
            add_edge(a, b, {"id": stable_id("collaboration", a, b), "type": "COAUTHORED_WITH",
                "status": "verified", "confidence": 1.0, "reliability": "verified_metadata",
                "source": [publications[pid]["url"] for pid in c["joint_publications"]],
                "evidence": {"publication_ids": c["joint_publications"]},
                "method": "shared_deduplicated_publication", "review_status": "unreviewed"})
        if c["score"] > 0:
            add_edge(a, b, {**c, "type": "THEMATIC_PROXIMITY", "confidence": c["score"],
                           "source": [publications[pid]["url"] for pid in c["supporting_publications"]],
                           "evidence": c["explanation"], "reliability": "candidate"})
    return graph


def filtered_snapshot(snapshot, years=None, concept=None, researcher=None, reviews=None):
    """Recompute all inferred relationships from the visible publication sample."""
    from .concepts import related_concepts
    from .connections import discover_connections
    reviews = reviews or {}
    publications = [p for p in snapshot["publications"] if not p.get("is_retracted") and not p.get("quarantined")
                    and (not years or (p.get("year") is not None and years[0] <= p["year"] <= years[1]))]
    if researcher:
        publications = [p for p in publications if researcher in p["researcher_ids"]]
    if concept:
        owners = {m["owner"] for m in snapshot["mentions"] if m["concept"] == concept}
        publications = [p for p in publications if p["id"] in owners]
    owners = {p["id"] for p in publications}
    # Profile descriptions have no publication date; exclude them when date filtering is active.
    if not years:
        owners.update("researcher:" + r["id"] for r in snapshot["researchers"]
                      if not researcher or r["id"] == researcher)
    mentions = [m for m in snapshot["mentions"] if m["owner"] in owners
                and reviews.get(stable_id("mention", m["owner"], m["concept"], m["field"]), {}).get("status") != "rejected"]
    visible = {m["concept"] for m in mentions}
    concepts = {k: v for k, v in snapshot["concepts"].items() if k in visible}
    relations = [e for e in related_concepts(concepts, mentions) if reviews.get(e["id"], {}).get("status") != "rejected"]
    connections = discover_connections(snapshot["researchers"], publications, concepts, mentions, relations)
    return {**snapshot, "publications": publications, "mentions": mentions, "concepts": concepts,
            "concept_relations": relations, "connections": connections}


def graph_view(graph, view, threshold=0.0, types=None, include_rejected=False):
    kinds = {"knowledge": {"concept"}, "researchers": {"researcher"},
             "integrated": {"researcher", "publication", "concept"}}[view]
    g = nx.MultiGraph()
    for node, attrs in graph.nodes(data=True):
        if attrs["kind"] in kinds:
            g.add_node(node, **attrs)
    for a, b, key, data in graph.edges(keys=True, data=True):
        if a not in g or b not in g or (types is not None and data["type"] not in types):
            continue
        if not include_rejected and data.get("review_decision") == "rejected":
            continue
        if data.get("status") == "candidate" and data.get("confidence", 0) < threshold:
            continue
        g.add_edge(a, b, key=key, **data)
    if view == "knowledge":
        g.remove_nodes_from(list(nx.isolates(g)))
    return g


def researcher_path(graph, a, b):
    """Find an evidence-bearing path, excluding shortcut proximity edges."""
    g = nx.Graph()
    for u, v, d in graph.edges(data=True):
        if d["type"] == "THEMATIC_PROXIMITY" or d.get("review_decision") == "rejected":
            continue
        g.add_edge(u, v, weight=2 if d.get("status") == "candidate" else 1)
    try:
        return nx.shortest_path(g, "researcher:" + a, "researcher:" + b, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []
