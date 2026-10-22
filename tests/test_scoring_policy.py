import pytest
from streamlit.testing.v1 import AppTest

from conftest import paper
from kgmap.connections import FULL_TEXT_WEIGHTS, WEIGHTS, thematic_candidate
from kgmap.graph import build_graph, filtered_snapshot, graph_view
from kgmap.pipeline import analyse
from kgmap.report import render_report
from kgmap.store import Store


def different_topics():
    abstract = 'We investigate examples and establish several useful properties using an explicit calculation.'
    return [paper('left', ['test-a'], title='Lie algebras', abstract=abstract),
            paper('right', ['test-b'], title='Quantum groups', abstract=abstract)]


def test_high_text_similarity_cannot_create_arc_without_shared_topics(researchers):
    s = analyse(researchers[:2], different_topics())
    c = s['connections'][0]
    assert not c['shared_concepts']
    assert c['components']['abstract_similarity'] == 1
    assert c['score'] == pytest.approx(0.20)  # Retain the calculation for audit.
    assert not thematic_candidate(c, threshold=0)
    g = build_graph(s)
    assert not any(e['type'] == 'THEMATIC_PROXIMITY' for *_, e in g.edges(data=True))
    assert graph_view(g, 'researchers', threshold=0).number_of_edges() == 0
    assert '### Test Author A ↔ Test Author B' not in render_report(s)
    assert '1 pairs with no shared extracted topics are omitted' in render_report(s)


def test_view_also_excludes_legacy_arc_without_shared_topics(researchers):
    s = analyse(researchers[:2], different_topics())
    g = build_graph(s)
    c = s['connections'][0]
    g.add_edge('researcher:test-a', 'researcher:test-b', key=c['id'],
               **{**c, 'type': 'THEMATIC_PROXIMITY', 'confidence': c['score']})
    assert graph_view(g, 'researchers', threshold=0).number_of_edges() == 0


def test_shared_topic_candidate_still_obeys_threshold(researchers):
    s = analyse(researchers[:2], [paper('left', ['test-a']), paper('right', ['test-b'])])
    c = s['connections'][0]
    assert thematic_candidate(c, c['score'])
    assert not thematic_candidate(c, c['score'] + 0.0001)
    assert sum(WEIGHTS.values()) == pytest.approx(1)
    assert sum(FULL_TEXT_WEIGHTS.values()) == pytest.approx(1)
    assert WEIGHTS['shared_concepts'] > sum(v for k, v in WEIGHTS.items() if k != 'shared_concepts')
    assert FULL_TEXT_WEIGHTS['shared_concepts'] > sum(v for k, v in FULL_TEXT_WEIGHTS.items() if k != 'shared_concepts')


def test_date_filter_rechecks_shared_topic_requirement(researchers):
    records = different_topics()
    records.append(paper('old-shared-topic', ['test-a', 'test-b'], year=2023, title='Hopf algebras', abstract=''))
    s = analyse(researchers[:2], records)
    assert thematic_candidate(s['connections'][0])
    filtered = filtered_snapshot(s, years=(2024, 2024))
    assert filtered['connections'][0]['score'] > 0
    assert not filtered['connections'][0]['shared_concepts']
    assert graph_view(build_graph(filtered), 'researchers').number_of_edges() == 0


def test_bibliographic_coauthorship_has_its_own_evidence(researchers):
    s = analyse(researchers[:2], [paper('joint', ['test-a', 'test-b'], title='General examples', abstract='')])
    assert not s['connections'][0]['shared_concepts']
    edges = [e['type'] for *_, e in graph_view(build_graph(s), 'researchers').edges(data=True)]
    assert edges == ['COAUTHORED_WITH']


def test_app_omits_zero_topic_candidate_even_at_zero_threshold(tmp_path, monkeypatch, researchers):
    store = Store(tmp_path / 'app.sqlite')
    store.save(analyse(researchers[:2], different_topics()))
    monkeypatch.setattr('kgmap.store.Store', lambda: store)
    at = AppTest.from_file('app.py', default_timeout=30).run()
    at.radio(key='map_view').set_value('Researcher network').run()
    at.slider(key='candidate_threshold').set_value(0.0).run()
    assert not at.exception
    assert any('1 pairs omitted' in x.value for x in at.caption)
    assert any('No relationships pass' in x.value for x in at.caption)
    assert any('No researcher pairs have shared extracted topics' in x.value for x in at.info)
