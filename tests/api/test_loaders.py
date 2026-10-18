"""One way to load a record (decision 8.158), over the real routes.

Per kind (identity, snapshot, evidence, dataset, invitation, material) and per
class of action (a read, a write) the same rows: a malformed id answers 404, a
missing record 404 with the one wording "<Kind> not found", a purged id 410,
an anonymous caller on a record that is not public 401, a signed-in caller
without a role 403, a withdrawn record outside its dataset a tombstone, and a
member is let through. A row expects an exact status, or ``OK`` (= anything
but 401 / 403 / 404 / 410: what the route does with the call is tested
elsewhere). The failures of a kind are collected, so that the run against code
that has not been changed yet lists every inconsistency at once.
"""

from __future__ import annotations

import pytest

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from evidence_samples import claim_body
from services import email_service
from support import DEFAULT_PASSWORD, iid, seed_05_catalog, sid

OK = 'ok'
DENY = (401, 403, 404, 410)
MISSING = '11111111-2222-4333-8444-555555555555'
PURGED = '99999999-2222-4333-8444-555555555555'
MALFORMED = 'not-a-uuid'
DRAFT = 'b8f2d6a4-0c1e-4b6f-9a2d-3e5f7a9c1b2d'
TOMB_EV = 'c1c1c1c1-2222-4333-8444-555555555555'


@pytest.fixture
def world(api, db, auth_headers, member_headers, monkeypatch):
    monkeypatch.setattr(email_service, 'send_mails',
                        lambda config, batch: [None for _ in batch])
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    headers = {'anonymous': {}, 'user': auth_headers('user'),
               'admin': auth_headers('admin')}
    ids = {}
    for name, roles in (('contributor', {'dbu_zirkus': ['contributor']}),
                        ('moderator', {'dbu_zirkus': ['moderator']})):
        headers[name], ids[name] = member_headers(roles)
    beam_v1 = db['component_snapshots'].find_one({'_id': sid('beam', 1)})
    db['component_snapshots'].insert_one({
        **beam_v1, '_id': DRAFT, 'version': 2, 'status': 'draft',
        'added_by_user_id': ids['contributor'], 'supersedes': None,
        'superseded_by': None})
    published = api.post(f'/identities/{iid("beam")}/evidence', json=claim_body(),
                         headers=headers['contributor']).json()['_id']
    api.post(f'/evidence/{published}/submit', headers=headers['contributor'])
    api.post(f'/evidence/{published}/publish', headers=headers['moderator'])
    # a withdrawn piece of a dataset every signed-in caller sees: a tombstone for them
    db['component_identities'].update_one({'_id': iid('panel')}, {'$set': {'withdrawn': {
        'at': '2026-01-01T00:00:00Z', 'by_user_id': 'x', 'reason': 'test'}}})
    record = db['component_evidence'].find_one({'_id': published})
    db['component_evidence'].insert_one({**record, '_id': TOMB_EV, 'identity_id': iid('panel')})
    db['purged_records'].insert_one({'_id': PURGED, 'purged_at': '2026-01-02T00:00:00Z',
                                     'kind': 'identity'})
    created = api.post('/invitations', headers=headers['moderator'], json={
        'emails': ['someone@partner.example'], 'dataset': 'dbu_zirkus',
        'roles': ['contributor']})
    return {'api': api, 'db': db, 'headers': headers, 'ids': ids,
            'evidence': published, 'invitation': created.json()[0]['invitation']['_id']}


def check(world, rows):
    """Run the rows; a row is (label, viewer, (method, path[, json]), expected[, detail])."""
    failures = []
    for label, viewer, call, expected, *detail in rows:
        method, path, *body = call
        response = world['api'].request(method, path, headers=world['headers'][viewer],
                                        json=body[0] if body else None)
        got = response.status_code
        ok = got not in DENY if expected == OK else got == expected
        if ok and detail:
            ok = response.json().get('detail') == detail[0]
        if not ok:
            failures.append(f'{label} [{viewer}]: got {got} {response.text[:90]!r}, want {expected}'
                            + (f' {detail[0]!r}' if detail else ''))
    assert not failures, '\n' + '\n'.join(failures)


def standard_rows(kind, read_or_write, make, existing, member_ok, purged=True):
    """The rows every kind shares; ``make(id)`` is the call, ``existing`` the id of a record
    that is not public."""
    name = kind.capitalize()
    rows = [
        (f'{kind} {read_or_write}: a malformed id', 'admin' if read_or_write == 'write' else 'anonymous',
         make(MALFORMED), 404, f'{name} not found'),
        (f'{kind} {read_or_write}: a missing record', 'admin' if read_or_write == 'write' else 'anonymous',
         make(MISSING), 404, f'{name} not found'),
    ]
    if purged:
        rows.append((f'{kind} {read_or_write}: a purged id', 'admin', make(PURGED), 410))
    rows += [
        (f'{kind} {read_or_write}: anonymous', 'anonymous', make(existing), 401),
        (f'{kind} {read_or_write}: signed in, no role', 'user', make(existing), 403),
    ]
    for viewer in member_ok:
        rows.append((f'{kind} {read_or_write}: a member', viewer, make(existing), OK))
    return rows


