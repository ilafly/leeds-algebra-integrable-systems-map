from __future__ import annotations

import html
import json
import re

from pyvis.network import Network

COLORS = {"researcher": "#176B63", "publication": "#647D9D", "concept": "#C38737"}
EDGE_COLORS = {"AUTHORED": "#74869D", "COAUTHORED_WITH": "#176B63", "DISCUSSES": "#B5AA85",
               "RESEARCHES": "#B5AA85", "RELATED_TO": "#D0A45F", "THEMATIC_PROXIMITY": "#9A79B6"}


def graph_html(graph, path=None):
    path = path or []
    highlighted = {frozenset([a, b]) for a, b in zip(path, path[1:])}
    network = Network(height="500px", width="100%", bgcolor="#FAFBF8", font_color="#203631", cdn_resources="in_line", directed=False)
    payload = {"nodes": {}, "edges": {}}
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
        network.add_edge(a, b, id=key, title=html.escape(attrs["type"] + " · " + attrs.get("status", "")),
            color="#CB4B32" if selected else EDGE_COLORS.get(attrs["type"], "#82958F"),
            width=4 if selected else (3 if attrs["type"] == "COAUTHORED_WITH" else 1.3),
            dashes=candidate, smooth={"enabled": True, "type": "dynamic"})
        payload["edges"][key] = attrs
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
    #inspection{padding:14px 18px;background:#eff3ee;border:1px solid #dae3db;border-radius:10px;margin-top:10px;max-height:160px;overflow:auto;font-size:13px}
    #inspection pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}#inspection a{color:#176b63}</style>
    <div id="inspection" aria-live="polite"><b>Inspect the evidence</b><p>Click a node or an edge. Drag nodes to arrange the map; scroll to zoom.</p></div>
    <script>
    const records = PAYLOAD;
    const box = document.getElementById('inspection');
    function showRecord(record) {
      box.replaceChildren();
      const title = document.createElement('b');title.textContent = record.label || record.type || 'Details';box.append(title);
      const pre = document.createElement('pre');pre.textContent = JSON.stringify(record,null,2);box.append(pre);
      let urls = new Set();
      function collect(value){if(typeof value === 'string' && /^https?:\\/\\/[^\\s]+$/.test(value))urls.add(value);
        else if(Array.isArray(value))value.forEach(collect);else if(value && typeof value==='object')Object.values(value).forEach(collect);}
      collect(record);
      urls.forEach(url=>{const link=document.createElement('a');link.href=url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=url;
        box.append(document.createElement('br'),link);});
    }
    network.on('click', params => {
      if(params.nodes.length)showRecord(records.nodes[params.nodes[0]]);
      else if(params.edges.length)showRecord(records.edges[params.edges[0]]);
    });
    network.once('stabilizationIterationsDone',()=>network.setOptions({physics:{enabled:false}}));
    </script>
    """.replace("PAYLOAD", serialised)
    return doc.replace("</body>", panel + "</body>")
