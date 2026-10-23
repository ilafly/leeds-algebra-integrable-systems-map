from streamlit.testing.v1 import AppTest

from kgmap.pipeline import analyse
from kgmap.store import Store
from kgmap.graph import build_graph
from kgmap.visualisation import graph_html
from conftest import paper


def app_with_fixture(tmp_path, monkeypatch, researchers):
    store = Store(tmp_path / "app.sqlite")
    store.save(analyse(researchers[:2], [paper("test-p1", ["test-a"], year=2023), paper("test-p2", ["test-b"], year=2025)]))
    monkeypatch.setattr("kgmap.store.Store", lambda: store)
    at = AppTest.from_file("app.py", default_timeout=30).run()
    assert not at.exception
    return at, store


def test_all_map_views_and_filters_execute(tmp_path, monkeypatch, researchers):
    at, _ = app_with_fixture(tmp_path, monkeypatch, researchers)
    for view in ["Researcher network", "Integrated map"]:
        at.radio(key="map_view").set_value(view).run()
        assert not at.exception
    at.selectbox(key="researcher_filter").set_value("test-a").run()
    assert not at.exception
    assert at.metric[1].value == "1"
    at.selectbox(key="researcher_filter").set_value(None).run()
    at.toggle(key="date_toggle").set_value(True).run()
    assert not at.exception
    at.slider(key="candidate_threshold").set_value(1.0).run()
    assert not at.exception


def test_review_form_persists_in_separate_test_database(tmp_path, monkeypatch, researchers):
    at, store = app_with_fixture(tmp_path, monkeypatch, researchers)
    next(x for x in at.selectbox if x.label == "Decision").set_value("rejected")
    next(x for x in at.text_area if x.label == "Review / correction note").set_value("Test rejection")
    next(x for x in at.button if x.label == "Save review").click().run()
    assert not at.exception
    decisions = store.reviews()
    assert len(decisions) == 1
    assert next(iter(decisions.values()))["status"] == "rejected"


def test_relationship_inspector_obeys_map_view_and_type_filters(tmp_path, monkeypatch, researchers):
    at, store = app_with_fixture(tmp_path, monkeypatch, researchers)
    graph = build_graph(store.load())
    association = next(e['id'] for *_, e in graph.edges(data=True) if e['type'] == 'RELATED_TO')
    at.toggle(key='edge_labels').set_value(True).run()
    at.selectbox(key='edge_inspector').set_value(association).run()
    assert not at.exception
    assert any('Calculation:' in x.value and '√' in x.value for x in at.markdown)
    at.radio(key='map_view').set_value('Researcher network').run()
    assert not at.exception
    assert at.selectbox(key='edge_inspector').value != association
    next(x for x in at.multiselect if x.label == 'Relationship types').set_value(['AUTHORED']).run()
    assert not at.exception
    assert any('No relationships pass' in x.value for x in at.caption)


def test_integrated_map_can_hide_papers_and_keep_inspectable_paths(tmp_path, monkeypatch, researchers):
    rendered = []
    def record_map(graph, path=None, **kwargs):
        rendered.append((graph, path))
        return graph_html(graph, path, **kwargs)
    monkeypatch.setattr('kgmap.visualisation.graph_html', record_map)
    at, store = app_with_fixture(tmp_path, monkeypatch, researchers)
    original = store.load()
    at.radio(key='map_view').set_value('Integrated map').run()
    assert at.toggle(key='show_papers').value
    assert any(d['kind'] == 'publication' for _, d in rendered[-1][0].nodes(data=True))
    at.toggle(key='show_papers').set_value(False).run()
    assert not at.exception
    graph, _ = rendered[-1]
    assert all(d['kind'] != 'publication' for _, d in graph.nodes(data=True))
    derived = next(d['id'] for *_, d in graph.edges(data=True) if d['type'] == 'PAPERS_MENTION')
    at.selectbox(key='edge_inspector').set_value(derived).run()
    assert not at.exception
    assert any('Supporting papers: 1' in x.value for x in at.markdown)
    next(x for x in at.multiselect if x.label == 'Highlight a path between two researchers').set_value(['test-a', 'test-b']).run()
    graph, path = rendered[-1]
    assert len(path) == 3 and all(graph.nodes[n]['kind'] != 'publication' for n in path)
    at.toggle(key='edge_labels').set_value(True).run()
    next(x for x in at.multiselect if x.label == 'Relationship types').set_value(['PAPERS_MENTION']).run()
    assert not at.exception
    assert all(d['type'] == 'PAPERS_MENTION' for *_, d in rendered[-1][0].edges(data=True))
    at.toggle(key='show_papers').set_value(True).run()
    assert not at.exception
    assert any(d['kind'] == 'publication' for _, d in rendered[-1][0].nodes(data=True))
    assert not any(d['type'] == 'PAPERS_MENTION' for *_, d in rendered[-1][0].edges(data=True))
    assert store.load() == original


def test_submit_and_review_joint_work_suggestion(tmp_path, monkeypatch, researchers):
    at, store = app_with_fixture(tmp_path, monkeypatch, researchers)
    original = store.load()
    at.text_input(key='suggestion_title').set_value('A joint paper to check')
    at.multiselect(key='suggestion_people').set_value(['test-a', 'test-b'])
    at.text_input(key='suggestion_source').set_value('10.1234/joint')
    at.text_area(key='suggestion_note').set_value('The source lists both authors.')
    at.text_input(key='suggestion_submitter').set_value('Test contributor')
    next(x for x in at.button if x.label == 'Submit suggestion').click().run()
    assert not at.exception
    record = store.suggestions()[0]
    assert record['title'] == 'A joint paper to check' and record['status'] == 'pending'
    assert at.text_input(key='suggestion_title').value == ''
    assert any('Suggestion saved' in x.value for x in at.success)
    at.selectbox(key='suggestion_review_status_' + record['id']).set_value('resolved')
    at.text_area(key='suggestion_review_note_' + record['id']).set_value('Checked: the paper is already present.')
    next(x for x in at.button if x.label == 'Save suggestion review').click().run()
    assert not at.exception
    assert store.suggestions()[0]['status'] == 'resolved'
    assert len(store.suggestions()[0]['history']) == 2
    assert store.load() == original
    at.selectbox(key='suggestion_status_filter').set_value('pending').run()
    assert not at.exception
    assert any('No suggestions match' in x.value for x in at.info)


def test_invalid_joint_suggestion_keeps_draft_for_correction(tmp_path, monkeypatch, researchers):
    at, store = app_with_fixture(tmp_path, monkeypatch, researchers)
    at.text_input(key='suggestion_title').set_value('A draft with one author')
    at.multiselect(key='suggestion_people').set_value(['test-a'])
    at.text_input(key='suggestion_source').set_value('10.1234/joint')
    at.text_area(key='suggestion_note').set_value('I need to add the second author.')
    next(x for x in at.button if x.label == 'Submit suggestion').click().run()
    assert not at.exception
    assert not store.suggestions()
    assert at.text_input(key='suggestion_title').value == 'A draft with one author'
    assert any('at least two researchers' in x.value for x in at.error)
