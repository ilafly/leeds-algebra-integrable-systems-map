"""Synthetic PDFs and text artefacts; never inserted into the live dataset."""
import hashlib
import io

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from conftest import paper
from kgmap import fulltext
from kgmap.core import dump_json
from kgmap.graph import build_graph, filtered_snapshot
from kgmap.http import SourceError
from kgmap.pipeline import analyse


def pdf_bytes(lines, pages=1):
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        content = ['BT /F1 10 Tf 12 TL 30 750 Td']
        for line in lines:
            escaped = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            content.append('(' + escaped + ') Tj T*')
        content.append('ET')
        stream.set_data('\n'.join(content).encode('latin-1'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    result = io.BytesIO()
    writer.write(result)
    return result.getvalue()


def install_document(tmp_path, monkeypatch, p, text):
    monkeypatch.setattr(fulltext, 'CACHE_ROOT', tmp_path)
    key = fulltext.artifact_key(p)
    doc = {'publication_id': p['id'], 'method': fulltext.EXTRACTOR_VERSION, 'status': 'ready',
           'source_url': 'https://example.org/paper.pdf', 'sha256': hashlib.sha256(text.encode()).hexdigest(),
           'cache_key': key, 'pages': [{'page': 2, 'text': text, 'analysis_text': text}],
           'page_count': 2, 'body_word_count': len(text.split())}
    dump_json(tmp_path / (key + '.json'), doc)
    p['full_text'] = {k: v for k, v in doc.items() if k != 'pages'}


def test_pdf_body_excludes_bibliography():
    p = paper('test-paper', ['a'], title='Hopf algebras and braid groups', abstract='')
    data = pdf_bytes([p['title'], *['Hopf algebras and braid groups have useful properties.'] * 30,
                      'References', 'Quantum groups are mentioned only in the bibliography.'])
    doc = fulltext.extract_pdf(data, p)
    assert doc['status'] == 'ready'
    assert doc['references_excluded']
    assert 'Quantum groups' in doc['pages'][0]['text']
    assert 'Quantum groups' not in doc['pages'][0]['analysis_text']


def test_wrong_title_and_non_pdf_are_rejected():
    p = paper('test-paper', ['a'], title='Hopf algebras and braid groups')
    with pytest.raises(SourceError, match='non-PDF'):
        fulltext.extract_pdf(b'<html>Sign in</html>', p)
    with pytest.raises(SourceError, match='title could not be corroborated'):
        fulltext.extract_pdf(pdf_bytes(['An entirely different psychology article']), p)


def test_extraction_limits_are_explicit():
    p = paper('test-paper', ['a'])
    with pytest.raises(SourceError, match='page limit'):
        fulltext.extract_pdf(pdf_bytes([p['title']], pages=2), p, {'max_pages': 1})
    doc = fulltext.extract_pdf(pdf_bytes([p['title']]), p)
    assert doc['status'] == 'needs_ocr_or_review'


def test_balanced_sampling_and_quarantine(researchers):
    records = [paper(f'{rid}-{i}', [rid]) for rid in ['test-a', 'test-b', 'test-c'] for i in range(4)]
    for p in records:
        p['arxiv_id'] = '2301.12345'
    selected = fulltext.balanced_sample(records, researchers, 6)
    assert [p['researcher_ids'][0] for p in selected] == ['test-a', 'test-b', 'test-c'] * 2
    records[0]['quarantined'] = True
    all_records = fulltext.balanced_sample(records, researchers, 0)
    assert len(all_records) == 11 and records[0] not in all_records


def test_page_evidence_and_metadata_baseline(tmp_path, monkeypatch, researchers):
    p = paper('fulltext-only-topic', ['test-a'], title='An investigation of examples', abstract='')
    install_document(tmp_path, monkeypatch, p, 'Hopf algebras and braid groups occur here.')
    snapshot = analyse(researchers[:2], [p])
    mentions = [m for m in snapshot['mentions'] if m['field'] == 'full_text']
    assert mentions and all(m['page'] == 2 and '#page=2' in m['source'] for m in mentions)
    assert not filtered_snapshot(snapshot, include_full_text=False)['concepts']
    assert not filtered_snapshot(snapshot, concept=mentions[0]['concept'], include_full_text=False)['publications']
    baseline = analyse(researchers[:2], [p], include_full_text=False)
    assert filtered_snapshot(baseline, include_full_text=True)['concepts']
    assert 'pages' not in p['full_text']  # Raw paper text stays out of the portable snapshot.


def test_fulltext_similarity_is_separate_and_has_coverage(tmp_path, monkeypatch, researchers):
    records = [paper('a-paper', ['test-a'], title='Examples and applications', abstract=''),
               paper('b-paper', ['test-b'], title='Examples and applications', abstract=''),
               paper('joint-paper', ['test-a', 'test-b'], title='Joint examples', abstract='')]
    for p in records:
        install_document(tmp_path, monkeypatch, p, 'Hopf algebras and braid groups. Quantum representations and invariants.')
    snapshot = analyse(researchers[:2], records)
    c = snapshot['connections'][0]
    assert c['components']['full_text_similarity'] == pytest.approx(1.0)
    assert c['components']['abstract_similarity'] == 0
    assert c['weights']['full_text_similarity'] == 0.1
    assert sum(c['weights'].values()) == pytest.approx(1)
    assert c['full_text_coverage'] == {'test-a': 2, 'test-b': 2}
    assert len(c['full_text_pairs']) == 1
    assert all('joint-paper' not in (pair['left'], pair['right']) for pair in c['full_text_pairs'])
    baseline = filtered_snapshot(snapshot, include_full_text=False)
    assert baseline['connections'][0]['score'] == 0


def test_missing_or_mismatched_cache_cannot_contribute(tmp_path, monkeypatch, researchers):
    p = paper('a-paper', ['test-a'], title='Examples and applications', abstract='')
    install_document(tmp_path, monkeypatch, p, 'Hopf algebras and braid groups.')
    snapshot = analyse(researchers[:2], [p])
    p['full_text']['sha256'] = 'incorrect'
    assert fulltext.document(p) is None
    assert not filtered_snapshot(snapshot)['mentions']


def test_arc_disappears_when_its_only_shared_topic_is_in_disabled_full_text(tmp_path, monkeypatch, researchers):
    records = [paper('left', ['test-a'], title='Lie algebras', abstract='We investigate examples.'),
               paper('right', ['test-b'], title='Quantum groups', abstract='We investigate examples.')]
    for p in records:
        install_document(tmp_path, monkeypatch, p, 'Hopf algebras occur here.')
    s = analyse(researchers[:2], records)
    assert any(e['type'] == 'THEMATIC_PROXIMITY' for *_, e in build_graph(s).edges(data=True))
    baseline = filtered_snapshot(s, include_full_text=False)
    assert baseline['connections'][0]['score'] > 0
    assert not baseline['connections'][0]['shared_concepts']
    assert not any(e['type'] == 'THEMATIC_PROXIMITY' for *_, e in build_graph(baseline).edges(data=True))


def test_public_source_guard_respects_robots_and_delay():
    class FakeHTTP:
        host_delays = {}
        def get(self, *args, **kwargs):
            return b'User-agent: *\nCrawl-delay: 15\nDisallow: /private\nAllow: /pdf\n'
    http = FakeHTTP()
    guard = fulltext.robots_guard(http)
    guard('https://example.org/pdf/test')
    assert http.host_delays['example.org'] == 15
    with pytest.raises(SourceError, match='disallows'):
        guard('https://example.org/private/test.pdf')
    with pytest.raises(SourceError, match='Local network'):
        guard('http://localhost/private.pdf')


def test_fulltext_pages_and_baseline_toggle_in_app(tmp_path, monkeypatch, researchers):
    from streamlit.testing.v1 import AppTest
    from kgmap.store import Store
    records = [paper('a-paper', ['test-a']), paper('b-paper', ['test-b'])]
    for p in records:
        install_document(tmp_path, monkeypatch, p, 'Hopf algebras and braid groups occur in this body text.')
    store = Store(tmp_path / 'app.sqlite')
    store.save(analyse(researchers[:2], records))
    monkeypatch.setattr('kgmap.store.Store', lambda: store)
    at = AppTest.from_file('app.py', default_timeout=30).run()
    assert not at.exception
    assert len([x for x in at.selectbox if x.label == 'PDF page']) >= 2
    assert any('body text' in x.value for x in at.text)
    at.toggle(key='include_full_text').set_value(False).run()
    assert not at.exception
    assert any('metadata analysis selected' in x.value for x in at.caption)
