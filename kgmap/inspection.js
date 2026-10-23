// Relationship details use text nodes so source text never becomes executable HTML.
(() => {
  const box = document.getElementById('inspection');
  function node(tag, text, parent, className) {
    const el = document.createElement(tag);
    if (text != null) el.textContent = text;
    if (className) el.className = className;
    if (parent) parent.append(el);
    return el;
  }
  function link(parent, title, url) {
    let parsed;
    try { parsed = new URL(url); } catch { return node('span', title, parent); }
    if (!['http:', 'https:'].includes(parsed.protocol)) return node('span', title, parent);
    const el = node('a', title, parent);
    el.href = parsed.href; el.target = '_blank'; el.rel = 'noopener noreferrer';
    return el;
  }
  function section(title) { node('h4', title, box); }
  function list(title, items) {
    if (!items.length) return;
    section(title);
    const ul = node('ul', null, box);
    items.forEach(item => node('li', item, ul));
  }
  function excerpt(parent, item) {
    const location = item.field + (item.page ? ' · PDF page ' + item.page : '');
    node('div', item.topic + ' · ' + location, parent, 'evidence-location');
    node('blockquote', item.text, parent);
    if (item.url.startsWith('upload:'))
      node('div', 'Uploaded PDF · download this paper from Publications.', parent, 'inspection-note');
    else link(parent, 'Read this source' + (item.page ? ' at page ' + item.page : ''), item.url);
  }
  function rawRecord(parent, record) {
    const details = node('details', null, parent);
    node('summary', 'Original record and provenance', details);
    node('pre', JSON.stringify(record, null, 2), details);
  }
  function showEdge(record) {
    const d = record.inspection;
    box.replaceChildren(); box.scrollTop = 0;
    node('div', d.label + ' · ' + d.status + ' · review: ' + d.review, box, 'inspection-meta');
    node('h3', d.title, box);
    node('p', d.summary, box);
    node('p', d.meaning, box, 'inspection-note');
    if (d.review_note) node('p', 'Reviewer note: ' + d.review_note, box);
    if (d.metric) {
      node('strong', d.metric.label + ': ' + d.metric.value.toFixed(3), box);
      node('div', d.metric.note, box, 'inspection-note');
    }
    d.facts.forEach(f => node('p', f.label + ': ' + f.value, box));
    list('Shared topics', d.shared_topics);
    if (d.components.length) {
      section('Score breakdown');
      const table = node('table', null, box);
      const head = node('tr', null, node('thead', null, table));
      ['Component', 'Value', 'Weight', 'Contribution'].forEach(t => node('th', t, head));
      const body = node('tbody', null, table);
      d.components.forEach(c => {
        const row = node('tr', null, body);
        const label = node('td', c.label, row); label.title = c.explanation;
        [c.value, c.weight, c.contribution].forEach(v => node('td', v.toFixed(4), row));
      });
      const definitions = node('details', null, box);
      node('summary', 'How the components are calculated', definitions);
      d.components.forEach(c => node('p', c.label + ': ' + c.explanation, definitions));
    }
    list('Candidate topic bridges', d.bridges);
    list('Intermediate topic paths', d.paths);
    if (d.comparisons.length) {
      section('Independent paper comparisons');
      d.comparisons.forEach(pair => {
        const item = node('div', null, box, 'evidence-paper');
        node('div', pair.label + ' · cosine ' + pair.similarity.toFixed(3), item, 'evidence-location');
        link(item, pair.left.title, pair.left.url);
        node('span', ' ↔ ', item);
        link(item, pair.right.title, pair.right.url);
      });
    }
    if (d.excerpt) { section('Source excerpt'); excerpt(box, d.excerpt); }
    if (d.publications.length) {
      section('Supporting publications (' + d.publications.length + ' of ' + d.publication_count + ')');
      d.publications.forEach(p => {
        const item = node('article', null, box, 'evidence-paper');
        link(item, p.title, p.url);
        node('div', (p.date || 'Date unknown') + (p.notes ? ' · ' + p.notes : ''), item, 'inspection-note');
        p.excerpts.forEach(e => excerpt(item, e));
      });
      if (d.publication_count > d.publications.length)
        node('p', 'Use “Inspect a relationship” below the map to show all supporting papers.', box, 'inspection-note');
    }
    section('How this link was created'); node('p', d.method, box);
    if (d.sources.length) {
      const sources = node('details', null, box);
      node('summary', 'Source links (' + d.sources.length + ' of ' + d.source_count + ')', sources);
      d.sources.forEach(url => link(node('p', null, sources), url, url));
    }
    const {inspection, ...original} = record;
    rawRecord(box, original);
  }
  function showNode(record) {
    box.replaceChildren(); box.scrollTop = 0;
    node('h3', record.label, box); node('p', record.kind, box);
    rawRecord(box, record.details);
    const urls = new Set();
    function collect(value) {
      if (typeof value === 'string' && /^https?:\/\/[^\s]+$/.test(value)) urls.add(value);
      else if (Array.isArray(value)) value.forEach(collect);
      else if (value && typeof value === 'object') Object.values(value).forEach(collect);
    }
    collect(record.details);
    urls.forEach(url => link(node('p', null, box), url, url));
  }
  network.on('click', params => {
    if (params.nodes.length) showNode(records.nodes[params.nodes[0]]);
    else if (params.edges.length) showEdge(records.edges[params.edges[0]]);
  });
  network.once('stabilizationIterationsDone', () => network.setOptions({physics: {enabled: false}}));
})();
