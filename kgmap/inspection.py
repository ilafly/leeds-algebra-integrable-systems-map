"""Readable, source-grounded explanations for graph relationships."""
from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlsplit

from .core import stable_id

RELATION_LABELS = {
    "AUTHORED": "Authored", "COAUTHORED_WITH": "Coauthored",
    "DISCUSSES": "Mentions topic", "RESEARCHES": "Profile mentions topic",
    "PAPERS_MENTION": "Papers mention topic",
    "RELATED_TO": "Topics mentioned together", "THEMATIC_PROXIMITY": "Thematic candidate",
}
FIELD_LABELS = {"title": "Title", "abstract": "Abstract", "full_text": "Full text",
                "research_description": "Research profile"}
COMPONENTS = {
    "shared_concepts": ("Shared topics", "IDF-weighted Jaccard overlap of researcher topic sets."),
    "related_concepts": ("Topic bridges", "Mean of the strongest three nonidentical topic co-occurrence bridges."),
    "abstract_similarity": ("Abstract similarity", "Mean of the strongest three independent abstract TF-IDF cosines; joint papers excluded."),
    "intermediate_concepts": ("Intermediate topic path", "Strength of the strongest two-hop path through an intermediate concept."),
    "full_text_similarity": ("Full-text similarity", "Mean of the strongest three independent body-text TF-IDF cosines; joint papers excluded."),
}
METHODS = {
    "publication_cooccurrence_cosine": "Count shared publications and normalise by each topic's publication coverage.",
    "normalised_phrase_match": "Match a vocabulary phrase after normalising spelling, accents and hyphens.",
    "recurring_mathematical_title_phrase": "Match a recurring mathematical title phrase; terminology is unvalidated.",
    "verified_openalex_author_id": "Match the researcher's verified OpenAlex author ID to the publication's authorship metadata.",
    "shared_deduplicated_publication": "Find retained publication records assigned to both researchers.",
    "publication_topic_projection": "Summarise the researcher's authorship links and unrejected topic mentions in the visible publication sample. Each paper is counted once per topic.",
}


def safe_source_url(url):
    try:
        return isinstance(url, str) and urlsplit(url).scheme in {"http", "https"} and bool(urlsplit(url).netloc)
    except ValueError:
        return False


