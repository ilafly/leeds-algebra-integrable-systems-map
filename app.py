from __future__ import annotations

import json
from collections import Counter

import networkx as nx
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from kgmap.core import ROOT, stable_id
from kgmap.graph import build_graph, filtered_snapshot, graph_view, researcher_path
from kgmap.report import identity_rows, render_report
from kgmap.store import Store
from kgmap.visualisation import graph_html

st.set_page_config(page_title="Leeds · Mathematical connections", page_icon="◈", layout="wide")
st.markdown("""<style>
.block-container{padding-top:2rem;max-width:1600px}h1{letter-spacing:-.045em;font-weight:600!important}
h2,h3{letter-spacing:-.025em}div[data-testid="stMetric"]{background:#eff3ee;border:1px solid #dae3db;border-radius:10px;padding:14px 18px}
.eyebrow{font-size:.76rem;letter-spacing:.18em;font-weight:700;color:#176b63;margin-bottom:9px}
.legend{font-size:.8rem;color:#53665c;padding:8px 0 13px;line-height:1.8}.legend span{margin-right:17px}
</style>""", unsafe_allow_html=True)


def publication_details(p, mentions, concepts):
    st.markdown(f"**{p['title']}**")
    st.caption(f"{p.get('date') or 'Date unknown'} · " + ", ".join(a["name"] for a in p["authors"]))
    st.link_button("Open publication ↗", p["url"])
    if p.get("is_retracted"):
        st.warning("Source marks this publication as retracted. Excluded from discovery.")
    st.write(p["abstract"] or "No abstract available from the retrieved sources.")
    found = [m for m in mentions if m["owner"] == p["id"]]
    if found:
        st.dataframe(pd.DataFrame([{"Topic": concepts[m["concept"]]["label"], "Field": m["field"],
                                  "Evidence": m["evidence"], "Method": m["method"], "Source": m["source"]} for m in found]), hide_index=True)
    with st.expander("Metadata and provenance"):
        st.json(p)


store = Store()
snapshot = store.load()
st.markdown('<div class="eyebrow">UNIVERSITY OF LEEDS / RESEARCH PROTOTYPE</div>', unsafe_allow_html=True)
st.title("Mathematical connections")
st.write("Explore the ideas between researchers. Follow every proposed connection back to its evidence.")
if not snapshot:
    st.info("Collect a real dataset to begin. No demonstration data are loaded.")
    st.code("python -m kgmap.cli collect", language="bash")
    st.stop()

reviews = store.reviews()
people = {r["id"]: r for r in snapshot["researchers"]}
all_concepts = snapshot["concepts"]
with st.sidebar:
    st.markdown("### Explore the sample")
    st.caption("Pilot 01 · Algebra & integrable systems")
    focus = st.selectbox("Researcher", [None, *people], format_func=lambda x: "All researchers" if x is None else people[x]["name"], key="researcher_filter")
    concept = st.selectbox("Mathematical concept", [None, *sorted(all_concepts, key=lambda k: all_concepts[k]["label"].casefold())],
                           format_func=lambda x: "All concepts" if x is None else all_concepts[x]["label"], key="concept_filter")
    years = [p["year"] for p in snapshot["publications"] if p.get("year")]
    year_range = None
    if years and st.toggle("Filter publication dates", key="date_toggle"):
        if min(years) != max(years):
            year_range = st.slider("Publication year", min(years), max(years), (min(years), max(years)))
        else:
            year_range = (min(years), max(years))
        st.caption("Undated publications and undated profile descriptions are excluded.")
    threshold = st.slider("Minimum candidate score", 0.0, 1.0, 0.03, 0.01,
                          help="Applied to researcher proximity and concept association edges. These scores use different heuristics.", key="candidate_threshold")
    st.caption("Scores rank exploratory candidates; they are not probabilities.")
    st.divider()
    st.caption("Dataset generated " + snapshot["generated_at"][:19].replace("T", " ") + " UTC")
    st.caption("Collection is explicit; opening the app never calls research APIs.")
    st.code("python -m kgmap.cli collect", language="bash")

