from __future__ import annotations

import streamlit as st

from .core import load_config
from .fulltext import eligible
from .http import SourceError
from .uploads import ingest_pdf, needs_pdf, publication_pdf, read_pdf


def render_pdf_upload(store, snapshot):
    result = st.session_state.pop("pdf_upload_result", None)
    if result:
        if result["status"] == "ready":
            st.success("PDF saved. Its text is now available to the analysis and page inspector.")
        else:
            st.info("PDF saved for OCR or review. Its text is not included in the analysis yet.")
        if result.get("export_warning"):
            st.warning(result["export_warning"])
    st.caption("Select a paper already in the map and upload its missing PDF. The title is checked, text is extracted, and the analysis is rebuilt. Files stay with this map; scans may need OCR.")
    publications = {p["id"]: p for p in snapshot["publications"]}
    missing = [p for p in publications.values() if eligible(p) and needs_pdf(p)]
    missing.sort(key=lambda p: (p.get("full_text", {}).get("status") != "unavailable", p["title"].casefold()))
    if not missing:
        st.info("Every eligible paper already has usable full text.")
        return
    st.caption(f"{len(missing)} eligible papers need a PDF or usable text. For a paper missing from the map entirely, attach its PDF in Suggestions.")
    epoch = st.session_state.get("pdf_upload_epoch", 0)
    with st.form("publication_upload_form_" + str(epoch)):
        pid = st.selectbox("Paper needing a PDF", [None, *(p["id"] for p in missing)],
                           format_func=lambda k: "Choose a paper" if k is None else publications[k]["title"],
                           key="pdf_upload_target_" + str(epoch))
        uploaded = st.file_uploader("PDF file", type=["pdf"], key="pdf_upload_file_" + str(epoch))
        submitted = st.form_submit_button("Upload PDF and update analysis", type="primary")
    if submitted:
        try:
            if not pid or uploaded is None:
                raise ValueError("Choose a paper and a PDF file.")
            with st.spinner("Checking the PDF and updating the map…"):
                result = ingest_pdf(store, pid, uploaded.getvalue(), uploaded.name, load_config().get("full_text"))
            st.session_state["pdf_upload_result"] = result
            st.session_state["pdf_upload_epoch"] = epoch + 1
            st.rerun()
        except (ValueError, SourceError, OSError, ImportError) as exc:
            st.error(str(exc))


def download_publication_pdf(publication, context):
    data = publication_pdf(publication)
    if data is not None:
        st.download_button("Download cached PDF", data,
                           publication.get("full_text", {}).get("filename", "paper.pdf"), "application/pdf",
                           key="download_pdf_" + context + publication["id"])


def render_suggestion_pdf(store, record, snapshot):
    attachment = record.get("attachment")
    if not attachment:
        return
    st.caption(f"Attached PDF: {attachment['filename']} · {attachment['page_count']} pages · text check: {attachment['status']}")
    body = read_pdf(attachment)
    if body is None:
        st.info("The PDF file is missing from this installation. Its saved attachment metadata is still available.")
        return
    st.download_button("Download attached PDF", body, attachment["filename"], "application/pdf",
                       key="suggestion_pdf_download_" + record["id"])
    with st.expander("Use attachment for a paper already in the map"):
        choices = {p["id"]: p for p in snapshot["publications"] if eligible(p) and needs_pdf(p)}
        if not choices:
            st.caption("All eligible papers already have usable text.")
            return
        st.caption("Choose the matching publication record. Its title will be checked before the file contributes to analysis.")
        pid = st.selectbox("Match attachment to paper", [None, *choices],
                           format_func=lambda k: "Choose a paper" if k is None else choices[k]["title"],
                           key="suggestion_pdf_target_" + record["id"])
        if st.button("Analyse attached PDF", key="suggestion_pdf_analyse_" + record["id"]):
            try:
                if not pid:
                    raise ValueError("Select the matching paper first.")
                with st.spinner("Checking the attachment and updating the map…"):
                    result = ingest_pdf(store, pid, body, attachment["filename"], load_config().get("full_text"))
                st.session_state["suggestion_pdf_used"] = result
                st.rerun()
            except (ValueError, SourceError, OSError, ImportError) as exc:
                st.error(str(exc))
