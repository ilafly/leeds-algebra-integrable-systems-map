from __future__ import annotations

import json
from collections import Counter

import pandas as pd
import streamlit as st

from .inspection import safe_source_url
from .suggestions import KINDS, STATUSES


def render_suggestions(store, snapshot):
    st.subheader("Suggestions")
    st.write("Flag missing joint work, suggest a paper or connection, or explain a correction.")
    st.caption("Suggestions are saved for review. Accepted suggestions are ready for follow-up; mark them resolved after incorporating the evidence or correction into the map.")
    people = {r["id"]: r["name"] for r in snapshot["researchers"]}
    pubs = {p["id"]: p for p in snapshot["publications"]}
    if st.session_state.pop("suggestion_reset_form", False):
        for key in ["suggestion_kind", "suggestion_title", "suggestion_people", "suggestion_publication",
                    "suggestion_source", "suggestion_note"]:
            st.session_state.pop(key, None)
    if st.session_state.pop("suggestion_saved", False):
        st.success("Suggestion saved. It is now in the review queue.")
    if st.session_state.pop("suggestion_review_saved", False):
        st.success("Suggestion review saved.")

    with st.form("suggestion_form"):
        st.markdown("**Add a suggestion**")
        kind = st.selectbox("Suggestion type", list(KINDS), format_func=KINDS.get, key="suggestion_kind")
        title = st.text_input("Paper title or short summary", max_chars=240, key="suggestion_title")
        rids = st.multiselect("Researchers involved", list(people), format_func=people.get, key="suggestion_people",
                              help="Choose at least two researchers in this map for joint work. Missing-paper and connection suggestions need at least one.")
        pid = st.selectbox("Existing paper (optional)", [None, *pubs], key="suggestion_publication",
                           format_func=lambda x: "No existing paper" if x is None else pubs[x]["title"])
        source = st.text_input("Source URL or DOI", max_chars=2000, key="suggestion_source",
                               help="Joint-work suggestions need a source. Selecting an existing paper supplies its source if this field is empty.")
        note = st.text_area("What should we add or correct?", max_chars=5000, key="suggestion_note")
        submitter = st.text_input("Your name (optional)", max_chars=120, key="suggestion_submitter")
        submitted = st.form_submit_button("Submit suggestion", type="primary")
    if submitted:
        try:
            record = store.add_suggestion({"kind": kind, "title": title, "researcher_ids": rids,
                "publication_id": pid, "source": source, "note": note, "submitter": submitter})
            st.session_state["suggestion_saved"] = True
            st.session_state["suggestion_reset_form"] = True
            st.session_state["suggestion_record"] = record["id"]
            st.session_state["suggestion_status_filter"] = "all"
            st.session_state["suggestion_person_filter"] = None
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    records = store.suggestions()
    st.markdown("**Suggestion queue**")
    if not records:
        st.info("No suggestions yet. Use the form above to add the first one.")
        return
    counts = Counter(r["status"] for r in records)
    st.caption(f"{len(records)} saved · " + " · ".join(f"{STATUSES[k]}: {v}" for k, v in counts.items()))
    left, right = st.columns(2)
    with left:
        status_filter = st.selectbox("Suggestion status", ["all", *STATUSES], key="suggestion_status_filter",
                                     format_func=lambda k: "All statuses" if k == "all" else STATUSES[k])
    with right:
        person_filter = st.selectbox("Suggestions about", [None, *people], key="suggestion_person_filter",
                                     format_func=lambda k: "All researchers" if k is None else people[k])
    filtered = [r for r in records if (status_filter == "all" or r["status"] == status_filter)
                and (person_filter is None or person_filter in r["researcher_ids"])]
    if not filtered:
        st.info("No suggestions match these filters.")
    else:
        lookup = {r["id"]: r for r in filtered}
        st.dataframe(pd.DataFrame([{"Title": r["title"], "Type": KINDS[r["kind"]],
            "Researchers": ", ".join(r["researcher_names"].values()), "Status": STATUSES[r["status"]],
            "Suggested by": r["submitter"] or "Not supplied", "Submitted (UTC)": r["created_at"]} for r in filtered]), hide_index=True)
        sid = st.selectbox("Suggestion to inspect", list(lookup), key="suggestion_record",
                           format_func=lambda k: lookup[k]["title"] + " · " + STATUSES[lookup[k]["status"]])
        record = lookup[sid]
        st.text(record["title"])
        st.caption(KINDS[record["kind"]] + " · " + ", ".join(record["researcher_names"].values()))
        st.text(record["note"])
        if record["publication_title"]:
            st.caption("Existing paper: " + record["publication_title"])
        if safe_source_url(record["source_url"]):
            st.link_button("Open suggested source", record["source_url"])
        with st.form("suggestion_review_" + sid):
            status = st.selectbox("Review suggestion", list(STATUSES), index=list(STATUSES).index(record["status"]),
                                  format_func=STATUSES.get, key="suggestion_review_status_" + sid)
            review_note = st.text_area("Suggestion review note", record["review_note"], max_chars=5000,
                                      key="suggestion_review_note_" + sid, help="Add a note when resolving or rejecting a suggestion.")
            reviewer = st.text_input("Reviewer name (optional)", max_chars=120, key="suggestion_reviewer")
            reviewed = st.form_submit_button("Save suggestion review")
        if reviewed:
            try:
                store.review_suggestion(sid, status, review_note, reviewer)
                st.session_state["suggestion_review_saved"] = True
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        with st.expander("Suggestion history"):
            st.dataframe(pd.DataFrame([{"When (UTC)": e["at"], "Status": STATUSES[e["status"]],
                "Name": e["by"] or "Not supplied", "Note": e["note"]} for e in record["history"]]), hide_index=True)
    st.download_button("Export all suggestions", json.dumps(records, ensure_ascii=False, indent=2),
                       "suggestions.json", "application/json")
