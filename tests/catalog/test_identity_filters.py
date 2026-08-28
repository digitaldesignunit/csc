"""Tests for identity list/match helpers."""

from apps.catalog.api.identity_filters import build_children_identity_match


def test_children_match_finds_parent_without_consumed_filter():
    match = build_children_identity_match('parent-id')
    assert match == {'parent_identities': 'parent-id'}
    assert 'consumed_at' not in match
    assert 'is_public' not in match


def test_children_match_restricts_to_public_for_anonymous():
    match = build_children_identity_match('parent-id', public_only=True)
    assert match == {
        'parent_identities': 'parent-id',
        'is_public': True,
    }
