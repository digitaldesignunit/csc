"""Users create and run their own datasets (decision 8.139): who may create,
the slug, the limit, the review gate on `catalog` and on both public paths,
the last moderator, the delete of an empty dataset, the mail to the admins."""

from __future__ import annotations

import copy

import pytest

from apps.catalog.api.datasets import max_datasets_per_user, slug_from_name
from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from services import email_service
from support import iid, seed_05_catalog

BEAM = iid('beam')


@pytest.fixture
def outbox(monkeypatch):
    box = {'mails': [], 'fail': False}

    def send_mails(config, batch):
        batch = list(batch)
        if box['fail']:
            raise RuntimeError('smtp down')
        box['mails'].extend(batch)
        return [None] * len(batch)

    monkeypatch.setattr(email_service, 'send_mails', send_mails)
    return box


@pytest.fixture
def world(api, db, auth_headers, make_user, login, outbox):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)

    def account(**state):
        user = make_user(username=f'u{len(db["users"].distinct("_id"))}x')
        headers = {'Authorization': 'Bearer ' + login(
            user['username']).json()['access_token']}
        if state:
            db['users'].update_one({'_id': user['id']}, {'$set': state})
        return headers, user['id']

    return {'api': api, 'db': db, 'admin': auth_headers('admin'),
            'account': account}


def create(w, headers, name='Tiny House Lab', **extra):
    return w['api'].post('/datasets', json={'name': name, **extra},
                         headers=headers)


# CREATE ----------------------------------------------------------------------
def test_an_account_creates_a_dataset_and_becomes_its_moderator(world, outbox):
    w = world
    headers, uid = w['account']()
    got = create(w, headers)
    assert got.status_code == 201, got.text
    body = got.json()
    assert body['_id'] == 'tiny_house_lab' and body['reviewed'] is False
    assert body['visibility'] == 'members'
    assert body['roles'] == ['contributor', 'moderator']
    stored = w['db']['datasets'].find_one({'_id': 'tiny_house_lab'})
    assert stored['created_by_user_id'] == uid and stored['reviewed'] is False
    assert [(m['user_id'], m['roles']) for m in stored['members']] == [
        (uid, ['contributor', 'moderator'])]
    # the slug is derived and unique: a second one gets a suffix
    again = create(w, headers, 'Tiny house LAB!!').json()
    assert again['_id'] == 'tiny_house_lab_2'
    assert create(w, headers, 'X').status_code == 201      # the third
    assert create(w, headers, 'Y').status_code == 403      # the default limit
    # the admins are told, with the current template
    to = {m.to for m in outbox['mails']}
    assert to and all(m.subject.startswith('[CSC] ') for m in outbox['mails'])
    assert 'Dataset created' in outbox['mails'][0].text


def test_the_slug_comes_from_the_name_and_cannot_be_chosen():
    assert slug_from_name('Tiny House Lab') == 'tiny_house_lab'
    assert slug_from_name('  Zur\u00fcck zum B\u00e4ren  ') == 'zuruck_zum_baren'
    assert slug_from_name('!!!') == 'dataset'
    assert slug_from_name('A') == 'a_x'
    assert len(slug_from_name('x' * 200)) <= 55


def test_an_account_may_not_state_a_slug_nor_ask_for_catalog(world):
    w = world
    headers, _ = w['account']()
    assert create(w, headers, **{'_id': 'mine'}).status_code == 422
    refused = create(w, headers, visibility='catalog')
    assert refused.status_code == 409 and 'reviewed' in refused.json()['detail']
    # an admin states the slug, and the dataset is reviewed
    got = create(w, w['admin'], 'Admin Set', **{'_id': 'admin_set'})
    assert got.status_code == 201 and got.json()['reviewed'] is True
    assert create(w, w['admin'], 'Admin Set', **{'_id': 'admin_set'}
                  ).status_code == 409


