import pytest

from conftest import paper
from kgmap.pipeline import analyse
from kgmap.store import Store


@pytest.fixture
def suggestion_store(tmp_path, researchers):
    store = Store(tmp_path / 'map.sqlite')
    store.save(analyse(researchers, [paper('known-paper', ['test-a', 'test-b'])]))
    return store


def joint_suggestion(**overrides):
    return {'kind': 'joint_work', 'title': 'A missing joint publication',
            'researcher_ids': ['test-a', 'test-b'], 'note': 'Both researchers are listed as authors.',
            'source': '10.1234/EXAMPLE', 'submitter': 'Test contributor', **overrides}


def test_suggestions_survive_refresh_without_changing_map_evidence_or_reviews(suggestion_store):
    store = suggestion_store
    original = store.load()
    record = store.add_suggestion(joint_suggestion())
    assert record['source_url'] == 'https://doi.org/10.1234/example'
    assert record['researcher_names'] == {'test-a': 'Test Author A', 'test-b': 'Test Author B'}
    assert record['status'] == 'pending'
    assert store.load() == original
    store.review('existing-decision', 'accepted', 'Existing scientific review')
    refreshed = {**original, 'generated_at': 'a later refresh'}
    store.save(refreshed)
    reopened = Store(store.path)
    assert reopened.suggestions() == [record]
    reopened.review_suggestion(record['id'], 'accepted', 'Check this source next.', 'Test reviewer')
    assert reopened.load() == refreshed
    assert reopened.reviews()['existing-decision']['status'] == 'accepted'


@pytest.mark.parametrize('overrides, error', [
    ({'researcher_ids': ['test-a', 'test-a']}, 'at least two'),
    ({'researcher_ids': ['test-a', 'unknown-author']}, 'from this map'),
    ({'source': ''}, 'source URL or DOI'),
    ({'source': 'javascript:alert(1)'}, 'HTTP'),
    ({'source': 'https://user:password@example.org/paper'}, 'HTTP'),
    ({'note': '   '}, 'provide a note'),
])
def test_invalid_suggestions_are_not_saved(suggestion_store, overrides, error):
    with pytest.raises(ValueError, match=error):
        suggestion_store.add_suggestion(joint_suggestion(**overrides))
    assert suggestion_store.suggestions() == []


def test_existing_paper_supplies_source_and_review_preserves_submission_history(suggestion_store):
    store = suggestion_store
    record = store.add_suggestion(joint_suggestion(source='', publication_id='known-paper'))
    assert record['publication_title'] == 'Hopf algebras and braid groups'
    assert record['source_url'] == 'https://example.org/known-paper'
    with pytest.raises(ValueError, match='provide a note'):
        store.review_suggestion(record['id'], 'resolved')
    assert store.suggestions() == [record]
    store.review_suggestion(record['id'], 'in_review', 'Checking the author list.', 'Reviewer A')
    updated = store.review_suggestion(record['id'], 'resolved', 'The paper was already in the map.', 'Reviewer B')
    assert updated['note'] == record['note'] and updated['submitter'] == record['submitter']
    assert [e['status'] for e in updated['history']] == ['pending', 'in_review', 'resolved']
    assert updated['history'][1]['by'] == 'Reviewer A'
    assert store.suggestions()[0] == updated


def test_general_correction_can_be_submitted_without_a_researcher_pair(suggestion_store):
    record = suggestion_store.add_suggestion({'kind': 'correction', 'title': 'Improve a topic label',
        'note': 'This terminology should be reviewed.', 'researcher_ids': []})
    assert record['researcher_ids'] == [] and record['source_url'] == ''