visible = filtered_snapshot(snapshot, year_range, concept, focus, reviews)
graph = build_graph(visible, reviews)
metrics = st.columns(4)
metrics[0].metric("Researchers", sum(r["status"] == "verified" for r in people.values()))
metrics[1].metric("Publications in view", len(visible["publications"]))
metrics[2].metric("Mathematical topics", len(visible["concepts"]))
metrics[3].metric("Abstract coverage", f"{sum(bool(p.get('abstract')) for p in visible['publications'])}/{len(visible['publications'])}")
tabs = st.tabs(["Explore maps", "Candidate connections", "Publications", "Identity & sources", "Review"])

with tabs[0]:
    view_label = st.radio("Map view", ["Knowledge map", "Researcher network", "Integrated map"], horizontal=True, label_visibility="collapsed", key="map_view")
    view = {"Knowledge map": "knowledge", "Researcher network": "researchers", "Integrated map": "integrated"}[view_label]
    left, right = st.columns([3, 2])
    types = sorted({d["type"] for _, _, d in graph.edges(data=True)})
    with left:
        selected_types = st.multiselect("Relationship types", types, default=types)
    with right:
        selected_researchers = st.multiselect("Highlight a path between two researchers", list(people),
            format_func=lambda k: people[k]["name"], max_selections=2)
    path = []
    if len(selected_researchers) == 2:
        # Honour relationship selections and threshold for path queries as well.
        path_graph = graph_view(graph, "integrated", threshold, selected_types)
        path = researcher_path(path_graph, *selected_researchers)
        if path:
            st.caption(" → ".join(graph.nodes[n]["label"] for n in path))
            if view != "integrated":
                st.info("Select Integrated map to see the full evidence path highlighted in red.")
        else:
            st.info("No evidence path is available under the current filters.")
    st.markdown('<div class="legend"><span>🟢 Researcher</span><span>🟦 Publication</span><span>🟠 Concept</span>'
                '<span style="color:#176B63">━━ Coauthorship</span><span style="color:#9A79B6">┄┄ Thematic candidate</span>'
                '<span style="color:#B2823C">┄┄ Concept association</span><span>Thin solid: source text / authorship</span><span>Red: selected path</span></div>', unsafe_allow_html=True)
    shown = graph_view(graph, view, threshold, selected_types)
    if shown.number_of_nodes():
        components.html(graph_html(shown, path), height=710, scrolling=False)
        st.caption(f"{shown.number_of_nodes()} nodes · {shown.number_of_edges()} edges. Click an edge to inspect its source, extraction method and review decision.")
    else:
        st.info("No nodes match these filters. Lower the threshold or broaden the sample.")
    with st.expander("Inspect a researcher or concept"):
        inspectable = [n for n, d in graph.nodes(data=True) if d["kind"] != "publication"]
        if inspectable:
            chosen = st.selectbox("Node", inspectable, format_func=lambda n: graph.nodes[n]["label"])
            data = graph.nodes[chosen]
            if data["kind"] == "researcher":
                rid = chosen.removeprefix("researcher:")
                owned = {p["id"] for p in visible["publications"] if rid in p["researcher_ids"]}
                topics = {m["concept"] for m in visible["mentions"] if m["owner"] in owned | {chosen}}
                st.write(", ".join(sorted(visible["concepts"][cid]["label"] for cid in topics)) or "No topics in this sample.")
            else:
                owned = {m["owner"] for m in visible["mentions"] if m["concept"] == chosen}
                rids = {rid for p in visible["publications"] if p["id"] in owned for rid in p["researcher_ids"]}
                rids.update(r["id"] for r in people.values() if "researcher:" + r["id"] in owned)
                st.write("Researchers: " + (", ".join(people[rid]["name"] for rid in sorted(rids)) or "none"))
            st.json(data["details"])
    st.download_button("Download visible graph (JSON)", json.dumps(nx.node_link_data(shown, edges="edges"), ensure_ascii=False, indent=2),
                       "leeds-map.json", "application/json")

