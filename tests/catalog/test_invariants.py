"""The invariant checker (data model spec section 5)."""

from __future__ import annotations

import re

import examples06 as ex
from apps.catalog.invariants import INVARIANT_BY_ID, INVARIANTS, Corpus, check_all


def _corpus() -> Corpus:
    """A small, consistent 0.6 database: one published beam with a core test."""
    material = ex.material()
    material.update({'_id': 'concrete', 'label': 'Concrete', 'group': 'mineral',
                     'default_class': '17 01 01'})
    return Corpus(
        identities=[ex.identity()],
        snapshots=[ex.snapshot()],
        evidence=[ex.evidence()],
        datasets=[ex.dataset()],
        materials=[material],
        users=[{'_id': 'root', 'role': 'admin', 'disabled': False}],
    )


def _ids(violations, severity='error'):
    return {v.invariant for v in violations if v.severity == severity}


def test_every_invariant_id_is_registered_once():
    ids = [inv.id for inv in INVARIANTS]
    assert len(ids) == len(set(ids))
    expected = {f'I{n}' for n in range(1, 29)} | {'I3b'}
    assert set(ids) == expected
    for inv in INVARIANTS:
        assert inv.kind in ('document', 'corpus', 'route', 'dropped')
        assert (inv.check is not None) == (inv.kind == 'corpus')
    assert INVARIANT_BY_ID['I12'].kind == 'dropped'


def test_document_invariants_are_named_in_model_messages():
    """Each 'document' id appears in a validator message of documents.py."""
    import inspect
    from apps.catalog import documents
    source = inspect.getsource(documents)
    for inv in INVARIANTS:
        if inv.kind == 'document':
            assert re.search(rf'\({inv.id}\)', source), inv.id


def test_consistent_corpus_has_no_violations():
    assert check_all(_corpus()) == []


def test_document_errors_carry_their_id():
    corpus = _corpus()
    corpus.snapshots[0]['shape_class'] = 'composite'
    assert _ids(check_all(corpus)) == {'I4'}


def test_i3_monotonic_effective_from():
    corpus = _corpus()
    v1 = ex.snapshot()
    v1.update({'_id': 'v1', 'version': 1, 'effective_from': '2020-01-01T00:00:00Z'})
    corpus.snapshots.append(v1)
    assert _ids(check_all(corpus)) == {'I3'}


def test_i3b_one_open_snapshot_and_current_is_published():
    corpus = _corpus()
    for n in (1, 2):
        s = ex.snapshot()
        s.update({'_id': f'd{n}', 'version': n, 'status': 'draft',
                  'effective_from': '2026-09-01T00:00:00Z'})
        corpus.snapshots.append(s)
    assert _ids(check_all(corpus)) == {'I3b'}
    corpus = _corpus()
    corpus.snapshots[0]['status'] = 'pending'
    assert 'I3b' in _ids(check_all(corpus))


def test_i9_position_snapshot_of_the_same_identity():
    corpus = _corpus()
    corpus.evidence[0]['position']['snapshot_id'] = 'someone-elses'
    assert _ids(check_all(corpus)) == {'I9'}


def test_i14_supersession_same_method_and_published_target():
    corpus = _corpus()
    newer = ex.evidence()
    newer.update({'_id': 'e2', 'supersedes': ex.EVIDENCE_ID, 'status': 'pending'})
    corpus.evidence.append(newer)
    assert check_all(corpus) == []
    corpus.evidence[0]['status'] = 'draft'
    assert 'I14' in _ids(check_all(corpus))


def test_i14_one_open_correction_per_record():
    corpus = _corpus()
    for n in (2, 3):
        newer = ex.evidence()
        newer.update({'_id': f'e{n}', 'supersedes': ex.EVIDENCE_ID, 'status': 'draft'})
        corpus.evidence.append(newer)
    assert _ids(check_all(corpus)) == {'I14'}
    corpus.evidence[2]['status'] = 'rejected'
    assert check_all(corpus) == []


