"""Synthetic unit-test records; never imported into the application dataset."""
import pytest


@pytest.fixture
def researchers():
    return [{"id": rid, "name": name, "affiliation": "Test University", "status": "verified",
             "openalex_id": "https://openalex.org/" + rid, "profile": {"descriptions": [], "sources": []}, "reason": "Synthetic test fixture"}
            for rid, name in [("test-a", "Test Author A"), ("test-b", "Test Author B"), ("test-c", "Test Author C")]]


def paper(pid, owners, title="Hopf algebras and braid groups", year=2024, abstract="Hopf algebras and braid groups give quantum invariants."):
    return {"id": pid, "title": title, "abstract": abstract, "date": f"{year}-01-01", "year": year,
            "doi": None, "arxiv_id": None, "openalex_ids": [pid], "url": "https://example.org/" + pid,
            "urls": ["https://example.org/" + pid], "authors": [{"name": rid, "openalex_id": "https://openalex.org/" + rid} for rid in owners],
            "researcher_ids": owners, "provenance": [{"source": "https://example.org/" + pid, "provider": "test_fixture",
                                                     "fields": ["title", "abstract"]}], "is_retracted": False}