def test_only_a_verified_and_enabled_account_creates(world):
    w = world
    unverified, _ = w['account']()
    w['db']['users'].update_many({}, {'$set': {'email_verified': False}})
    refused = create(w, unverified)
    assert refused.status_code == 403 and 'Verify' in refused.json()['detail']
    disabled, uid = w['account']()
    w['db']['users'].update_one({'_id': uid}, {'$set': {'disabled': True}})
    assert create(w, disabled).status_code in (400, 401)   # no session at all
    assert create(w, {}).status_code == 401                  # anonymous
    # an invited account is verified from the start
    invited, _ = w['account'](email_verified=True)
    assert create(w, invited, 'From Invitation').status_code == 201


def test_the_limit_counts_the_datasets_one_account_created(world, monkeypatch):
    w = world
    monkeypatch.setenv('CSC_MAX_DATASETS_PER_USER', '2')
    headers, _ = w['account']()
    other, _ = w['account']()
    assert create(w, headers, 'One').status_code == 201
    assert create(w, headers, 'Two').status_code == 201
    refused = create(w, headers, 'Three')
    assert refused.status_code == 403 and '2' in refused.json()['detail']
    assert create(w, other, 'Mine').status_code == 201       # per account
    for n in range(4):                                        # admins: none
        assert create(w, w['admin'], f'Admin {n}').status_code == 201
    monkeypatch.setenv('CSC_MAX_DATASETS_PER_USER', 'many')
    assert max_datasets_per_user() == 3
    monkeypatch.delenv('CSC_MAX_DATASETS_PER_USER')
    assert max_datasets_per_user() == 3
    monkeypatch.setenv('CSC_MAX_DATASETS_PER_USER', '0')
    assert create(w, other, 'Over').status_code == 403


def test_a_failing_mail_never_blocks_the_create(world, outbox):
    w = world
    outbox['fail'] = True
    headers, _ = w['account']()
    assert create(w, headers).status_code == 201
    assert w['db']['datasets'].find_one({'_id': 'tiny_house_lab'})


def test_a_dataset_from_before_the_field_is_reviewed(world):
    w = world
    w['db']['datasets'].update_one({'_id': 'dbu_zirkus'},
                                   {'$unset': {'reviewed': ''}})
    got = w['api'].get('/datasets/dbu_zirkus', headers=w['admin']).json()
    assert got['reviewed'] is True


# THE REVIEW GATE -------------------------------------------------------------
def _piece_in(w, slug):
    """A published piece of the dataset (a copy of the beam)."""
    beam = copy.deepcopy(w['db']['component_identities'].find_one({'_id': BEAM}))
    beam.update({'_id': f'aaaaaaaa-0000-4000-8000-{abs(hash(slug)) % 10 ** 12:012d}',
                 'dataset': slug, 'catalog_number': 9100, 'is_public': False})
    w['db']['component_identities'].insert_one(beam)
    return beam['_id']


def test_until_reviewed_nothing_becomes_catalog_or_public(world):
    w = world
    headers, _ = w['account']()
    create(w, headers)
    did = 'tiny_house_lab'
    piece = _piece_in(w, did)
    # catalog
    catalog = w['api'].patch(f'/datasets/{did}', json={'visibility': 'catalog'},
                             headers=headers)
    assert catalog.status_code == 409 and 'reviewed' in catalog.json()['detail']
    # both public paths
    one = w['api'].patch(f'/identities/{piece}', json={'is_public': True},
                         headers=headers)
    assert one.status_code == 409 and 'reviewed' in one.json()['detail']
    many = w['api'].post(f'/datasets/{did}/public', json={'is_public': True},
                         headers=headers)
    assert many.status_code == 409
    counted = w['api'].post(f'/datasets/{did}/public',
                            json={'is_public': True, 'dry_run': True},
                            headers=headers)
    assert counted.status_code == 200 and counted.json()['changed'] == 1
    # private is always allowed
    assert w['api'].post(f'/datasets/{did}/public', json={'is_public': False},
                         headers=headers).status_code == 200
    # a moderator cannot mark it reviewed; an admin can, then everything opens
    assert w['api'].patch(f'/datasets/{did}', json={'reviewed': True},
                          headers=headers).status_code == 403
    assert w['api'].patch(f'/datasets/{did}', json={'reviewed': True},
                          headers=w['admin']).json()['reviewed'] is True
    assert w['api'].patch(f'/datasets/{did}', json={'visibility': 'catalog'},
                          headers=headers).status_code == 200
    assert w['api'].patch(f'/identities/{piece}', json={'is_public': True},
                          headers=headers).status_code == 200
    assert w['api'].post(f'/datasets/{did}/public', json={'is_public': True},
                         headers=headers).status_code == 200