with tabs[1]:
    st.subheader("Connections to investigate")
    st.caption("Collaboration is observed in publication metadata. Thematic proximity is a separate, exploratory calculation.")
    connections = [c for c in visible["connections"] if c["score"] >= threshold and reviews.get(c["id"], {}).get("status") != "rejected"]
    pub_lookup = {p["id"]: p for p in visible["publications"]}
    if not connections:
        st.info("No candidate researcher pairs pass the current filters and review decisions.")
    for c in connections:
        label = f"{people[c['researcher_a']]['name']} ↔ {people[c['researcher_b']]['name']} · {c['score']:.3f}"
        with st.expander(label, expanded=True):
            st.write(c["explanation"])
            a, b = st.columns(2)
            a.metric("Joint publications in sample", len(c["joint_publications"]))
            b.metric("Shared external collaborators", len(c["shared_collaborator_ids"]))
            st.dataframe(pd.DataFrame([{"Component": key.replace("_", " "), "Value": value,
                "Weight": c["weights"][key], "Contribution": value * c["weights"][key]} for key, value in c["components"].items()]), hide_index=True)
            st.caption("Shared concepts use IDF-weighted Jaccard. Related concepts use mean top-three co-occurrence scores; abstract similarity uses mean top-three independent TF-IDF comparisons. The intermediate path component uses the strongest two-hop concept path. Missing components contribute zero.")
            st.write("Shared topics: " + (", ".join(visible["concepts"][cid]["label"] for cid in c["shared_concepts"]) or "None"))
            for bridge in c["related_concepts"]:
                st.write(f"Candidate topic bridge: {visible['concepts'][bridge['left_concept']]['label']} ↔ {visible['concepts'][bridge['right_concept']]['label']} ({bridge['weight']:.3f})")
                for pid in bridge["publication_ids"]:
                    st.link_button(pub_lookup[pid]["title"], pub_lookup[pid]["url"])
            for middle_path in c["intermediate_paths"]:
                st.write("Candidate concept path: " + " → ".join(visible["concepts"][cid]["label"] for cid in middle_path["path"]))
            st.markdown("**Most similar independent abstract pairs**")
            if not c["abstract_pairs"]:
                st.caption("Not enough non-joint publications with abstracts.")
            for pair in c["abstract_pairs"]:
                p, q = pub_lookup[pair["left"]], pub_lookup[pair["right"]]
                st.write(f"Cosine similarity {pair['similarity']:.3f}")
                st.link_button(p["title"], p["url"])
                st.link_button(q["title"], q["url"])
            st.markdown("**Supporting publications and extraction evidence**")
            options = c["supporting_publications"]
            if options:
                pid = st.selectbox("Inspect supporting publication", options,
                    format_func=lambda key: pub_lookup[key]["title"], key="support_" + c["id"])
                publication_details(pub_lookup[pid], visible["mentions"], visible["concepts"])
            st.info(c["uncertainty"])
            decision = reviews.get(c["id"], {})
            st.caption("Review: " + decision.get("status", "unreviewed") + (" · " + decision["note"] if decision.get("note") else ""))
    st.download_button("Download full evidence report", render_report(snapshot, reviews), "discovered_connections.md", "text/markdown")

with tabs[2]:
    st.subheader("Publication evidence")
    query = st.text_input("Search titles, abstracts or authors")
    records = [p for p in visible["publications"] if not query or query.casefold() in
               (p["title"] + " " + p.get("abstract", "") + " " + " ".join(a["name"] for a in p["authors"])).casefold()]
    if records:
        st.dataframe(pd.DataFrame([{"Title": p["title"], "Date": p["date"], "Abstract": bool(p["abstract"]),
            "Researchers": ", ".join(people[rid]["name"] for rid in p["researcher_ids"]), "DOI": p["doi"], "Source": p["url"]} for p in records]),
            hide_index=True, use_container_width=True, column_config={"Source": st.column_config.LinkColumn("Source")})
        pid = st.selectbox("Publication details", [p["id"] for p in records], format_func=lambda key: pub_lookup[key]["title"])
        publication_details(pub_lookup[pid], visible["mentions"], visible["concepts"])
    else:
        st.info("No publications match.")