# IDENTITY --------------------------------------------------------------------
def test_identity_read(world):
    check(world, standard_rows(
        'identity', 'read', lambda i: ('GET', f'/identities/{i}'), iid('beam'),
        ('contributor', 'moderator', 'admin')))


def test_identity_write(world):
    check(world, standard_rows(
        'identity', 'write', lambda i: ('PATCH', f'/identities/{i}', {}), iid('beam'),
        ('moderator', 'admin')))


def test_identity_withdrawn_outside_its_dataset_is_a_tombstone(world):
    response = world['api'].get(f'/identities/{iid("panel")}', headers=world['headers']['user'])
    assert response.status_code == 200
    assert response.json()['kind'] == 'identity' and response.json()['status'] == 'withdrawn'


# SNAPSHOT --------------------------------------------------------------------
def test_snapshot_read(world):
    check(world, standard_rows(
        'snapshot', 'read', lambda i: ('GET', f'/snapshots/{i}'), DRAFT,
        ('contributor', 'moderator', 'admin')))


def test_snapshot_write(world):
    check(world, standard_rows(
        'snapshot', 'write', lambda i: ('POST', f'/snapshots/{i}/submit'), DRAFT,
        ('contributor',)))


def test_snapshot_withdrawn_outside_its_dataset_is_a_tombstone(world):
    response = world['api'].get(f'/snapshots/{sid("panel")}', headers=world['headers']['user'])
    assert response.status_code == 200
    assert response.json()['kind'] == 'snapshot' and response.json()['status'] == 'withdrawn'
    # its files are for members only
    assert world['api'].get(f'/snapshots/{sid("panel")}/photos',
                            headers=world['headers']['user']).status_code == 403


def test_snapshot_file_routes_load_like_the_rest(world):
    check(world, [
        ('file read: a malformed id', 'anonymous', ('GET', f'/snapshots/{MALFORMED}/photos'), 404,
         'Snapshot not found'),
        ('file read: a missing snapshot', 'anonymous', ('GET', f'/snapshots/{MISSING}/photos'), 404,
         'Snapshot not found'),
        ('file write: a malformed id', 'admin', ('DELETE', f'/snapshots/{MALFORMED}/meshes/0/reduced'), 404,
         'Snapshot not found'),
        ('file write: a missing snapshot', 'admin', ('DELETE', f'/snapshots/{MISSING}/meshes/0/reduced'),
         404, 'Snapshot not found'),
        ('file write: a purged snapshot', 'admin', ('DELETE', f'/snapshots/{PURGED}/meshes/0/reduced'), 410),
        ('file write: anonymous', 'anonymous', ('DELETE', f'/snapshots/{DRAFT}/meshes/0/reduced'), 401),
        ('file write: no role', 'user', ('DELETE', f'/snapshots/{DRAFT}/meshes/0/reduced'), 403),
    ])


# EVIDENCE --------------------------------------------------------------------
def test_evidence_read(world):
    check(world, standard_rows(
        'evidence', 'read', lambda i: ('GET', f'/evidence/{i}'), world['evidence'],
        ('contributor', 'moderator', 'admin')))


def test_evidence_write(world):
    check(world, standard_rows(
        'evidence', 'write', lambda i: ('POST', f'/evidence/{i}/submit'), world['evidence'],
        ('contributor', 'admin')))


def test_evidence_withdrawn_outside_its_dataset_is_a_tombstone(world):
    response = world['api'].get(f'/evidence/{TOMB_EV}', headers=world['headers']['user'])
    assert response.status_code == 200
    assert response.json()['kind'] == 'evidence' and response.json()['status'] == 'withdrawn'


# DATASET ---------------------------------------------------------------------
def test_dataset_read(world):
    check(world, [
        ('dataset read: a malformed slug', 'anonymous', ('GET', '/datasets/Not%20A%20Slug!'), 404,
         'Dataset not found'),
        ('dataset read: a missing dataset', 'anonymous', ('GET', '/datasets/nope'), 404,
         'Dataset not found'),
        ('dataset read: anonymous', 'anonymous', ('GET', '/datasets/dbu_zirkus'), 401),
        ('dataset read: no role', 'user', ('GET', '/datasets/dbu_zirkus'), 403),
        ('dataset read: a member', 'contributor', ('GET', '/datasets/dbu_zirkus'), OK),
    ])


