"""Synthetic PDF uploads are confined to temporary stores and directories."""
import io
import json

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from conftest import paper
from test_fulltext import pdf_bytes
from kgmap import fulltext, uploads
from kgmap.http import CachedHTTP, SourceError
from kgmap.pipeline import analyse
from kgmap.report import render_report
from kgmap.store import Store


@pytest.fixture
def upload_store(tmp_path, monkeypatch, researchers):
    monkeypatch.setattr(fulltext, 'CACHE_ROOT', tmp_path / 'text-cache')
    monkeypatch.setattr(uploads, 'UPLOAD_ROOT', tmp_path / 'uploads')
    store = Store(tmp_path / 'data/map.sqlite')
    p = paper('missing-paper', ['test-a'], title='Examples and applications', abstract='')
    p['arxiv_id'] = '2301.12345'
    store.save(analyse(researchers, [p]))
    return store


def supplied_pdf(title='Examples and applications'):
    return pdf_bytes([title, *['Hopf algebras and braid groups have useful properties.'] * 30,
                      'References', 'Quantum groups occur only in this bibliography.'])


def test_upload_indexes_pages_and_preserves_reviews_suggestions_and_authorship(upload_store):
    store = upload_store
    original = store.load()
    store.review('existing-review', 'accepted', 'Keep this decision.')
    suggestion = store.add_suggestion({'kind': 'other', 'title': 'Existing note', 'note': 'Keep this contribution.'})
    body = supplied_pdf()
    result = uploads.ingest_pdf(store, 'missing-paper', body, '../../supplied.pdf')
    s = store.load()
    p = s['publications'][0]
    assert result['status'] == 'ready' and result['origin'] == 'upload'
    assert result['filename'] == 'supplied.pdf'
    assert p['researcher_ids'] == original['publications'][0]['researcher_ids']
    assert store.reviews()['existing-review']['status'] == 'accepted'
    assert store.suggestions() == [suggestion]
    assert uploads.publication_pdf(p) == body
    doc = fulltext.document(p)
    assert doc and doc['references_excluded']
    mentions = [m for m in s['mentions'] if m['field'] == 'full_text']
    assert mentions and all(m['page'] == 1 and m['source'].startswith('upload:') for m in mentions)
    assert not any(s['concepts'][m['concept']]['label'] == 'quantum groups' for m in mentions)
    assert 'pages' not in p['full_text']
    assert json.loads((store.path.parent / 'snapshot.json').read_text()) == s
    report = render_report(s)
    assert 'Uploaded PDF: supplied.pdf' in report and '](upload:' not in report
    assert 'user-supplied' in report


def test_upload_survives_metadata_restore_and_public_pdf_refresh(upload_store, monkeypatch):
    store = upload_store
    uploads.ingest_pdf(store, 'missing-paper', supplied_pdf(), 'supplied.pdf')
    s = store.load()
    s['publications'][0].pop('full_text')
    fulltext.restore_cached_text(s['publications'])
    assert s['publications'][0]['full_text']['origin'] == 'upload'
    http = CachedHTTP(store, refresh=True)
    def forbidden(*args, **kwargs):
        raise AssertionError('A public refresh must preserve the uploaded PDF')
    monkeypatch.setattr(http.session, 'get', forbidden)
    result = fulltext.retrieve_full_text(s['publications'], s['researchers'], http, limit=1)
    assert result['status_counts'] == {'ready': 1}


def test_uploaded_comparisons_cite_publication_records(upload_store):
    uploads.ingest_pdf(upload_store, 'missing-paper', supplied_pdf(), 'first.pdf')
    s = upload_store.load()
    second = paper('second-paper', ['test-b'], title='Examples and applications II', abstract='')
    upload_store.save(analyse(s['researchers'], [*s['publications'], second], s['collection']))
    uploads.ingest_pdf(upload_store, 'second-paper', supplied_pdf('Examples and applications II'), 'second.pdf')
    s = upload_store.load()
    comparison = next(c for c in s['connections'] if c['full_text_pairs'])
    assert comparison['components']['full_text_similarity'] == pytest.approx(1.0)
    assert all(fulltext.citation_url(p) == p['url'] for p in s['publications'])
    report = render_report(s)
    assert 'Includes a locally uploaded PDF.' in report and '](upload:' not in report
    # Historical comparisons remain printable if an artifact's metadata is lost.
    s['publications'][0].pop('full_text')
    assert 'Independent full-text comparisons' in render_report(s)


@pytest.mark.parametrize('body, options, error', [
    (b'<html>not a paper</html>', {}, 'non-PDF'),
    (supplied_pdf('An unrelated psychology investigation'), {}, 'title could not be corroborated'),
    (supplied_pdf(), {'max_pdf_mb': 0.00001}, 'size limit'),
    (supplied_pdf(), {'max_pages': 0}, 'page limit'),
])
def test_rejected_upload_does_not_modify_the_map(upload_store, body, options, error):
    original = upload_store.load()
    with pytest.raises((SourceError, ValueError), match=error):
        uploads.ingest_pdf(upload_store, 'missing-paper', body, 'paper.pdf', options)
    assert upload_store.load() == original
    assert not uploads.UPLOAD_ROOT.exists()


