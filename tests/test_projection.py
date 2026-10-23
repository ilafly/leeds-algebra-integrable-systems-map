import copy

from conftest import paper
from kgmap.core import stable_id
from kgmap.graph import build_graph, filtered_snapshot, graph_view, researcher_path, without_publications
from kgmap.inspection import EdgeInspector
from kgmap.pipeline import analyse


def topic_link(graph, researcher='test-a', label='Hopf algebras'):
    return next((a, b, edge) for a, b, edge in graph.edges(data=True)
                if edge['type'] == 'PAPERS_MENTION' and 'researcher:' + researcher in (a, b)
                and any(graph.nodes[n]['label'] == label for n in (a, b)))


def test_hidden_papers_keep_topics_evidence_and_scores(researchers):
    s = analyse(researchers[:2], [paper('left', ['test-a']), paper('right', ['test-b']),
                                 paper('joint', ['test-a', 'test-b'])])
    original = copy.deepcopy(s)
    graph = build_graph(s)
    projected = without_publications(graph)
    assert s == original
    assert 'left' in graph and 'left' not in projected
    assert {d['kind'] for _, d in projected.nodes(data=True)} == {'researcher', 'concept'}
    a, b, edge = topic_link(projected)
    assert edge['evidence']['publication_ids'] == ['joint', 'left']
    # Title and abstract matches count as one paper, with their evidence retained.
    assert len(edge['evidence']['mention_ids']) == 4
    info = EdgeInspector(s, projected).describe(a, b, edge)
    assert info['publication_count'] == 2 and info['status'] == 'extracted'
    assert {p['id'] for p in info['publications']} == {'left', 'joint'}
    assert all(p['excerpts'] for p in info['publications'])
    assert 'does not establish expertise' in info['meaning']
    before = {d['id']: d for *_, d in graph.edges(data=True) if d['type'] == 'THEMATIC_PROXIMITY'}
    after = {d['id']: d for *_, d in projected.edges(data=True) if d['type'] == 'THEMATIC_PROXIMITY'}
    assert before == after
    assert any(d['type'] == 'COAUTHORED_WITH' for *_, d in projected.edges(data=True))


def test_rejected_extractions_do_not_reappear_in_projected_inspector(researchers):
    s = analyse(researchers[:2], [paper('left', ['test-a'])])
    reviews = {stable_id('mention', m['owner'], m['concept'], m['field']): {'status': 'rejected'}
               for m in s['mentions'] if m['field'] == 'abstract'}
    graph = without_publications(build_graph(s, reviews))
    a, b, edge = topic_link(graph)
    info = EdgeInspector(s, graph).describe(a, b, edge)
    assert {e['field'] for p in info['publications'] for e in p['excerpts']} == {'Title'}
    # Rejecting the authorship removes the entire derived path.
    reviews[stable_id('authored', 'test-a', 'left')] = {'status': 'rejected'}
    assert not any(d['type'] == 'PAPERS_MENTION'
                   for *_, d in without_publications(build_graph(s, reviews)).edges(data=True))


def test_projection_obeys_sample_filters_and_does_not_create_thematic_shortcuts(researchers):
    s = analyse(researchers[:2], [paper('old', ['test-a'], year=2023), paper('new', ['test-b'], year=2025)])
    projected = without_publications(build_graph(filtered_snapshot(s, years=(2025, 2025))))
    assert all(d['evidence']['publication_ids'] == ['new'] for *_, d in projected.edges(data=True)
               if d['type'] == 'PAPERS_MENTION')
    assert not any(a == 'researcher:test-a' or b == 'researcher:test-a' for a, b in projected.edges())
    full = without_publications(build_graph(s))
    path = researcher_path(full, 'test-a', 'test-b')
    assert len(path) == 3 and full.nodes[path[1]]['kind'] == 'concept'
    themes_only = graph_view(full, 'integrated', types=['THEMATIC_PROXIMITY'])
    assert not researcher_path(themes_only, 'test-a', 'test-b')
    assert all(d['type'] == 'PAPERS_MENTION' for *_, d in
               graph_view(full, 'integrated', threshold=1, types=['PAPERS_MENTION']).edges(data=True))


def test_profile_mentions_remain_separate_and_held_papers_are_excluded(researchers):
    researchers[0]['profile']['descriptions'] = [{'text': 'Hopf algebras', 'source': 'https://example.org/profile'}]
    s = analyse(researchers[:2], [paper('left', ['test-a'])])
    graph = without_publications(build_graph(s))
    a, b, _ = topic_link(graph)
    assert {d['type'] for d in graph[a][b].values()} == {'RESEARCHES', 'PAPERS_MENTION'}
    for flag in ('quarantined', 'is_retracted'):
        held = copy.deepcopy(s)
        held['publications'][0][flag] = True
        projected = without_publications(build_graph(held))
        assert not any(d['type'] == 'PAPERS_MENTION' for *_, d in projected.edges(data=True))