with tabs[3]:
    st.subheader("Identity before inference")
    st.dataframe(pd.DataFrame(identity_rows(snapshot)), hide_index=True, use_container_width=True)
    for r in people.values():
        with st.expander(r["name"] + " · " + r["status"]):
            st.write(r["reason"])
            for source in r.get("profile", {}).get("sources", []):
                st.write(source["status"] + " · " + source["url"])
                if source.get("error"):
                    st.caption(source["error"])
            st.json(r)
    providers = Counter(s["provider"] for p in snapshot["publications"] for s in p["provenance"])
    st.write("Publication provenance records: " + ", ".join(f"{k}: {v}" for k, v in sorted(providers.items())))
    events = snapshot.get("collection", {}).get("requests", [])
    stale = [e for e in events if e["status"] == "stale_cache"]
    if stale:
        st.warning(f"{len(stale)} requests used explicitly recorded stale cached responses.")
    issues = snapshot.get("collection", {}).get("issues", [])
    source_issues = [e for e in issues if e["stage"] != "publication_authorship_review"]
    authorship_issues = [e for e in issues if e["stage"] == "publication_authorship_review"]
    if source_issues:
        st.warning(f"{len(source_issues)} collection/enrichment issues. Retrieved records remain available.")
        st.dataframe(pd.DataFrame(source_issues), hide_index=True)
    if authorship_issues:
        with st.expander(f"{len(authorship_issues)} publication assignments awaiting authorship review"):
            st.write("Flagged author clusters require independent publication evidence. Uncorroborated assignments are excluded from discovery; absence of evidence does not establish non-authorship.")
            original_pubs = {p["id"]: p for p in snapshot["publications"]}
            st.dataframe(pd.DataFrame([{"Researcher": people[e["researcher"]]["name"],
                "Title": original_pubs[e["publication"]]["title"], "Source": e["source"], "Reason": e["error"]}
                for e in authorship_issues]), hide_index=True,
                column_config={"Source": st.column_config.LinkColumn("Source")})
    duplicates = snapshot.get("collection", {}).get("possible_duplicate_title_groups", [])
    if duplicates:
        with st.expander(f"{len(duplicates)} matching-title groups need version review"):
            st.caption("These records have no shared reliable identifier. They remain separate; joint publication counts may include unlinked versions.")
            original_pubs = {p["id"]: p for p in snapshot["publications"]}
            for group in duplicates:
                for pid in group:
                    p = original_pubs[pid]
                    st.link_button(p["title"], p["url"])
                st.divider()
    with st.expander("HTTP request and cache log"):
        st.dataframe(pd.DataFrame(events), hide_index=True)
    st.caption("OpenAlex metadata are CC0. Other source content and abstracts retain their source licences; cached content is for local analysis. No full-text scraping or paid AI service is used.")

with tabs[4]:
    st.subheader("Mathematician review")
    st.write("Accept, reject or annotate a correction. Decisions survive refreshes. Acceptance preserves the candidate's scientific status.")
    family = st.radio("Review category", ["Researcher candidates", "Concept associations", "Text extractions"], horizontal=True, key="review_category")
    raw_graph = build_graph(snapshot, reviews)
    family_type = {"Researcher candidates": {"THEMATIC_PROXIMITY"}, "Concept associations": {"RELATED_TO"}, "Text extractions": {"DISCUSSES", "RESEARCHES"}}[family]
    reviewable = {key: (a, b, d) for a, b, key, d in raw_graph.edges(keys=True, data=True) if d["type"] in family_type}
    if reviewable:
        edge_id = st.selectbox("Relationship to review", list(reviewable), format_func=lambda key:
            raw_graph.nodes[reviewable[key][0]]["label"] + " ↔ " + raw_graph.nodes[reviewable[key][1]]["label"] + " · " + reviews.get(key, {}).get("status", "unreviewed"))
        _, _, edge = reviewable[edge_id]
        with st.expander("Original evidence", expanded=True):
            st.json(edge)
        previous = reviews.get(edge_id, {})
        with st.form("review_form"):
            choices = ["unreviewed", "accepted", "rejected", "corrected"]
            status = st.selectbox("Decision", choices, index=choices.index(previous.get("status", "unreviewed")))
            note = st.text_area("Review / correction note", previous.get("note", ""),
                help="Corrections annotate the original edge. To remove an incorrect extraction from scoring, reject it. To change vocabulary aliases, edit config/vocabulary.json and run analyse.")
            submitted = st.form_submit_button("Save review", type="primary")
        if submitted:
            try:
                store.review(edge_id, status, note)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    else:
        st.info("No relationships in this category.")
    st.download_button("Export saved reviews", json.dumps(reviews, ensure_ascii=False, indent=2), "reviews.json", "application/json")
    st.caption("Rejected topic extractions and concept associations are excluded before filtered graph scores are recomputed. Rejected researcher proposals are hidden. Corrected notes preserve original evidence for audit.")

st.divider()
st.caption("LEEDS MATH MAP · Local research prototype · Solid edges carry metadata or explicit text evidence. Dashed edges are candidates for mathematical review.")
