from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path

from pyvis.network import Network

from .inspection import EdgeInspector, edge_tooltip

COLORS = {"researcher": "#176B63", "publication": "#647D9D", "concept": "#C38737"}
EDGE_COLORS = {"AUTHORED": "#74869D", "COAUTHORED_WITH": "#176B63", "DISCUSSES": "#B5AA85",
               "RESEARCHES": "#B5AA85", "RELATED_TO": "#D0A45F", "THEMATIC_PROXIMITY": "#9A79B6"}


def edge_width(attrs, highlighted=False):
    """Use an absolute scale so filtering cannot change the same edge's width."""
    if attrs.get("status") == "candidate":
        score = float(attrs.get("score", attrs.get("confidence", 0)))
        score = min(1.0, max(0.0, score)) if math.isfinite(score) else 0.0
        width = 1.2 + 6.0 * score
    else:
        width = 3.0 if attrs["type"] == "COAUTHORED_WITH" else 1.3
    return round(width + (2.0 if highlighted else 0.0), 3)


def graph_html(graph, path=None, snapshot=None, show_edge_labels=False):
    path = path or []
    highlighted = {frozenset([a, b]) for a, b in zip(path, path[1:])}
    network = Network(height="500px", width="100%", bgcolor="#FAFBF8", font_color="#203631", cdn_resources="in_line", directed=False)
    payload = {"nodes": {}, "edges": {}}
    inspector = EdgeInspector(snapshot, graph)
    for node, attrs in graph.nodes(data=True):
        kind, label = attrs["kind"], attrs["label"]
        shape = {"researcher": "dot", "publication": "square", "concept": "dot"}[kind]
        size = {"researcher": 26, "publication": 9, "concept": 12}[kind]
        short = label if len(label) <= 42 else label[:39] + "…"
        network.add_node(node, label=short, title=html.escape(label), color=COLORS[kind], shape=shape, size=size,
                         borderWidth=4 if node in path else 1, font={"size": 16 if kind == "researcher" else 12})
        payload["nodes"][node] = {"label": label, "kind": kind, "details": attrs.get("details", attrs)}
    for a, b, key, attrs in graph.edges(keys=True, data=True):
        candidate = attrs.get("status") == "candidate"
        selected = frozenset([a, b]) in highlighted
        detail = inspector.describe(a, b, attrs)
        tooltip = "<br>".join(html.escape(line) for line in edge_tooltip(detail).splitlines())
        network.add_edge(a, b, id=key, title=tooltip,
            label=detail["short_label"] if show_edge_labels else "", font={"size": 10, "align": "middle", "strokeWidth": 3, "strokeColor": "#FAFBF8"},
            color="#CB4B32" if selected else EDGE_COLORS.get(attrs["type"], "#82958F"),
            width=edge_width(attrs, selected),
            dashes=candidate, smooth={"enabled": True, "type": "dynamic"})
        payload["edges"][key] = {**attrs, "inspection": detail}
    network.set_options(json.dumps({"physics": {"enabled": True, "solver": "forceAtlas2Based",
        "forceAtlas2Based": {"gravitationalConstant": -65, "centralGravity": 0.015, "springLength": 125, "springConstant": 0.045},
        "stabilization": {"enabled": True, "iterations": 180, "fit": True}},
        "layout": {"randomSeed": 42}, "interaction": {"hover": True, "navigationButtons": False, "keyboard": True},
        "edges": {"selectionWidth": 3}, "nodes": {"borderWidth": 1}}))
    doc = network.generate_html(notebook=False)
    # PyVis includes optional Bootstrap CDN markup; the graph needs no Bootstrap.
    doc = re.sub(r'<link[^>]+href="https://cdn\.jsdelivr\.net/[^>]*>', '', doc)
    doc = re.sub(r'<script[^>]+src="https://cdn\.jsdelivr\.net/[^>]*>\s*</script>', '', doc)
    serialised = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    panel = """
    <style>body{margin:0;font-family:system-ui,sans-serif;color:#203631;background:#fafbf8}
    #mynetwork{border:1px solid #dae3db!important;border-radius:12px;}
    .card{border:0!important;background:transparent!important}
    .vis-tooltip{max-width:460px;white-space:normal!important;line-height:1.5}
    #inspection{box-sizing:border-box;padding:16px 20px;background:#eff3ee;border:1px solid #dae3db;border-radius:10px;margin-top:10px;height:320px;overflow:auto;font-size:13px;line-height:1.55;overflow-wrap:anywhere}
    #inspection h3{font-size:16px;margin:6px 0}#inspection h4{font-size:13px;margin:18px 0 6px}
    #inspection p{margin:8px 0}#inspection pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}
    #inspection a{color:#176b63}#inspection summary{cursor:pointer;margin-top:10px}
    #inspection table{border-collapse:collapse;width:100%;margin:8px 0}#inspection td,#inspection th{text-align:left;border-bottom:1px solid #cfdbd2;padding:5px 10px 5px 0}
    #inspection blockquote{margin:6px 0;padding-left:12px;border-left:3px solid #a6b9ab;white-space:pre-wrap}
    .inspection-meta,.evidence-location{font-size:11px;font-weight:600;color:#53665c}
    .inspection-note{color:#53665c;font-size:12px}.evidence-paper{padding:10px 0;border-bottom:1px solid #d7e0d7}</style>
    <div id="inspection" aria-live="polite" role="region" aria-label="Graph evidence"><b>Inspect a relationship</b><p>Hover over a link for a summary. Click it for an explanation, supporting papers, source excerpts and score details.</p><p>Drag nodes to arrange the map; scroll to zoom. The searchable relationship inspector below also lists the visible links.</p></div>
    <script>
    const records = PAYLOAD;
    INSPECTOR_SCRIPT
    </script>
    """.replace("INSPECTOR_SCRIPT", Path(__file__).with_name("inspection.js").read_text(encoding="utf-8")).replace("PAYLOAD", serialised)
    return doc.replace("</body>", panel + "</body>")
