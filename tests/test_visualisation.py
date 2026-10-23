import json
import re

from conftest import paper
from kgmap.graph import build_graph, graph_view
from kgmap.pipeline import analyse
from kgmap.visualisation import graph_html


def rendered_edges(graph, snapshot, path=None):
    rendered = graph_html(graph, path=path, snapshot=snapshot)
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
