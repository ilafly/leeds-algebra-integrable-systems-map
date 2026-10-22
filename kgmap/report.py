from __future__ import annotations

from collections import Counter

import pandas as pd

from .core import ROOT


def identity_rows(snapshot):
    return [{"Researcher": r["name"], "Affiliation": r["affiliation"], "Affiliation context": r.get("affiliation_note", "Profile-reported affiliation; not independently checked as current employment"),
             "Affiliation source": r.get("affiliation_source", r.get("profile_url", "")), "Status": r["status"],
             "OpenAlex": r.get("openalex_id") or "unverified", "ORCID": r.get("verified_orcid") or "unverified / unavailable",
             "Reported ORCID": r.get("reported_orcid") or "unavailable", "ORCID basis": r.get("orcid_basis", ""),
             "Basis": r.get("reason", ""),
             "Sources": " ; ".join(s["url"] for s in r.get("profile", {}).get("sources", []))}
            for r in snapshot["researchers"]]


def markdown_table(rows, fields):
    def escape(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    return "\n".join(["| " + " | ".join(fields) + " |", "| " + " | ".join("---" for _ in fields) + " |",
                      *("| " + " | ".join(escape(row.get(f, "")) for f in fields) + " |" for row in rows)])


def render_report(snapshot, reviews=None):
    reviews = reviews or {}
    people = {r["id"]: r for r in snapshot["researchers"]}
    pubs = {p["id"]: p for p in snapshot["publications"]}
    concepts = snapshot["concepts"]
    providers = Counter(prov["provider"] for p in pubs.values() for prov in p["provenance"])
    parts = ["# Leeds Algebra and Integrable Systems — pilot evidence report", "",
        f"Generated: {snapshot['generated_at']}. Data: real retrieved public metadata; no demonstration records.", "",
        "## Researcher identity verification", "", markdown_table(identity_rows(snapshot),
            ["Researcher", "Affiliation", "Affiliation context", "Affiliation source", "Status", "OpenAlex", "ORCID", "Reported ORCID", "ORCID basis", "Basis", "Sources"]), "",
        "Identity verification here means bibliographic identity corroboration, not independent validation of every publication in a provider's author cluster. The Leeds roster is a research context including former or joint affiliations, not a current employment directory.", "",
        "## Collection coverage", "",
        f"{len(pubs)} identifier-deduplicated publication records, {sum(bool(p.get('abstract')) for p in pubs.values())} with abstracts; "
        f"{len(concepts)} extracted concepts or unvalidated mathematical phrases.", "",
        f"{sum(not p.get('quarantined') and not p.get('is_retracted') for p in pubs.values())} records are included in discovery; "
        f"{sum(bool(p.get('quarantined')) for p in pubs.values())} are retained for provenance but quarantined pending authorship corroboration. "
        "A record corroborated for one pilot researcher can remain in that researcher's sample while an uncertain coauthor assignment is withheld.", "",
        "Metadata provenance records by provider: " + ", ".join(f"{p}: {n}" for p, n in sorted(providers.items())) + ".", "",
        markdown_table([{"Researcher": r["name"], "Publications": sum(r["id"] in p["researcher_ids"] for p in pubs.values()),
                         "With abstracts": sum(r["id"] in p["researcher_ids"] and bool(p.get("abstract")) for p in pubs.values())}
                        for r in people.values()], ["Researcher", "Publications", "With abstracts"]), "",
        "## Interpretation and scoring", "",
        "The thematic score is 0.40 × IDF-weighted shared-topic Jaccard + 0.20 × mean of the strongest three "
        "nonidentical co-occurrence bridges + 0.30 × mean of the strongest three independent abstract TF-IDF cosine similarities "
        "+ 0.10 × strongest two-hop concept path. Missing components contribute zero; weights are not renormalised. "
        "TF-IDF uses unigrams and bigrams with smoothed IDF and L2 normalisation. Joint papers are excluded from abstract comparisons. "
        "These choices are transparent exploratory heuristics, not calibrated probabilities or mathematical proofs. "
        "Vocabulary entries normalise terminology; no mathematical relationships are seeded. Co-occurrence alone only creates candidate RELATED_TO edges. "
        "No GENERALISES, SPECIAL_CASE_OF or USES_METHOD edges are inferred without explicit reviewed evidence. "
        "Coauthorship and shared collaborators are reported separately from the thematic score. "
        "Shared broad concepts may inflate rankings; small samples, missing abstracts and provider author-cluster errors limit recall and precision.", "",
        "## Candidate connections", ""]
    for c in snapshot["connections"]:
        review = reviews.get(c["id"], {})
        parts += [f"### {people[c['researcher_a']]['name']} ↔ {people[c['researcher_b']]['name']}", "",
                  f"Candidate score: **{c['score']:.3f}**. Review: {review.get('status', 'unreviewed')}.", "",
                  c["explanation"], "", c["uncertainty"], "",
                  markdown_table([{"Component": k, "Value": f"{v:.4f}", "Weight": c["weights"][k]}
                                  for k, v in c["components"].items()], ["Component", "Value", "Weight"]), "",
                  "Shared concepts: " + (", ".join(concepts[k]["label"] for k in c["shared_concepts"]) or "none") + ".", "",
                  f"Shared external collaborators (stable author IDs): {len(c['shared_collaborator_ids'])}.", ""]
        if review.get("note"):
            parts += ["Reviewer note: " + review["note"], ""]
        for bridge in c["related_concepts"]:
            parts += [f"- Candidate bridge: {concepts[bridge['left_concept']]['label']} ↔ {concepts[bridge['right_concept']]['label']}; "
                      f"co-occurrence weight {bridge['weight']:.3f}."]
        for path in c["intermediate_paths"]:
            parts += ["- Candidate intermediate path: " + " → ".join(concepts[k]["label"] for k in path["path"]) + "."]
        parts += ["", "Independent abstract comparisons:", ""]
        for pair in c["abstract_pairs"]:
            left, right = pubs[pair["left"]], pubs[pair["right"]]
            parts += [f"- {pair['similarity']:.3f}: [{left['title']}]({left['url']}) ↔ [{right['title']}]({right['url']})."]
        parts += ["", "Supporting publications and explicit terminology evidence:", ""]
        shared_set = set(c["shared_concepts"])
        for pid in c["supporting_publications"]:
            p = pubs[pid]
            parts += [f"- [{p['title']}]({p['url']}) ({p.get('date') or 'date unknown'}). "
                      + ("**Joint publication.** " if pid in c["joint_publications"] else "")]
            matches = [m for m in snapshot["mentions"] if m["owner"] == pid and m["concept"] in shared_set]
            if matches:
                # Avoid reproducing full copyrighted abstracts in a distributable report.
                parts[-1] += "Matched topics: " + ", ".join(sorted({concepts[m["concept"]]["label"] for m in matches})) + "."
        parts += [""]
    duplicates = snapshot.get("collection", {}).get("possible_duplicate_title_groups", [])
    parts += ["## Possible unlinked versions", "",
              "Matching titles without a shared reliable identifier remain separate. These groups need review; title similarity alone does not prove they are the same work. Joint publication counts count records and may include unlinked versions.", ""]
    for group in duplicates:
        parts += ["- " + " ; ".join(f"[{pubs[pid]['title']}]({pubs[pid]['url']})" for pid in group)]
    held = [p for p in pubs.values() if p.get("unverified_researcher_ids")]
    if held:
        parts += ["", "## Authorship assignments awaiting review", "",
                  "Some OpenAlex author clusters contain namesake records. For researchers flagged in configuration, assignments require an exact work identifier in the public ORCID bibliography or an exact publisher-supplied ORCID. Absence of corroboration is not proof of non-authorship. Quarantined records do not contribute concepts, TF-IDF, collaborations or map paths.", ""]
        for p in held:
            names = ", ".join(people[rid]["name"] for rid in p["unverified_researcher_ids"])
            parts += [f"- [{p['title']}]({p['url']}) — assignment to {names} awaiting review."]
    parts += ["", "## Source availability", ""]
    for r in people.values():
        for source in r.get("profile", {}).get("sources", []):
            parts += [f"- {r['name']}: {source['url']} — {source['status']}" + ("; " + source["error"] if source.get("error") else "")]
        if r.get("orcid_status"):
            parts += [f"- {r['name']} ORCID API: {r['orcid_status']}"]
    issues = snapshot.get("collection", {}).get("issues", [])
    source_issues = [e for e in issues if e["stage"] != "publication_authorship_review"]
    review_issues = [e for e in issues if e["stage"] == "publication_authorship_review"]
    parts += ["", f"Supplementary collection/enrichment issues: {len(source_issues)}. "
              f"Authorship assignments awaiting corroboration: {len(review_issues)} (listed above). Full request log is in data/snapshot.json.", ""]
    for issue in source_issues:
        parts += ["- " + issue["stage"] + ": " + issue["error"]]
    parts += ["", "## Review and evaluation", "",
        "Use the application's Review tab or `python -m kgmap.cli export-reviews`, edit the JSON, then `import-reviews`. "
        "Review IDs persist across refreshes. Rejected extraction and concept-association edges are removed before visible scores are recomputed. "
        "Accepting a candidate records a mathematician's opinion; it does not turn similarity into a proven theorem. "
        "Corrected decisions require a note and preserve the original evidence. "
        "A scientific evaluation still needs a mathematician-labelled set: check author-cluster precision, topic extraction precision/recall, "
        "and connection usefulness, then compare against a shared-keywords-only baseline. No accuracy claim is made from software tests.", ""]
    return "\n".join(line.rstrip() for line in parts).rstrip() + "\n"


def write_reports(snapshot, reviews=None, directory=None):
    directory = directory or ROOT / "reports"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "discovered_connections.md").write_text(render_report(snapshot, reviews), encoding="utf-8")
    pd.DataFrame(identity_rows(snapshot)).to_csv(directory / "researcher_identities.csv", index=False)
