from streamlit.testing.v1 import AppTest

from kgmap.pipeline import analyse
from kgmap.store import Store
from kgmap.graph import build_graph
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
