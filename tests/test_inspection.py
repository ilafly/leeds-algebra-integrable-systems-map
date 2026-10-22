import json
import math

import pytest

from conftest import paper
from kgmap.graph import build_graph, filtered_snapshot, graph_view
from kgmap.inspection import EdgeInspector
from kgmap.pipeline import analyse
from kgmap.visualisation import graph_html


def test_cooccurrence_explains_counts_and_cites_both_topics(researchers):
    s = analyse(researchers[:2], [
        paper('joint-topics', ['test-a'], title='Hopf algebras and braid groups', abstract=''),
        paper('hopf-only', ['test-a'], title='Hopf algebras', abstract=''),
        paper('braid-only', ['test-b'], title='Braid groups', abstract=''),
    ])
    edge = s['concept_relations'][0]
    info = EdgeInspector(s).describe(edge['source_id'], edge['target_id'], edge)
    assert info['metric']['value'] == pytest.approx(1 / math.sqrt(2 * 2))
    assert '1 / √(2 × 2)' in info['facts'][1]['value']
    assert info['publication_count'] == 1
    assert {x['topic'] for x in info['publications'][0]['excerpts']} == {'Hopf algebras', 'braid groups'}
    assert 'does not establish an implication' in info['meaning']


def test_parallel_mention_edges_keep_their_exact_field_and_pdf_page(researchers):
    s = analyse(researchers[:2], [paper('p1', ['test-a'])])
    mention = dict(next(m for m in s['mentions'] if m['field'] == 'abstract'))
    mention.update(field='full_text', page=7, source='https://example.org/body.pdf#page=7', evidence='Exact page seven evidence.')
    s['mentions'].append(mention)
    g = build_graph(s)
    a, b, edge = next((a, b, e) for a, b, e in g.edges(data=True) if e.get('field') == 'full_text')
    info = EdgeInspector(s).describe(a, b, edge)
    excerpt = info['publications'][0]['excerpts'][0]
    assert excerpt['page'] == 7 and excerpt['url'].endswith('#page=7')
    assert excerpt['text'] == 'Exact page seven evidence.'
    assert 'PDF page 7' in info['facts'][0]['value']


def test_thematic_details_include_actual_weighted_components_and_independent_pairs(researchers):
    s = analyse(researchers[:2], [paper('left', ['test-a']), paper('right', ['test-b']), paper('joint', ['test-a', 'test-b'])])
    g = build_graph(s)
    a, b, edge = next((a, b, e) for a, b, e in g.edges(data=True) if e['type'] == 'THEMATIC_PROXIMITY')
    info = EdgeInspector(s).describe(a, b, edge, limit=1)
    assert sum(c['contribution'] for c in info['components']) == pytest.approx(edge['score'], abs=0.0001)
    assert info['shared_topics'] and not any(t.startswith('concept:') for t in info['shared_topics'])
    assert all(not p[side]['url'].endswith('/joint') for p in info['comparisons'] for side in ('left', 'right'))
    assert len(info['publications']) == 1 and info['publication_count'] == 3
    all_papers = EdgeInspector(s).describe(a, b, edge, limit=None)['publications']
    assert any(p['id'] == 'joint' and p['notes'] for p in all_papers)
    assert 'not a probability' in info['metric']['note']


def test_filtered_graph_details_exclude_outside_publication_evidence(researchers):
    s = analyse(researchers[:2], [paper('excluded-2023', ['test-a'], year=2023), paper('visible-2025', ['test-b'], year=2025)])
    visible = filtered_snapshot(s, years=(2025, 2025))
    g = graph_view(build_graph(visible), 'knowledge')
    a, b, edge = next(iter(g.edges(data=True)))
    info = EdgeInspector(visible).describe(a, b, edge)
    assert info['publication_count'] == 1
    assert {p['id'] for p in info['publications']} == {'visible-2025'}
    assert 'excluded-2023' not in json.dumps(info)


def test_graph_payload_escapes_source_text_and_keeps_readable_edge_details(researchers):
    s = analyse(researchers[:2], [paper('p1', ['test-a'])])
    hostile = '</script><script>alert(1)</script> INSPECTOR_SCRIPT PAYLOAD'
    s['publications'][0]['title'] = hostile
    rendered = graph_html(build_graph(s), snapshot=s, show_edge_labels=True)
    payload = json.loads(rendered.split('const records = ', 1)[1].split(';\n', 1)[0])
    assert payload['nodes']['p1']['label'] == hostile
    assert hostile not in rendered
    assert all('inspection' in edge for edge in payload['edges'].values())
    assert any(edge['inspection']['publications'][0]['title'] == hostile
               for edge in payload['edges'].values() if edge['inspection']['publications'])