def test_dataset_write(world):
    check(world, [
        ('dataset write: a missing dataset', 'admin', ('PATCH', '/datasets/nope', {}), 404,
         'Dataset not found'),
        ('dataset write: anonymous', 'anonymous', ('PATCH', '/datasets/dbu_zirkus', {}), 401),
        ('dataset write: no role', 'user', ('PATCH', '/datasets/dbu_zirkus', {}), 403),
        ('dataset write: a contributor', 'contributor', ('PATCH', '/datasets/dbu_zirkus', {}), 403),
        ('dataset write: the moderator', 'moderator', ('PATCH', '/datasets/dbu_zirkus', {}), OK),
        ('members: a missing dataset', 'admin', ('POST', '/datasets/nope/members',
                                                 {'email': 'a@partner.example', 'roles': ['contributor']}),
         404, 'Dataset not found'),
    ])


def test_a_moderator_who_removes_their_own_roles_gets_the_stored_state(world, member_headers):
    """The write stands; the answer is not a 403 from a read check of the new
    state (the dataset is members-only)."""
    second, _ = member_headers({'dbu_zirkus': ['moderator']})
    response = world['api'].put(f'/datasets/dbu_zirkus/members/{world["ids"]["moderator"]}',
                                json={'roles': []}, headers=world['headers']['moderator'])
    assert response.status_code == 200, response.text
    assert response.json()['roles'] == [] and 'members' not in response.json()
    stored = world['db']['datasets'].find_one({'_id': 'dbu_zirkus'})
    assert world['ids']['moderator'] not in {m['user_id'] for m in stored['members']}
    # the same person is now an outsider of the members-only dataset
    assert world['api'].get('/datasets/dbu_zirkus',
                            headers=world['headers']['moderator']).status_code == 403
    assert world['api'].get('/datasets/dbu_zirkus', headers=second).status_code == 200


# INVITATION ------------------------------------------------------------------
def test_invitation_write(world):
    existing = world['invitation']
    check(world, [
        ('invitation: a malformed id', 'admin', ('DELETE', f'/invitations/{MALFORMED}'), 404,
         'Invitation not found'),
        ('invitation: a missing one', 'admin', ('DELETE', f'/invitations/{MISSING}'), 404,
         'Invitation not found'),
        ('resend: a missing one', 'admin', ('POST', f'/invitations/{MISSING}/resend'), 404,
         'Invitation not found'),
        ('invitation: anonymous', 'anonymous', ('DELETE', f'/invitations/{existing}'), 401),
        ('invitation: no role', 'user', ('DELETE', f'/invitations/{existing}'), 403),
        ('invitation: a contributor', 'contributor', ('DELETE', f'/invitations/{existing}'), 403),
        ('invitation: the moderator', 'moderator', ('DELETE', f'/invitations/{existing}'), OK),
    ])


def test_redeeming_an_unknown_code_is_no_oracle(world):
    """An unknown code and a known one for another address answer alike (400,
    8.144): the only deliberate exception to the 404 of a missing record."""
    api = world['api']
    body = {'username': 'newbie', 'full_name': 'New Person', 'password': DEFAULT_PASSWORD}
    unknown = api.post('/auth/register', json={
        **body, 'email': 'newbie@partner.example', 'code': 'a-code-nobody-issued'})
    assert unknown.status_code == 400, unknown.text


# MATERIAL --------------------------------------------------------------------
def test_material_write(world):
    check(world, [
        ('material: a missing one', 'admin', ('PATCH', '/materials/nope', {}), 404, 'Material not found'),
        ('material: anonymous', 'anonymous', ('PATCH', '/materials/concrete', {}), 401),
        ('material: no role', 'user', ('PATCH', '/materials/concrete', {}), 403),
        ('material: admin', 'admin', ('PATCH', '/materials/concrete', {}), OK),
    ])


# NO CURRENT STATE ------------------------------------------------------------
def test_a_component_without_a_current_state(world):
    identities = world['db']['component_identities']
    url = f'/identities/{iid("beam")}?expand=current_snapshot'
    headers = world['headers']['moderator']
    # none named: an empty passport (8.17)
    identities.update_one({'_id': iid('beam')}, {'$set': {'current_snapshot_id': None}})
    response = world['api'].get(url, headers=headers)
    assert response.status_code == 200 and response.json()['snapshots'] == []
    # one that is gone: 409, not 500
    identities.update_one({'_id': iid('beam')}, {'$set': {'current_snapshot_id': MISSING}})
    for path in (url, f'/identities/{iid("beam")}/compose'):
        response = world['api'].get(path, headers=headers)
        assert response.status_code == 409, (path, response.status_code, response.text[:100])
        assert 'no current state' in response.json()['detail'], path
