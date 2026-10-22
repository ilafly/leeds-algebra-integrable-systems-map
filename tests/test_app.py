from streamlit.testing.v1 import AppTest

from kgmap.pipeline import analyse
from kgmap.store import Store
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
