"""
The section 7.0 permission table against the real routes (plan P3).

One migrated catalog; the target dataset D is ``dbu_zirkus`` (members-only
visibility) with the ZirKuS beam. Every row is run for the seven kinds of
caller: anonymous, a user without roles, contributor(D), reviewer(D),
moderator(D), a moderator of another dataset, and admin. A row expects an
exact status, or ``OK`` (= the permission check let the call through; what
the route does with it is tested elsewhere). Rows grow with each P3 part.
"""

from __future__ import annotations

import pytest

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import iid, seed_05_catalog, sid

VIEWERS = ('anonymous', 'user', 'contributor', 'reviewer', 'moderator',
           'other_moderator', 'admin')
OK = 'ok'                      # anything but 401 / 403
DENY = (401, 403)

PLY = (b'ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\n'
       b'property float y\nproperty float z\nelement face 1\n'
       b'property list uchar int vertex_indices\nend_header\n'
       b'0 0 0\n1 0 0\n0 1 0\n3 0 1 2\n')

DRAFT = 'b8f2d6a4-0c1e-4b6f-9a2d-3e5f7a9c1b2d'


@pytest.fixture
def world(api, db, auth_headers, member_headers):
    """The migrated catalog, the seven callers, and a draft v2 of the beam
    authored by the contributor."""
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    headers = {'anonymous': {}, 'user': auth_headers('user'),
               'admin': auth_headers('admin')}
    ids = {}
    for name, roles in (('contributor', {'dbu_zirkus': ['contributor']}),
                        ('reviewer', {'dbu_zirkus': ['reviewer']}),
                        ('moderator', {'dbu_zirkus': ['moderator']}),
                        ('other_moderator',
                         {'schoenes_neues_feld': ['moderator']})):
        headers[name], ids[name] = member_headers(roles)
    beam_v1 = db['component_snapshots'].find_one({'_id': sid('beam', 1)})
    draft = {**beam_v1, '_id': DRAFT, 'version': 2, 'status': 'draft',
             'added_by_user_id': ids['contributor'], 'supersedes': None,
             'superseded_by': None}
    db['component_snapshots'].insert_one(draft)
    return {'headers': headers, 'ids': ids, 'db': db, 'api': api}


def _check(world, name, call, expected, before=None):
    failures = []
    for viewer in VIEWERS:
        if before:
            before(world)
        response = call(world['api'], world['headers'][viewer])
        want = expected[viewer]
        got = response.status_code
        ok = got not in DENY if want == OK else got == want
        if not ok:
            failures.append(f'{name} / {viewer}: got {got}, want {want} '
                            f'({response.text[:120]})')
    return failures


def _reset_reservation(value=''):
    def reset(world):
        world['db']['component_identities'].update_one(
            {'_id': iid('beam')}, {'$set': {'reserved': value}})
    return reset


def _expect(anonymous, user, contributor, reviewer, moderator,
            other_moderator, admin):
    return dict(zip(VIEWERS, (anonymous, user, contributor, reviewer,
                              moderator, other_moderator, admin)))