class EdgeInspector:
    def __init__(self, snapshot=None, graph=None):
        snapshot = snapshot or {}
        self.publications = {p["id"]: p for p in snapshot.get("publications", [])}
        self.labels = {k: c["label"] for k, c in snapshot.get("concepts", {}).items()}
        self.labels.update({"researcher:" + r["id"]: r["name"] for r in snapshot.get("researchers", [])})
        self.labels.update({p["id"]: p["title"] for p in self.publications.values()})
        if graph is not None:
            self.labels.update({n: d["label"] for n, d in graph.nodes(data=True)})
            self.publications.update({n: d["details"] for n, d in graph.nodes(data=True)
                                      if d["kind"] == "publication" and "details" in d})
        self.mentions = defaultdict(list)
        self.topic_papers = defaultdict(set)
        for m in snapshot.get("mentions", []):
            self.mentions[m["owner"]].append(m)
            if m["owner"] in self.publications:
                self.topic_papers[m["concept"]].add(m["owner"])

    def label(self, value):
        return self.labels.get(value, value)

    def describe(self, a, b, edge, limit=5):
        kind = edge["type"]
        evidence = edge.get("evidence", {})
        evidence = evidence if isinstance(evidence, dict) else {}
        ids = list(evidence.get("publication_ids", []))
        if evidence.get("publication_id"):
            ids.append(evidence["publication_id"])
        topics, comparisons, components, facts, bridges, paths = [], [], [], [], [], []
        metric = None
        short_label = RELATION_LABELS.get(kind, kind.replace("_", " ").title())
        summary = f"{self.label(a)} ↔ {self.label(b)}"
        meaning = "Follow the supporting sources to assess this relationship."
        if kind == "RELATED_TO":
            topics = [a, b]
            count = len(ids)
            summary = f"Both topics appear in {count} publication record{'s' if count != 1 else ''} in the current sample."
            meaning = "Co-occurrence can come from different pages or text fields. It suggests an association; it does not establish an implication, equivalence or use of one concept by the other."
            metric = {"label": "Association score", "value": edge["confidence"], "note": "Normalised co-occurrence, not a probability."}
            na, nb = len(self.topic_papers[a]), len(self.topic_papers[b])
            if na and nb:
                facts = [{"label": "Topic coverage", "value": f"{self.label(a)}: {na} papers; {self.label(b)}: {nb} papers"},
                         {"label": "Calculation", "value": f"{count} / √({na} × {nb}) = {edge['confidence']:.4f}"}]
            short_label = f"Together in {count} paper{'s' if count != 1 else ''}"
        elif kind in {"DISCUSSES", "RESEARCHES"}:
            owner, topic = edge["owner"], edge["concept"]
            a, b, topics = owner, topic, [topic]
            field = FIELD_LABELS.get(edge.get("field"), edge.get("field", "source text"))
            location = field + (f", PDF page {edge['page']}" if edge.get("page") else "")
            summary = f'“{self.label(topic)}” was matched in the {location.lower()}.'
            meaning = "This records a terminology match. The source may discuss background work, limitations or other authors' results; the match alone does not establish expertise or a mathematical claim."
            metric = {"label": "Extraction confidence", "value": edge["confidence"], "note": "Uncalibrated extraction hint, not a probability of mathematical truth."}
            facts = [{"label": "Text field", "value": location},
                     {"label": "Matched phrase", "value": edge.get("matched_phrase", "not recorded")}]
            if owner in self.publications:
                ids = [owner]
        elif kind == "PAPERS_MENTION":
            if not a.startswith("researcher:"):
                a, b = b, a
            topics = [b]
            count = len(ids)
            summary = f"{count} publication record{'s' if count != 1 else ''} by {self.label(a)} mention “{self.label(b)}” in the current sample."
            meaning = "This display link summarises authorship and extracted topic mentions while paper nodes are hidden. A mention may describe background work; it does not establish expertise or a mathematical claim. Review the underlying text extractions to correct its evidence."
            facts = [{"label": "Supporting papers", "value": str(count)}]
            short_label = f"Papers mention topic ({count})"
        elif kind == "AUTHORED":
            if not a.startswith("researcher:"):
                a, b = b, a
            summary = f"{self.label(a)} is listed as an author of this publication in the retained bibliographic metadata."
            meaning = "The link follows verified author identifiers and any configured work-level corroboration. Provider author clusters and unlinked publication versions can still require review."
        elif kind == "COAUTHORED_WITH":
            count = len(ids)
            summary = f"These researchers share {count} publication record{'s' if count != 1 else ''} in the current sample."
            meaning = "This is bibliographic collaboration evidence. Counts can include unlinked preprint and journal versions; absence of a link means none was found in this sample."
            short_label = f"Coauthored ({count} paper{'s' if count != 1 else ''})"
        elif kind == "THEMATIC_PROXIMITY":
            summary = edge["explanation"]
            meaning = edge["uncertainty"]
            topics = list(edge["shared_concepts"])
            metric = {"label": "Thematic score", "value": edge["score"], "note": "Exploratory ranking, not a probability. Missing components contribute zero."}
            for k, value in edge["components"].items():
                label, explanation = COMPONENTS.get(k, (k.replace("_", " "), ""))
                components.append({"label": label, "value": value, "weight": edge["weights"][k],
                                   "contribution": round(value * edge["weights"][k], 5), "explanation": explanation})
            # Prefer papers actually used by the independent language comparisons.
            ids = []
            for key, label in [("full_text_pairs", "Full-text comparison"), ("abstract_pairs", "Abstract comparison")]:
                for pair in edge.get(key, []):
                    left, right = self.publications.get(pair["left"]), self.publications.get(pair["right"])
                    if not left or not right:
                        continue
                    ids.extend([left["id"], right["id"]])
                    def citation(p):
                        url = p.get("full_text", {}).get("source_url") if key == "full_text_pairs" else None
                        if not safe_source_url(url):
                            url = p["url"]
                        return {"title": p["title"], "url": url or p["url"]}
                    comparisons.append({"label": label, "similarity": pair["similarity"], "left": citation(left), "right": citation(right)})
            ids.extend(edge.get("joint_publications", []))
            ids.extend(edge["supporting_publications"])
            for bridge in edge.get("related_concepts", []):
                ca, cb = bridge["left_concept"], bridge["right_concept"]
                bridges.append(f"{self.label(ca)} ↔ {self.label(cb)} · {bridge['weight']:.3f}")
                topics.extend([ca, cb])
            paths = [" → ".join(self.label(cid) for cid in p["path"]) for p in edge.get("intermediate_paths", [])]
            facts = [{"label": "Joint publications", "value": str(len(edge["joint_publications"]))},
                     {"label": "Shared external collaborators", "value": str(len(edge["shared_collaborator_ids"]))}]
            if any(edge.get("full_text_coverage", {}).values()):
                facts.append({"label": "Full-text coverage", "value": "; ".join(
                    f"{self.label('researcher:' + rid)}: {n} papers" for rid, n in edge["full_text_coverage"].items())})
            short_label = f"Thematic candidate: {edge['score']:.3f}"

        ids = [pid for pid in dict.fromkeys(ids) if pid in self.publications]
        papers = []
        for pid in ids if limit is None else ids[:limit]:
            p = self.publications[pid]
            found = [m for m in self.mentions[pid] if m["concept"] in topics]
            if kind == "PAPERS_MENTION":
                allowed = set(evidence["mention_ids"])
                found = [m for m in found if stable_id("mention", m["owner"], m["concept"], m["field"]) in allowed]
            if kind == "DISCUSSES":
                found = [edge]  # Inspect this exact field/page rather than another parallel edge.
            # Show one best-located excerpt per topic, preferring PDF page evidence.
            found.sort(key=lambda m: ({"full_text": 0, "abstract": 1, "title": 2}.get(m["field"], 3), m.get("page", 0)))
            excerpts, seen = [], set()
            for m in found:
                if m["concept"] in seen:
                    continue
                seen.add(m["concept"])
                excerpts.append(self.excerpt(m))
                if len(excerpts) == 3:
                    break
            notes = "Joint publication in this sample." if pid in edge.get("joint_publications", []) else ""
            papers.append({"id": pid, "title": p["title"], "date": p.get("date"), "url": p["url"], "notes": notes, "excerpts": excerpts})
        sources = edge.get("source", [])
        sources = list(dict.fromkeys([sources] if isinstance(sources, str) else sources))
        review = edge.get("review", {})
        return {"id": edge["id"], "label": RELATION_LABELS.get(kind, kind), "short_label": short_label,
                "title": f"{self.label(a)} {'→' if kind in {'AUTHORED', 'DISCUSSES', 'RESEARCHES', 'PAPERS_MENTION'} else '↔'} {self.label(b)}",
                "status": edge.get("status", "unrecorded"), "review": review.get("status", edge.get("review_status", "unreviewed")),
                "review_note": review.get("note", ""), "summary": summary, "meaning": meaning,
                "metric": metric, "facts": facts, "components": components,
                "shared_topics": [self.label(cid) for cid in edge.get("shared_concepts", [])],
                "bridges": bridges, "paths": paths, "comparisons": comparisons,
                "publications": papers, "publication_count": len(ids),
                "excerpt": self.excerpt(edge) if kind == "RESEARCHES" else None,
                "method": METHODS.get(edge.get("method"), "Combine the displayed weighted score components." if kind == "THEMATIC_PROXIMITY" else edge.get("method", "not recorded")),
                "sources": sources if limit is None else sources[:limit], "source_count": len(sources)}

    def excerpt(self, mention):
        return {"topic": self.label(mention["concept"]), "field": FIELD_LABELS.get(mention["field"], mention["field"]),
                "page": mention.get("page"), "text": mention["evidence"], "url": mention["source"]}


def edge_tooltip(details):
    lines = [details["label"], details["title"], details["summary"]]
    if details["metric"]:
        metric = details["metric"]
        lines.append(f"{metric['label']}: {metric['value']:.3f}")
    lines.append(f"Status: {details['status']} · Review: {details['review']}")
    lines.append("Click for explanation, papers and source excerpts.")
    return "\n".join(lines)