def test_scanned_pdf_is_saved_but_not_indexed(upload_store):
    body = pdf_bytes([])
    result = uploads.ingest_pdf(upload_store, 'missing-paper', body, 'scan.pdf')
    p = upload_store.load()['publications'][0]
    assert result['status'] == 'needs_ocr_or_review'
    assert fulltext.document(p) is None
    assert uploads.publication_pdf(p) == body
    assert not upload_store.load()['mentions']


def test_failed_analysis_rolls_back_the_active_document(upload_store, monkeypatch):
    original = upload_store.load()
    def fail(*args, **kwargs):
        raise RuntimeError('Analysis failed')
    monkeypatch.setattr('kgmap.pipeline.analyse', fail)
    with pytest.raises(RuntimeError, match='Analysis failed'):
        uploads.ingest_pdf(upload_store, 'missing-paper', supplied_pdf(), 'paper.pdf')
    assert upload_store.load() == original
    assert not (fulltext.CACHE_ROOT / (fulltext.artifact_key(original['publications'][0]) + '.json')).exists()


def test_usable_existing_text_is_not_replaced_and_repeated_upload_is_idempotent(upload_store):
    first = uploads.ingest_pdf(upload_store, 'missing-paper', supplied_pdf(), 'first.pdf')
    again = uploads.ingest_pdf(upload_store, 'missing-paper', supplied_pdf(), 'first.pdf')
    assert first['sha256'] == again['sha256']
    assert len(upload_store.load()['collection']['uploads']) == 1
    different = supplied_pdf() + b'\n% another file'
    with pytest.raises(ValueError, match='already has usable full text'):
        uploads.ingest_pdf(upload_store, 'missing-paper', different, 'replacement.pdf')
    assert upload_store.load()['publications'][0]['full_text']['sha256'] == first['sha256']
    (uploads.UPLOAD_ROOT / (first['sha256'] + '.pdf')).unlink()
    assert uploads.needs_pdf(upload_store.load()['publications'][0])
    uploads.ingest_pdf(upload_store, 'missing-paper', supplied_pdf(), 'restored.pdf')
    assert uploads.publication_pdf(upload_store.load()['publications'][0]) == supplied_pdf()
    assert len(upload_store.load()['collection']['uploads']) == 1


def test_pdf_attachment_can_supply_a_joint_work_source_without_adding_a_publication(upload_store):
    original = upload_store.load()
    record = upload_store.add_suggestion({'kind': 'joint_work', 'title': 'A new paper to review',
        'researcher_ids': ['test-a', 'test-b'], 'note': 'Please check the attached paper.'},
        attachment={'filename': 'attachment.pdf', 'body': supplied_pdf()})
    assert record['status'] == 'pending' and record['source_url'] == ''
    assert record['attachment']['status'] == 'needs_title_review'
    assert uploads.read_pdf(record['attachment']) == supplied_pdf()
    assert upload_store.load() == original
    assert 'pages' not in record['attachment']


def test_quarantined_authorship_cannot_be_bypassed_by_pdf_upload(upload_store):
    s = upload_store.load()
    s['publications'][0]['quarantined'] = True
    upload_store.save(s)
    with pytest.raises(ValueError, match='corroborated authorship'):
        uploads.ingest_pdf(upload_store, 'missing-paper', supplied_pdf(), 'paper.pdf')
    assert upload_store.load() == s


class SuppliedFile(io.BytesIO):
    name = 'provided.pdf'


def test_publications_upload_action_updates_the_app(upload_store, monkeypatch):
    monkeypatch.setattr('kgmap.store.Store', lambda: upload_store)
    monkeypatch.setattr(st, 'file_uploader', lambda label, **kwargs:
        SuppliedFile(supplied_pdf()) if kwargs.get('key', '').startswith('pdf_upload_file_') else None)
    at = AppTest.from_file('app.py', default_timeout=30).run()
    at.selectbox(key='pdf_upload_target_0').set_value('missing-paper')
    next(x for x in at.button if x.label == 'Upload PDF and update analysis').click().run()
    assert not at.exception
    assert fulltext.document(upload_store.load()['publications'][0])
    assert any('PDF saved' in x.value for x in at.success)
    assert any('Uploaded file: provided.pdf' in x.value for x in at.caption)


def test_suggestion_attachment_can_be_matched_and_analysed_in_app(upload_store, monkeypatch):
    monkeypatch.setattr('kgmap.store.Store', lambda: upload_store)
    monkeypatch.setattr(st, 'file_uploader', lambda label, **kwargs:
        SuppliedFile(supplied_pdf()) if kwargs.get('key', '').startswith('suggestion_pdf_') else None)
    at = AppTest.from_file('app.py', default_timeout=30).run()
    at.text_input(key='suggestion_title').set_value('New work to review')
    at.multiselect(key='suggestion_people').set_value(['test-a', 'test-b'])
    at.text_area(key='suggestion_note').set_value('Please inspect the attached file.')
    next(x for x in at.button if x.label == 'Submit suggestion').click().run()
    assert not at.exception
    record = upload_store.suggestions()[0]
    at.selectbox(key='suggestion_pdf_target_' + record['id']).set_value('missing-paper')
    next(x for x in at.button if x.label == 'Analyse attached PDF').click().run()
    assert not at.exception
    assert fulltext.document(upload_store.load()['publications'][0])
    assert upload_store.suggestions()[0]['status'] == 'pending'
    assert upload_store.load()['publications'][0]['researcher_ids'] == ['test-a']
