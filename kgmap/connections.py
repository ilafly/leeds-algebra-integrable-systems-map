from __future__ import annotations

from collections import Counter
from itertools import combinations

from .concepts import cosine, tfidf_vectors
from .core import normalise, stable_id

WEIGHTS = {"shared_concepts": 0.40, "related_concepts": 0.20, "abstract_similarity": 0.30, "intermediate_concepts": 0.10}


def weighted_jaccard(a, b, weights):
    union = a | b
    return sum(weights[c] for c in a & b) / sum(weights[c] for c in union) if union else 0


def discover_connections(researchers, publications, concepts, mentions, related):
    verified = [r for r in researchers if r.get("status") == "verified"]
    profiles = {r["id"]: set() for r in verified}
    papers = {r["id"]: [p for p in publications if r["id"] in p["researcher_ids"] and not p.get("is_retracted")] for r in verified}
    pub_concepts = {}
    for m in mentions:
        if not m["owner"].startswith("researcher:"):
            pub_concepts.setdefault(m["owner"], set()).add(m["concept"])
    for r in verified:
        for p in papers[r["id"]]:
            profiles[r["id"]].update(pub_concepts.get(p["id"], set()))
        for m in mentions:
            if m["owner"] == "researcher:" + r["id"]:
                profiles[r["id"]].add(m["concept"])
    import math
    concept_weights = {c: 1 + math.log((1 + len(verified)) / (1 + sum(c in v for v in profiles.values()))) for c in concepts}
    all_papers = [p for p in publications if p.get("abstract") and not p.get("is_retracted")]
    vectors = dict(zip([p["id"] for p in all_papers], tfidf_vectors([p["abstract"] for p in all_papers])))
    related_by_pair = {tuple(sorted([e["source_id"], e["target_id"]])): e for e in related}
    adjacency = {}
    for e in related:
        adjacency.setdefault(e["source_id"], {})[e["target_id"]] = e
        adjacency.setdefault(e["target_id"], {})[e["source_id"]] = e
    results = []
    for a, b in combinations(verified, 2):
        aid, bid = a["id"], b["id"]
        ac, bc = profiles[aid], profiles[bid]
        shared = ac & bc
        ap, bp = papers[aid], papers[bid]
        joint = sorted({p["id"] for p in ap} & {p["id"] for p in bp})
        # A joint paper is evidence of collaboration, not independent abstract similarity.
        abstract_pairs = sorted([{"left": p["id"], "right": q["id"],
                                  "similarity": round(cosine(vectors[p["id"]], vectors[q["id"]]), 4)}
                                 for p in ap for q in bp if p["id"] != q["id"]
                                 and p["id"] not in joint and q["id"] not in joint
                                 and p["id"] in vectors and q["id"] in vectors],
                                key=lambda x: (-x["similarity"], x["left"], x["right"]))[:3]
        bridges = []
        for ca in ac - shared:
            for cb in bc - shared:
                e = related_by_pair.get(tuple(sorted([ca, cb])))
                if e:
                    bridges.append({"left_concept": ca, "right_concept": cb,
                                    "weight": e["confidence"], "publication_ids": e["evidence"]["publication_ids"], "edge_id": e["id"]})
        bridges.sort(key=lambda x: (-x["weight"], x["left_concept"], x["right_concept"]))
        intermediate = []
        for ca in ac - shared:
            for cb in bc - shared:
                for middle in set(adjacency.get(ca, {})) & set(adjacency.get(cb, {})):
                    if middle in ac | bc:
                        continue
                    e1, e2 = adjacency[ca][middle], adjacency[cb][middle]
                    intermediate.append({"path": [ca, middle, cb], "weight": min(e1["confidence"], e2["confidence"]),
                        "publication_ids": sorted(set(e1["evidence"]["publication_ids"]) | set(e2["evidence"]["publication_ids"]))})
        intermediate.sort(key=lambda x: (-x["weight"], x["path"]))
        def collaborators(ps):
            # Stable OpenAlex IDs only; names are too ambiguous for collaboration matching.
            return {x["openalex_id"] for p in ps for x in p["authors"] if x.get("openalex_id")}
        pilot_ids = {r["openalex_id"] for r in verified}
        common_collaborators = sorted((collaborators(ap) & collaborators(bp)) - pilot_ids)
        components = {"shared_concepts": weighted_jaccard(ac, bc, concept_weights),
                      "related_concepts": sum(x["weight"] for x in bridges[:3]) / len(bridges[:3]) if bridges else 0,
                      "abstract_similarity": sum(x["similarity"] for x in abstract_pairs) / len(abstract_pairs) if abstract_pairs else 0,
                      "intermediate_concepts": intermediate[0]["weight"] if intermediate else 0}
        score = sum(components[k] * weight for k, weight in WEIGHTS.items())
        evidence_ids = {p["id"] for p in ap + bp if pub_concepts.get(p["id"], set()) & shared}
        evidence_ids.update(pid for x in bridges[:5] for pid in x["publication_ids"])
        evidence_ids.update(pid for x in intermediate[:3] for pid in x["publication_ids"])
        evidence_ids.update(pid for pair in abstract_pairs for pid in [pair["left"], pair["right"]])
        shared_labels = [concepts[c]["label"] for c in sorted(shared)]
        results.append({"id": stable_id("connection", *sorted([aid, bid])), "researcher_a": aid, "researcher_b": bid,
            "score": round(score, 4), "components": {k: round(v, 4) for k, v in components.items()}, "weights": WEIGHTS,
            "shared_concepts": sorted(shared), "related_concepts": bridges[:5], "intermediate_paths": intermediate[:3],
            "abstract_pairs": abstract_pairs, "joint_publications": joint, "shared_collaborator_ids": common_collaborators,
            "supporting_publications": sorted(evidence_ids), "status": "candidate", "review_status": "unreviewed",
            "method": "idf_weighted_topic_jaccard+cooccurrence+abstract_tfidf+two_hop_paths",
            "uncertainty": "Exploratory candidate; score is a ranking heuristic, not a calibrated probability. Missing abstracts and the publication sample affect it. No joint publications means none in this sample.",
            "explanation": f"{len(shared)} shared extracted topics" + (": " + ", ".join(shared_labels[:8]) if shared_labels else "")
                + f"; {len(bridges)} nonidentical topic bridges; {len(abstract_pairs)} independent abstract pairs scored. "
                + (f"{len(joint)} joint publications in this sample." if joint else "No joint publications in this sample; this candidate is based on mathematical proximity.")})
    return sorted(results, key=lambda x: (-x["score"], x["id"]))
