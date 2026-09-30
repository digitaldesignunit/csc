"""Visibility and permission predicates (data model spec section 3.6, 7.0)."""

from __future__ import annotations

import dataclasses

import pytest

from apps.catalog.documents import Dataset
from apps.catalog.permissions import (
    ANONYMOUS,
    RULES,
    Target,
    Viewer,
    can,
    can_see_component,
    can_see_record,
    dataset_roles,
)

T = '2026-02-03T10:15:00Z'


def _dataset(slug='zirkus', visibility='members', members=()):
    return Dataset.model_validate({
        '_id': slug, 'name': slug, 'visibility': visibility, 'created': T,
        'lastmodified': T,
        'members': [{'user_id': uid, 'roles': list(roles)} for uid, roles in members],
    })


D = _dataset(members=[
    ('contrib', ['contributor']),
    ('review', ['reviewer']),
    ('mod', ['moderator']),
    ('author', ['contributor']),
])
OTHER = _dataset('panels', members=[('mod', ['moderator']), ('mod2', ['moderator'])])

ADMIN = Viewer('root', 'admin')
AUTHOR = Viewer('author', 'user')
CONTRIB = Viewer('contrib', 'user')
REVIEW = Viewer('review', 'user')
MOD = Viewer('mod', 'user')
STRANGER = Viewer('stranger', 'user')
ALL = {'anonymous': ANONYMOUS, 'stranger': STRANGER, 'author': AUTHOR,
       'contrib': CONTRIB, 'review': REVIEW, 'mod': MOD, 'admin': ADMIN}


def _who(action, target):
    return {name for name, viewer in ALL.items() if can(viewer, action, target)}


def test_admin_is_an_implicit_member_with_every_role():
    assert dataset_roles(ADMIN, D) == {'contributor', 'reviewer', 'moderator'}
    assert dataset_roles(ANONYMOUS, D) == frozenset()
    assert dataset_roles(STRANGER, D) == frozenset()


def test_unknown_action_is_an_error():
    with pytest.raises(KeyError):
        can(ADMIN, 'fly', Target(D))


# section 7.0, row by row -----------------------------------------------------
DRAFT = Target(D, kind='snapshot', status='draft', author_id='author')
PENDING = dataclasses.replace(DRAFT, status='pending')
REJECTED = dataclasses.replace(DRAFT, status='rejected')
PUBLISHED = dataclasses.replace(DRAFT, status='published')

TABLE = [
    # create identity / snapshot / evidence: contributor(D)
    ('create_identity', Target(D), {'contrib', 'author', 'admin'}),
    ('create_snapshot', Target(D), {'contrib', 'author', 'admin'}),
    ('create_evidence', Target(D, kind='evidence'), {'contrib', 'author', 'admin'}),
    # a child also needs read access to the parent (8.8)
    ('create_identity', Target(D, readable=False), {'admin'}),
    ('supersede_snapshot', PUBLISHED, {'contrib', 'author', 'admin'}),
    ('supersede_evidence', dataclasses.replace(PUBLISHED, kind='evidence'),
     {'contrib', 'author', 'admin'}),
    # the author's drafts; PATCH on a draft also moderator (8.3)
    ('edit_draft', DRAFT, {'author', 'mod', 'admin'}),
    ('submit', DRAFT, {'author', 'admin'}),
    ('resubmit', REJECTED, {'author', 'admin'}),
    # hard delete only unpublished
    ('delete_record', DRAFT, {'author', 'mod', 'admin'}),
    ('delete_record', PENDING, {'author', 'mod', 'admin'}),
    ('delete_record', PUBLISHED, {'admin'}),
    # geometry files only while not published (6.6)
    ('upload_geometry', DRAFT, {'author', 'mod', 'admin'}),
    ('upload_geometry', PUBLISHED, {'admin'}),
    ('delete_geometry', PUBLISHED, {'admin'}),
    # photos and attachments: append after publish by contributor, remove by moderator
    ('add_photo', DRAFT, {'author', 'mod', 'admin'}),
    ('add_photo', PUBLISHED, {'contrib', 'author', 'mod', 'admin'}),
    ('delete_photo', DRAFT, {'author', 'mod', 'admin'}),
    ('delete_photo', PUBLISHED, {'mod', 'admin'}),
    ('add_attachment', dataclasses.replace(PUBLISHED, kind='evidence'),
     {'contrib', 'author', 'mod', 'admin'}),
    ('remove_attachment', dataclasses.replace(PUBLISHED, kind='evidence'),
     {'mod', 'admin'}),
    # moderation
    ('publish', PENDING, {'mod', 'admin'}),
    ('reject', PENDING, {'mod', 'admin'}),
    ('withdraw', PUBLISHED, {'mod', 'admin'}),
    ('reinstate', dataclasses.replace(PUBLISHED, status='withdrawn'), {'mod', 'admin'}),
    ('promote', PUBLISHED, {'mod', 'admin'}),
    ('edit_published_metadata', PUBLISHED, {'mod', 'admin'}),
    ('edit_valid_time', PUBLISHED, {'mod', 'admin'}),
    ('override_derived', PUBLISHED, {'mod', 'admin'}),
    ('set_verification', dataclasses.replace(PENDING, kind='evidence'),
     {'review', 'admin'}),
    # identity metadata: moderator; the creator too while unpublished (8.9)
    ('patch_identity', Target(D, author_id='author'), {'mod', 'admin'}),
    ('patch_identity', Target(D, author_id='author', identity_published=False),
     {'author', 'mod', 'admin'}),
    ('delete_identity', Target(D, author_id='author', identity_published=False),
     {'author', 'mod', 'admin'}),
    ('delete_identity', Target(D, author_id='author'), {'admin'}),
    ('exit', Target(D), {'mod', 'admin'}),
    ('reenter', Target(D), {'mod', 'admin'}),
    ('withdraw_identity', Target(D), {'mod', 'admin'}),
    ('reinstate_identity', Target(D), {'mod', 'admin'}),
    # reservations
    ('reserve', Target(D), {'stranger', 'author', 'contrib', 'review', 'mod', 'admin'}),
    ('reserve', Target(D, reserved_by='contrib'), {'admin'}),
    ('reserve', Target(D, readable=False), {'admin'}),
    ('release', Target(D, reserved_by='contrib'), {'contrib', 'mod', 'admin'}),
    # datasets
    ('manage_members', Target(D, kind='dataset'), {'mod', 'admin'}),
    ('edit_dataset', Target(D, kind='dataset'), {'mod', 'admin'}),
    # admin only
    ('create_dataset', Target(D), {'admin'}),
    ('purge', Target(D), {'admin'}),
    ('redact_actor', Target(D), {'admin'}),
    ('manage_users', Target(D), {'admin'}),
    ('manage_materials', Target(D), {'admin'}),
    ('read_logs', Target(D), {'admin'}),
]