def test_i17_inherited_fields_equal_the_parent():
    corpus = _corpus()
    child = ex.identity()
    child.update({'_id': 'child', 'catalog_number': 43,
                  'parent_identities': [ex.IDENTITY_ID],
                  'inherited_from': ex.IDENTITY_ID,
                  'inherited_fields': ['origin', 'material'],
                  'current_snapshot_id': None, 'material': 'concrete'})
    corpus.identities.append(child)
    violations = check_all(corpus)
    assert 'I17' not in _ids(violations)
    child['origin'] = dict(child['origin'], kind='demolition')
    assert 'I17' in _ids(check_all(corpus))


def test_i18_split_exit_follows_published_children():
    corpus = _corpus()
    child = ex.identity()
    child.update({'_id': 'child', 'catalog_number': 43,
                  'parent_identities': [ex.IDENTITY_ID], 'current_snapshot_id': None})
    corpus.identities.append(child)
    snap = ex.snapshot()
    snap.update({'_id': 'child-v0', 'identity_id': 'child', 'status': 'draft',
                 'effective_from': '2026-05-01T00:00:00Z'})
    corpus.snapshots.append(snap)
    assert 'I18' not in _ids(check_all(corpus))      # a draft child ends nothing (8.8)
    snap['status'] = 'published'
    assert 'I18' in _ids(check_all(corpus))           # published child, parent not split
    corpus.identities[0]['exit'] = {'kind': 'split', 'at': '2026-05-01T00:00:00Z',
                                    'recorded_by_user_id': None}
    assert 'I18' not in _ids(check_all(corpus))
    corpus.identities[0]['exit']['at'] = '2026-06-01T00:00:00Z'
    assert 'I18' in _ids(check_all(corpus))           # at = earliest child effective_from


def test_i19_duplicate_of_live_identity():
    corpus = _corpus()
    corpus.identities[0]['withdrawn'] = {'at': ex.T1, 'by_user_id': 'root',
                                         'reason': 'dup', 'duplicate_of': 'nowhere'}
    assert 'I19' in _ids(check_all(corpus))


def test_i20_dataset_admin_and_moderator_warning():
    corpus = _corpus()
    corpus.identities[0]['dataset'] = 'nowhere'
    corpus.users = [{'_id': 'root', 'role': 'admin', 'disabled': True}]
    corpus.datasets[0]['members'] = []
    violations = check_all(corpus)
    assert _ids(violations) == {'I20'}
    assert _ids(violations, 'warning') == {'I20'}


def test_i25_material_fk_and_derived_class():
    corpus = _corpus()
    corpus.identities[0]['material_class'] = '17 01 07'
    assert _ids(check_all(corpus)) == {'I25'}
    corpus.identities[0]['material_class_source'] = 'assigned'
    assert check_all(corpus) == []
    corpus.identities[0]['material'] = 'unobtainium'
    assert _ids(check_all(corpus)) == {'I25'}


def test_i26_no_published_evidence_on_an_unpublished_identity():
    corpus = _corpus()
    corpus.snapshots[0]['status'] = 'draft'
    corpus.identities[0]['current_snapshot_id'] = None
    assert _ids(check_all(corpus)) == {'I26'}


def test_i28_no_evidence_on_withdrawn_or_after_terminal_exit():
    corpus = _corpus()
    identity = corpus.identities[0]
    identity['exit'] = {'kind': 'recycled', 'at': '2026-02-25T00:00:00Z'}
    assert _ids(check_all(corpus)) == {'I28'}          # core test observed after it
    identity['exit'] = {'kind': 'installed', 'at': '2026-02-25T00:00:00Z'}
    assert check_all(corpus) == []                     # non-terminal: after_exit
    identity['exit'] = None
    identity['withdrawn'] = {'at': '2026-02-01T00:00:00Z', 'by_user_id': ex.MODERATOR_ID,
                             'reason': 'duplicate'}
    assert _ids(check_all(corpus)) == {'I28'}          # created after the withdrawal
    identity['withdrawn']['at'] = '2026-03-01T00:00:00Z'
    assert check_all(corpus) == []


def test_i3b_no_current_only_when_no_published_snapshot_is_left():
    corpus = _corpus()
    corpus.identities[0]['current_snapshot_id'] = None
    assert _ids(check_all(corpus)) == {'I3b'}
    corpus.snapshots[0]['status'] = 'withdrawn'
    assert check_all(corpus) == []
