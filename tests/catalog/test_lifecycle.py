"""Status transitions (I15) and the per-field PATCH rule (decision 8.3)."""

from __future__ import annotations

import itertools

import pytest

from apps.catalog.lifecycle import (
    REASON_REQUIRED,
    TRANSITIONS,
    hard_delete_allowed,
    patch_problems,
    transition_action,
    transition_allowed,
)
from apps.catalog.permissions import RULES
from apps.catalog.vocab import STATUSES

ALLOWED = {
    ('draft', 'pending'), ('pending', 'published'), ('pending', 'rejected'),
    ('rejected', 'draft'), ('published', 'withdrawn'), ('withdrawn', 'published'),
}


@pytest.mark.parametrize('current, target', list(itertools.product(STATUSES, STATUSES)))
def test_i15_transition_matrix(current, target):
    assert transition_allowed(current, target) == ((current, target) in ALLOWED)


def test_every_transition_names_a_permission_action():
    assert set(TRANSITIONS) == ALLOWED
    assert all(action in RULES for action in TRANSITIONS.values())
    assert transition_action('draft', 'published') is None      # no shortcut
    assert REASON_REQUIRED == {('pending', 'rejected'), ('published', 'withdrawn')}


@pytest.mark.parametrize('status, allowed', [
    ('draft', True), ('pending', True), ('rejected', True),
    ('published', False), ('withdrawn', False),
])
def test_hard_delete_only_unpublished(status, allowed):
    assert hard_delete_allowed(status) is allowed


# snapshots (section 3.2.2) ---------------------------------------------------
def test_published_snapshot_frozen_fields_point_at_supersede():
    got = patch_problems('snapshot', {'geometry': [], 'quantity': [], 'notes': []},
                         status='published', is_moderator=True)
    assert got == {'frozen': ['geometry', 'quantity']}


def test_capture_notes_stay_editable_after_publish():
    got = patch_problems('snapshot', {'capture': ['notes']},
                         status='published', is_moderator=True)
    assert got == {}
    got = patch_problems('snapshot', {'capture': ['markers']},
                         status='published', is_moderator=True)
    assert got == {'frozen': ['capture.markers']}


def test_derived_snapshot_fields_are_never_accepted():
    got = patch_problems('snapshot', {'descriptors': [], 'frame': [], 'status': []},
                         status='draft', is_author=True)
    assert got == {'derived': ['descriptors', 'frame', 'status']}


def test_published_snapshot_metadata_moderator_only():
    fields = {'name': [], 'effective_from': [], 'shape_class': []}
    assert patch_problems('snapshot', fields, status='published', is_moderator=True) == {}
    assert patch_problems('snapshot', fields, status='published', is_author=True) == \
        {'forbidden': ['name', 'effective_from', 'shape_class']}


def test_draft_snapshot_editable_by_author():
    fields = {'geometry': [], 'name': [], 'effective_from': [], 'fragment': []}
    assert patch_problems('snapshot', fields, status='draft', is_author=True) == {}
    assert patch_problems('snapshot', fields, status='draft') == \
        {'forbidden': ['geometry', 'name', 'effective_from', 'fragment']}


# evidence (section 3.3.4) ----------------------------------------------------
def test_published_evidence_frozen_and_mutable():
    got = patch_problems('evidence',
                         {'summary': [], 'position': ['point', 'description'],
                          'notes': []},
                         status='published', is_moderator=True)
    assert got == {'frozen': ['summary', 'position.point']}


def test_published_evidence_notes_moderator_only():
    assert patch_problems('evidence', {'notes': []}, status='published',
                          is_author=True) == {'forbidden': ['notes']}


def test_evidence_server_fields_and_own_routes():
    got = patch_problems('evidence', {'source_tier': [], 'verification': [],
                                      'attachments': []},
                         status='draft', is_author=True)
    assert got == {'derived': ['source_tier', 'verification', 'attachments']}


# identity (section 3.1, 3.1.5) -----------------------------------------------
def test_identity_metadata_moderator_or_creator_while_unpublished():
    fields = {'origin': [], 'material': []}
    assert patch_problems('identity', fields, is_moderator=True) == {}
    assert patch_problems('identity', fields, is_author=True) == \
        {'forbidden': ['origin', 'material']}
    assert patch_problems('identity', fields, is_author=True,
                          identity_published=False) == {}


def test_identity_server_fields_and_own_routes():
    got = patch_problems('identity', {'properties': [], 'exit': [], 'dataset': [],
                                      'catalog_number': []}, is_moderator=True)
    assert got == {'derived': ['properties', 'catalog_number'],
                   'forbidden': ['exit', 'dataset']}


def test_unknown_kind():
    with pytest.raises(ValueError):
        patch_problems('design', {})