@pytest.mark.parametrize('action, target, expected', TABLE,
                         ids=[f'{a}-{t.status or t.kind}' for a, t, _ in TABLE])
def test_permission_table(action, target, expected):
    assert _who(action, target) == expected


def test_every_rule_is_covered_by_the_table():
    assert {row[0] for row in TABLE} | {'move_identity'} == set(RULES)


def test_publishing_a_childs_first_snapshot_needs_the_parents_moderator():
    child = dataclasses.replace(PENDING, parent_datasets=(OTHER,))
    assert can(MOD, 'publish', child)                    # moderator of both
    only_child_side = dataclasses.replace(PENDING, parent_datasets=(
        _dataset('elsewhere', members=[('mod2', ['moderator'])]),))
    assert not can(MOD, 'publish', only_child_side)      # waits for the other queue
    assert can(ADMIN, 'publish', only_child_side)


def test_move_needs_moderator_of_both_datasets():
    assert can(MOD, 'move_identity', Target(D, destination=OTHER))
    assert not can(MOD, 'move_identity', Target(D, destination=_dataset('unrelated')))
    assert not can(MOD, 'move_identity', Target(D))      # no destination named
    assert not can(CONTRIB, 'move_identity', Target(D, destination=OTHER))


# visibility (section 3.6, 3.1.5) ---------------------------------------------
@pytest.mark.parametrize('visibility, is_public, expected', [
    ('members', False, {'author', 'contrib', 'review', 'mod', 'admin'}),
    ('catalog', False, {'stranger', 'author', 'contrib', 'review', 'mod', 'admin'}),
    ('members', True, set(ALL)),
    ('catalog', True, set(ALL)),
])
def test_published_component_visibility(visibility, is_public, expected):
    dataset = _dataset(visibility=visibility, members=[
        ('author', ['contributor']), ('contrib', ['contributor']),
        ('review', ['reviewer']), ('mod', ['moderator'])])
    seen = {n for n, v in ALL.items()
            if can_see_component(v, dataset, is_public=is_public, published=True)}
    assert seen == expected


def test_unpublished_component_is_seen_by_creator_and_moderator_only():
    seen = {n for n, v in ALL.items() if can_see_component(
        v, D, is_public=True, published=False, created_by_user_id='author')}
    assert seen == {'author', 'mod', 'admin'}


@pytest.mark.parametrize('kind, status, expected', [
    ('snapshot', 'draft', {'author', 'mod', 'admin'}),
    ('snapshot', 'pending', {'author', 'mod', 'admin'}),
    ('evidence', 'pending', {'author', 'review', 'mod', 'admin'}),
    ('evidence', 'rejected', {'author', 'mod', 'admin'}),
])
def test_unpublished_record_visibility(kind, status, expected):
    seen = {n for n, v in ALL.items() if can_see_record(
        v, D, kind=kind, status=status, author_id='author', component_visible=True)}
    assert seen == expected


@pytest.mark.parametrize('status', ['published', 'withdrawn'])
def test_published_records_follow_the_component(status):
    for visible in (True, False):
        assert can_see_record(STRANGER, D, kind='evidence', status=status,
                              author_id='author', component_visible=visible) is visible