def test_an_admin_may_publish_in_an_unreviewed_dataset(world):
    w = world
    headers, _ = w['account']()
    create(w, headers)
    piece = _piece_in(w, 'tiny_house_lab')
    assert w['api'].patch(f'/identities/{piece}', json={'is_public': True},
                          headers=w['admin']).status_code == 200


# THE LAST MODERATOR ----------------------------------------------------------
def test_a_dataset_keeps_a_moderator(world):
    w = world
    headers, uid = w['account']()
    create(w, headers)
    did = 'tiny_house_lab'
    second, sid = w['account']()
    path = lambda user: f'/datasets/{did}/members/{user}'        # noqa: E731
    put = lambda user, roles, h: w['api'].put(                    # noqa: E731
        path(user), json={'roles': roles}, headers=h)
    refused = put(uid, ['contributor'], headers)                  # demote self
    assert refused.status_code == 409 and 'moderator' in refused.json()['detail']
    assert put(uid, [], headers).status_code == 409               # remove self
    # with a second moderator the first may step down
    assert put(sid, ['moderator'], headers).status_code == 200
    assert put(uid, ['contributor'], headers).status_code == 200
    # the last one cannot go, an admin can
    assert put(sid, ['reviewer'], second).status_code == 409
    assert put(sid, [], second).status_code == 409
    assert put(sid, [], w['admin']).status_code == 200


# DELETE ----------------------------------------------------------------------
def test_an_empty_dataset_is_deleted_with_its_open_invitations(world):
    w = world
    headers, _ = w['account']()
    create(w, headers)
    did = 'tiny_house_lab'
    w['db']['invitations'].insert_one({
        '_id': 'inv1', 'dataset': did, 'email': 'x@example.org',
        'code_sha256': 'x', 'roles': ['contributor'], 'revoked_at': None,
        'used_at': None, 'expires_at': '2999-01-01T00:00:00Z',
        'created': '2026-10-10T00:00:00Z'})
    contributor, cid = w['account']()
    w['api'].put(f'/datasets/{did}/members/{cid}', json={'roles': ['contributor']},
                 headers=headers)
    assert w['api'].delete(f'/datasets/{did}', headers=contributor
                           ).status_code == 403
    assert w['api'].delete(f'/datasets/{did}').status_code == 401
    other_mod, _other = w['account']()
    create(w, other_mod, 'Another')
    assert w['api'].delete(f'/datasets/{did}', headers=other_mod
                           ).status_code == 403
    done = w['api'].delete(f'/datasets/{did}', headers=headers)
    assert done.status_code == 200, done.text
    assert done.json() == {'deleted': did, 'revoked_invitations': 1}
    assert w['db']['datasets'].find_one({'_id': did}) is None
    assert w['db']['invitations'].find_one({'_id': 'inv1'})['revoked_at']
    assert w['api'].get(f'/datasets/{did}', headers=w['admin']
                        ).status_code == 404


def test_a_dataset_with_pieces_is_not_deleted_by_anyone(world):
    w = world
    headers, _ = w['account']()
    create(w, headers)
    did = 'tiny_house_lab'
    _piece_in(w, did)
    for who in (headers, w['admin']):
        refused = w['api'].delete(f'/datasets/{did}', headers=who)
        assert refused.status_code == 409 and 'move' in refused.json()['detail']
    assert w['db']['datasets'].find_one({'_id': did})