ROWS = [
    # --- reads (3.6, 7.0) ------------------------------------------------
    ('read a published component of a members-only dataset',
     lambda api, h: api.get(f'/identities/{iid("beam")}/compose', headers=h),
     _expect(401, 403, 200, 200, 200, 403, 200), None),
    ('read a published component of a catalog dataset',
     lambda api, h: api.get(f'/identities/{iid("panel")}/compose', headers=h),
     _expect(401, 200, 200, 200, 200, 200, 200), None),
    ('read a draft snapshot: author and moderator(D) only',
     lambda api, h: api.get(f'/snapshots/{DRAFT}', headers=h),
     _expect(401, 403, 200, 403, 200, 403, 200), None),
    ('read a published snapshot file of a members-only dataset',
     lambda api, h: api.get(f'/snapshots/{sid("beam", 1)}/meshes/0/preview',
                            headers=h),
     _expect(401, 403, 200, 200, 200, 403, 200), None),
    # --- writes: files (6.6, 7.0) ----------------------------------------
    ('upload geometry to a published snapshot: frozen (409) for all who '
     'can see it',
     lambda api, h: api.put(f'/snapshots/{sid("beam", 1)}/meshes/0/reduced',
                            files={'mesh_file': ('m.ply', PLY)}, headers=h),
     _expect(401, 403, 409, 409, 409, 403, 409), None),
    ('upload geometry to a draft: its author, moderator(D)',
     lambda api, h: api.put(f'/snapshots/{DRAFT}/meshes/0/reduced',
                            files={'mesh_file': ('m.ply', PLY)}, headers=h),
     _expect(401, 403, OK, 403, OK, 403, OK), None),
    ('add a photo to a published snapshot: contributor(D), moderator(D)',
     lambda api, h: api.put(f'/snapshots/{sid("beam", 1)}/photos/0',
                            files={'photo': ('p.jpg', b'not an image')},
                            headers=h),
     _expect(401, 403, OK, 403, OK, 403, OK), None),
    ('delete a photo of a published snapshot: moderator(D)',
     lambda api, h: api.delete(f'/snapshots/{sid("beam", 1)}/photos/0',
                               headers=h),
     _expect(401, 403, 403, 403, OK, 403, OK), None),
    # --- reserve / release (7.0) -----------------------------------------
    ('reserve: anyone signed in who can read the piece',
     lambda api, h: api.post(f'/identities/{iid("beam")}/reserve', headers=h),
     _expect(401, 403, 200, 200, 200, 403, 200), _reset_reservation()),
    ("release someone else's reservation: moderator(D)",
     lambda api, h: api.delete(f'/identities/{iid("beam")}/reserve',
                               headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200),
     _reset_reservation('someone-else')),
    # --- datasets (7.7) --------------------------------------------------
    ('edit dataset name / visibility: moderator(D)',
     lambda api, h: api.patch('/datasets/dbu_zirkus',
                              json={'description': 'x'}, headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200), None),
    ("set a member's roles: moderator(D)",
     lambda api, h: api.put('/datasets/dbu_zirkus/members/u-alice',
                            json={'roles': ['contributor']}, headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200), None),
    ('create a dataset: admin',
     lambda api, h: api.post('/datasets', json={
         '_id': f'new_{len(h)}', 'name': 'New'}, headers=h),
     _expect(401, 403, 403, 403, 403, 403, 201), None),
    ('the caller and their roles',
     lambda api, h: api.get('/users/me', headers=h),
     _expect(401, 200, 200, 200, 200, 200, 200), None),
]


def test_permission_table(world):
    failures = []
    for name, call, expected, before in ROWS:
        failures += _check(world, name, call, expected, before)
    assert failures == [], '\n'.join(failures)


def test_lists_follow_the_visibility_rule(world):
    api, headers = world['api'], world['headers']

    def listed(viewer):
        response = api.get('/identities', params={'circulation': 'all'},
                           headers=headers[viewer])
        assert response.status_code == 200, response.text
        return {row['_id'] for row in response.json()}

    assert iid('beam') not in listed('user')
    assert iid('panel') in listed('user')          # catalog dataset
    assert iid('beam') in listed('contributor')
    assert iid('beam') not in listed('other_moderator')
    assert iid('feld') in listed('other_moderator')
    world['db']['component_identities'].update_one(
        {'_id': iid('beam')}, {'$set': {'is_public': True}})
    assert iid('beam') in listed('user')           # public: everyone


def test_versions_hide_other_peoples_drafts(world):
    api, headers = world['api'], world['headers']

    def versions(viewer):
        response = api.get(f'/identities/{iid("beam")}/snapshots',
                           headers=headers[viewer])
        assert response.status_code == 200, response.text
        return [row['version'] for row in response.json()]

    assert versions('contributor') == [0, 1, 2]    # the author
    assert versions('moderator') == [0, 1, 2]
    assert versions('reviewer') == [0, 1]


def test_me_and_datasets(world):
    api, headers = world['api'], world['headers']
    me = api.get('/users/me', headers=headers['moderator']).json()
    assert me['moderated_datasets'] == ['dbu_zirkus']
    assert [m['roles'] for m in me['memberships']] == [['moderator']]
    admin = api.get('/users/me', headers=headers['admin']).json()
    assert len(admin['moderated_datasets']) == 5

    def slugs(viewer):
        return [d['_id'] for d in api.get('/datasets',
                                          headers=headers[viewer]).json()]

    assert slugs('anonymous') == []                # nothing public yet
    assert 'dbu_zirkus' not in slugs('user')
    assert 'dbu_zirkus' in slugs('contributor')
    assert len(slugs('admin')) == 5
    detail = api.get('/datasets/dbu_zirkus', headers=headers['moderator'])
    assert {m['user_id'] for m in detail.json()['members']} >= {
        world['ids']['moderator']}
    assert 'members' not in api.get('/datasets/dbu_zirkus',
                                    headers=headers['contributor']).json()
    removed = api.put(f'/datasets/dbu_zirkus/members/{world["ids"]["reviewer"]}',
                      json={'roles': []}, headers=headers['moderator'])
    assert world['ids']['reviewer'] not in {
        m['user_id'] for m in removed.json()['members']}
