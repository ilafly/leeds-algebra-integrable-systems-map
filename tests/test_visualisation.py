import json
import re

from conftest import paper
from kgmap.graph import build_graph, graph_view, without_publications
from kgmap.pipeline import analyse
from kgmap.visualisation import graph_html


def rendered_edges(graph, snapshot, path=None, show_edge_labels=False):
    rendered = graph_html(graph, path=path, snapshot=snapshot, show_edge_labels=show_edge_labels)
    data = re.search(r'edges = new vis.DataSet\((\[.*?\])\);', rendered, re.S)
    return {edge['id']: edge for edge in json.loads(data.group(1))}


def test_dotted_edge_width_tracks_score_and_is_stable_across_filters(researchers):
    s = analyse(researchers, [paper('a', ['test-a']), paper('b', ['test-b']),
        paper('c', ['test-c'], title='Hopf algebras', abstract='An investigation of examples.')])
    g = graph_view(build_graph(s), 'researchers')
    thematic = sorted((d for *_, d in g.edges(data=True)), key=lambda d: d['score'])
    low, high = thematic[0], thematic[-1]
    assert low['score'] < high['score']
    edges = rendered_edges(g, s)
    assert edges[low['id']]['dashes'] and edges[high['id']]['dashes']
    assert edges[low['id']]['width'] < edges[high['id']]['width']
    nodes = ['researcher:' + high[k] for k in ('researcher_a', 'researcher_b')]
    subset = g.subgraph(nodes)
    assert rendered_edges(subset, s)[high['id']]['width'] == edges[high['id']]['width']
    highlighted = rendered_edges(g, s, path=nodes)
    assert highlighted[high['id']]['width'] > edges[high['id']]['width']
    assert highlighted[high['id']]['color'] == '#CB4B32'


def test_plain_labels_keep_parallel_social_and_thematic_relationships(researchers):
    s = analyse(researchers[:2], [paper('left', ['test-a']), paper('right', ['test-b']),
                                 paper('joint', ['test-a', 'test-b'])])
    g = build_graph(s)
    edges = rendered_edges(g, s, show_edge_labels=True)
    assert len(edges) == g.number_of_edges()
    labels = {e['label'] for e in edges.values() if e['label']}
    assert 'Mentions topic' in labels and 'Coauthored (1 paper)' in labels
    assert any(label.startswith('Thematic candidate: ') for label in labels)
    assert all(label.isascii() for label in labels)
    assert all(e['font']['align'] == 'horizontal' and e['font']['multi'] is False for e in edges.values())
    assert all(not end['enabled'] for e in edges.values() for end in e['arrows'].values())
    paired = [edges[d['id']] for *_, d in g.edges(data=True)
              if d['type'] in {'COAUTHORED_WITH', 'THEMATIC_PROXIMITY'}]
    assert len(paired) == 2 and {e['smooth']['type'] for e in paired} == {'curvedCW', 'curvedCCW'}
    # Repeated text fields keep their inspectable edges but print one label.
    mentions = [edges[d['id']] for *_, d in g.edges(data=True)
                if d['type'] == 'DISCUSSES' and d['owner'] == 'left' and d['matched_phrase'] == 'hopf algebras']
    assert len(mentions) == 2 and sum(bool(e['label']) for e in mentions) == 1
    assert all(not e['label'] for e in rendered_edges(g, s).values())


def test_projected_links_render_with_their_source_papers(researchers):
    s = analyse(researchers[:2], [paper('left', ['test-a']), paper('right', ['test-b'])])
    g = without_publications(build_graph(s))
    rendered = graph_html(g, snapshot=s, show_edge_labels=True)
    payload = json.loads(rendered.split('const records = ', 1)[1].split(';\n', 1)[0])
    assert all(n['kind'] != 'publication' for n in payload['nodes'].values())
    links = [edge for edge in payload['edges'].values() if edge['type'] == 'PAPERS_MENTION']
    assert links and all(edge['inspection']['publications'] for edge in links)
    assert all(edge['inspection']['short_label'] == 'Papers mention topic (1)' for edge in links)
