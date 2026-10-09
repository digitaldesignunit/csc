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

import os

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from evidence_samples import PDF, claim_body, person, rebound_body
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
EV = {}                       # evidence ids of the current `world`


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
    _make_evidence(api, headers, ids, db)
    return {'headers': headers, 'ids': ids, 'db': db, 'api': api}


def _make_evidence(api, headers, ids, db):
    """Two records of the contributor on the beam: a published claim and a
    draft rebound record the contributor performed."""
    c, m = headers['contributor'], headers['moderator']
    pub = api.post(f'/identities/{iid("beam")}/evidence', json=claim_body(),
                   headers=c).json()['_id']
    api.post(f'/evidence/{pub}/submit', headers=c)
    api.post(f'/evidence/{pub}/publish', headers=m)
    draft = api.post(
        f'/identities/{iid("beam")}/evidence',
        json=rebound_body(observed_at='2026-07-01T10:00:00Z',
                          performed_by=[person(ids['contributor'])]),
        headers=c).json()['_id']
    EV.update(pub=pub, draft=draft, draft_doc=db['component_evidence'].find_one(
        {'_id': draft}))


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


def _set_draft(status):
    def reset(world):
        world['db']['component_snapshots'].update_one(
            {'_id': DRAFT}, {'$set': {'status': status}})
    return reset


def _republish_v1(world):
    world['db']['component_snapshots'].update_one(
        {'_id': sid('beam', 1)}, {'$set': {'status': 'published'}})
    world['db']['component_identities'].update_one(
        {'_id': iid('beam')}, {'$set': {'current_snapshot_id': sid('beam', 1)}})


def _reinstate_beam(world):
    world['db']['component_identities'].update_one(
        {'_id': iid('beam')}, {'$set': {'withdrawn': None}})


def _clear_exit(world):
    world['db']['component_identities'].update_one(
        {'_id': iid('beam')}, {'$set': {'exit': None, 'withdrawn': None}})


def _drop_test_material(world):
    world['db']['materials'].delete_one({'_id': 'test_material'})


def _ev(status, **fields):
    """Put the draft evidence record into a state."""
    def reset(world):
        db = world['db']['component_evidence']
        if db.find_one({'_id': EV['draft']}) is None:     # a row deleted it
            import copy
            db.insert_one(copy.deepcopy(EV['draft_doc']))
        db.update_one({'_id': EV['draft']}, {'$set': {
            'status': status, 'verification': {
                'state': 'unverified', 'by': None, 'at': None,
                'note': None}, **fields}})
        db.delete_many({'supersedes': {'$ne': None}})
        db.update_one({'_id': EV['pub']}, {'$set': {
            'status': 'published', 'superseded_by': None}})
    return reset


def _drop_new_evidence(world):
    world['db']['component_evidence'].delete_many(
        {'_id': {'$nin': [EV['pub'], EV['draft']]},
         'method': {'$ne': 'reinforcement_layout'}})
    _ev('draft')(world)


def _with_attachment(status='draft'):
    def reset(world):
        _ev(status)(world)
        root = os.environ['EVIDENCE_ATTACHMENTS_DIR']
        for key in ('draft', 'pub'):
            os.makedirs(os.path.join(root, EV[key]), exist_ok=True)
            with open(os.path.join(root, EV[key], '0.pdf'), 'wb') as handle:
                handle.write(PDF)
            world['db']['component_evidence'].update_one(
                {'_id': EV[key]}, {'$set': {'attachments': [{
                    'index': 0, 'name': 'r.pdf',
                    'media_type': 'application/pdf', 'size': len(PDF),
                    'sha256': 'a' * 64, 'uploaded_by_user_id': 'u',
                    'uploaded_at': '2026-07-02T00:00:00Z',
                    'removed': None}]}})
    return reset


def _no_attachments(world):
    _ev('draft')(world)
    world['db']['component_evidence'].update_many(
        {'_id': {'$in': [EV['draft'], EV['pub']]}},
        {'$set': {'attachments': []}})


MESH = {'vertices': [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
        'faces': [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]]}


_restore_draft = _ev('draft')


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
    # --- the snapshot lifecycle (7.1) ------------------------------------
    ('submit a draft: its author',
     lambda api, h: api.post(f'/snapshots/{DRAFT}/submit', headers=h),
     _expect(401, 403, 200, 403, 403, 403, 200), _set_draft('draft')),
    ('publish a pending snapshot: moderator(D)',
     lambda api, h: api.post(f'/snapshots/{DRAFT}/publish', headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200), _set_draft('pending')),
    ('withdraw a published snapshot: moderator(D)',
     lambda api, h: api.post(f'/snapshots/{sid("beam", 1)}/withdraw',
                             json={'reason': 'test'}, headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200), _republish_v1),
    ('edit a draft: its author, moderator(D)',
     lambda api, h: api.patch(f'/snapshots/{DRAFT}', json={'notes': 'n'},
                              headers=h),
     _expect(401, 403, 200, 403, 200, 403, 200), _set_draft('draft')),
    ('withdraw a component: moderator(D)',
     lambda api, h: api.post(f'/identities/{iid("beam")}/withdraw',
                             json={'reason': 'test'}, headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200), _reinstate_beam),
    # --- datasets (7.7) --------------------------------------------------
    ('edit dataset name / visibility: moderator(D)',
     lambda api, h: api.patch('/datasets/dbu_zirkus',
                              json={'description': 'x'}, headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200), None),
    ("set a member's roles: moderator(D)",
     lambda api, h: api.put('/datasets/dbu_zirkus/members/u-alice',
                            json={'roles': ['contributor']}, headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200), None),
    ('invite into D: moderator(D)',
     lambda api, h: api.post('/invitations', json={
         'emails': ['guest@partner.example'], 'dataset': 'dbu_zirkus',
         'roles': ['contributor']}, headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200), None),
    ('add a person to D by email: moderator(D)',
     lambda api, h: api.post('/datasets/dbu_zirkus/members', json={
         'email': 'alice@example.org', 'roles': ['reviewer']}, headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200), None),
    ('search users: admin',
     lambda api, h: api.get('/users/search', params={'q': 'al'}, headers=h),
     _expect(401, 403, 403, 403, 403, 403, 200), None),
    ('create a dataset: admin',
     lambda api, h: api.post('/datasets', json={
         '_id': f'new_{len(h)}', 'name': 'New'}, headers=h),
     _expect(401, 403, 403, 403, 403, 403, 201), None),
    ('the caller and their roles',
     lambda api, h: api.get('/users/me', headers=h),
     _expect(401, 200, 200, 200, 200, 200, 200), None),
    # --- provenance, lineage, materials (P4) -----------------------------
    ('edit component metadata: moderator(D)',
     lambda api, h: api.patch(f'/identities/{iid("beam")}',
                              json={'trade_name': 'x'}, headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200), None),
    ('take a component out of circulation: moderator(D)',
     lambda api, h: api.post(f'/identities/{iid("beam")}/exit', json={
         'kind': 'lost', 'at': '2026-07-01T00:00:00Z'}, headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200), _clear_exit),
    ('record a cut from a component: contributor(D) who reads the parent',
     lambda api, h: api.post('/identities', json={
         'dataset': 'dbu_zirkus', 'parent_identities': [iid('beam')],
         'snapshot': {'geometry': {'meshes': [MESH]}}}, headers=h),
     _expect(401, 403, 201, 403, 403, 403, 201), _clear_exit),
    ('read the change log: members of D',
     lambda api, h: api.get(f'/identities/{iid("beam")}/changes', headers=h),
     _expect(401, 403, 200, 200, 200, 403, 200), None),
    ('add a material: admin',
     lambda api, h: api.post('/materials', json={
         '_id': 'test_material', 'label': 'Test', 'group': 'other',
         'default_class': '17 09 04'}, headers=h),
     _expect(401, 403, 403, 403, 403, 403, 201), _drop_test_material),
    # --- evidence (P6): reads --------------------------------------------
    ('read a published evidence record of a members-only dataset',
     lambda api, h: api.get(f'/evidence/{EV["pub"]}', headers=h),
     _expect(401, 403, 200, 200, 200, 403, 200), None),
    ('read a draft evidence record: author and moderator(D) only',
     lambda api, h: api.get(f'/evidence/{EV["draft"]}', headers=h),
     _expect(401, 403, 200, 403, 200, 403, 200), _ev('draft')),
    ('read a pending evidence record: reviewer(D) too (7.0)',
     lambda api, h: api.get(f'/evidence/{EV["draft"]}', headers=h),
     _expect(401, 403, 200, 200, 200, 403, 200), _ev('pending')),
    ('read the evidence of a component',
     lambda api, h: api.get(f'/identities/{iid("beam")}/evidence',
                            headers=h),
     _expect(401, 403, 200, 200, 200, 403, 200), None),
    ('read the folded properties of a component',
     lambda api, h: api.get(f'/identities/{iid("beam")}/properties',
                            headers=h),
     _expect(401, 403, 200, 200, 200, 403, 200), None),
    ('read the timeline of a component',
     lambda api, h: api.get(f'/identities/{iid("beam")}/timeline',
                            headers=h),
     _expect(401, 403, 200, 200, 200, 403, 200), None),
    ('read the evidence methods: public',
     lambda api, h: api.get('/evidence/methods', headers=h),
     _expect(200, 200, 200, 200, 200, 200, 200), None),
    ('read the evidence moderation queue: any signed-in user, filtered',
     lambda api, h: api.get('/evidence/pending', headers=h),
     _expect(401, 200, 200, 200, 200, 200, 200), None),
    # --- evidence: writes ------------------------------------------------
    ('create evidence: contributor(D)',
     lambda api, h: api.post(f'/identities/{iid("beam")}/evidence',
                             json=claim_body(), headers=h),
     _expect(401, 403, 201, 403, 403, 403, 201), _drop_new_evidence),
    ('create evidence in bulk: contributor(D) of every target',
     lambda api, h: api.post('/evidence/bulk', json={'records': [
         {**claim_body(), 'identity_id': iid('beam')}]}, headers=h),
     _expect(401, 403, 201, 403, 403, 403, 201), _drop_new_evidence),
    ('submit a draft evidence record: its author',
     lambda api, h: api.post(f'/evidence/{EV["draft"]}/submit', headers=h),
     _expect(401, 403, 200, 403, 403, 403, 200), _ev('draft')),
    ('recall a pending evidence record: its author',
     lambda api, h: api.post(f'/evidence/{EV["draft"]}/recall', headers=h),
     _expect(401, 403, 200, 403, 403, 403, 200), _ev('pending')),
    ('publish a pending evidence record: moderator(D)',
     lambda api, h: api.post(f'/evidence/{EV["draft"]}/publish', headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200), _ev('pending')),
    ('reject a pending evidence record: moderator(D)',
     lambda api, h: api.post(f'/evidence/{EV["draft"]}/reject',
                             json={'reason': 'x'}, headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200), _ev('pending')),
    ('withdraw a published evidence record: moderator(D)',
     lambda api, h: api.post(f'/evidence/{EV["pub"]}/withdraw',
                             json={'reason': 'x'}, headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200), _ev('draft')),
    ('reinstate a withdrawn evidence record: moderator(D)',
     lambda api, h: api.post(f'/evidence/{EV["pub"]}/reinstate', headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200),
     lambda world: (_ev('draft')(world),
                    world['db']['component_evidence'].update_one(
                        {'_id': EV['pub']}, {'$set': {
                            'status': 'withdrawn'}}))),
    ('supersede a published evidence record: contributor(D)',
     lambda api, h: api.post(f'/evidence/{EV["pub"]}/supersede',
                             json=claim_body(), headers=h),
     _expect(401, 403, 201, 403, 403, 403, 201), _ev('draft')),
    ('edit a draft evidence record: its author, moderator(D)',
     lambda api, h: api.patch(f'/evidence/{EV["draft"]}',
                              json={'notes': 'n'}, headers=h),
     _expect(401, 403, 200, 403, 200, 403, 200), _ev('draft')),
    ('edit a pending evidence record: moderator(D)',
     lambda api, h: api.patch(f'/evidence/{EV["draft"]}',
                              json={'notes': 'n'}, headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200), _ev('pending')),
    ('edit the notes of a published evidence record: moderator(D)',
     lambda api, h: api.patch(f'/evidence/{EV["pub"]}', json={'notes': 'n'},
                              headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200), None),
    ('delete a draft evidence record: its author, moderator(D)',
     lambda api, h: api.delete(f'/evidence/{EV["draft"]}', headers=h),
     _expect(401, 403, 200, 403, 200, 403, 200),
     _restore_draft),
    # --- evidence: verification (8.12, I27) ------------------------------
    ('set reviewed: reviewer(D) or admin, not the recorder or a performer',
     lambda api, h: api.put(f'/evidence/{EV["draft"]}/verification',
                            json={'state': 'reviewed'}, headers=h),
     _expect(401, 403, 403, 200, 403, 403, 200), _ev('pending')),
    ('self-attest: the recorder who performed it, never the admin shortcut',
     lambda api, h: api.put(f'/evidence/{EV["draft"]}/verification',
                            json={'state': 'self_attested'}, headers=h),
     _expect(401, 403, 200, 403, 403, 403, 403), _ev('pending')),
    # --- evidence: attachments (7.3, 8.13) -------------------------------
    ('attach a file to a draft evidence record: its author, moderator(D)',
     lambda api, h: api.post(
         '/evidence/attachments', data={'record_ids': [EV['draft']]},
         files={'file': ('r.pdf', PDF, 'application/pdf')}, headers=h),
     _expect(401, 403, 201, 403, 201, 403, 201), _no_attachments),
    ('attach a file to a published evidence record: contributor(D)',
     lambda api, h: api.post(
         '/evidence/attachments', data={'record_ids': [EV['pub']]},
         files={'file': ('r.pdf', PDF, 'application/pdf')}, headers=h),
     _expect(401, 403, 201, 403, 201, 403, 201), _no_attachments),
    ('download an attachment: signed in, with access to the record',
     lambda api, h: api.get(f'/evidence/{EV["pub"]}/attachments/0',
                            headers=h),
     _expect(401, 403, 200, 200, 200, 403, 200), _with_attachment()),
    ('remove an attachment of a published record: moderator(D)',
     lambda api, h: api.delete(f'/evidence/{EV["pub"]}/attachments/0',
                               params={'reason': 'x'}, headers=h),
     _expect(401, 403, 403, 403, 200, 403, 200), _with_attachment()),
    ('remove an attachment of a draft: its author, moderator(D)',
     lambda api, h: api.delete(f'/evidence/{EV["draft"]}/attachments/0',
                               headers=h),
     _expect(401, 403, 200, 403, 200, 403, 200), _with_attachment()),
    # --- redaction (3.1.4) -----------------------------------------------
    ('redact an actor: admin',
     lambda api, h: api.post('/actors/redact', json={
         'name': 'nobody', 'dry_run': True}, headers=h),
     _expect(401, 403, 403, 403, 403, 403, 200), None),
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


def test_dataset_rows_count_members_and_published_pieces(world):
    """`member_count` for moderator(D) and admin only; `component_count` is the
    published pieces the caller may see (the catalog lists' visibility match)."""
    api, headers, db = world['api'], world['headers'], world['db']
    ids = db['component_identities']
    published = {'current_snapshot_id': {'$ne': None}, 'withdrawn': None}
    total = ids.count_documents({'dataset': 'dbu_zirkus', **published})
    members = len(db['datasets'].find_one({'_id': 'dbu_zirkus'})['members'])
    assert total > 0 and members > 0

    def row(viewer, slug='dbu_zirkus'):
        got = api.get('/datasets', headers=headers[viewer])
        assert got.status_code == 200, got.text
        return next((d for d in got.json() if d['_id'] == slug), None)

    admin = row('admin')
    assert admin['component_count'] == total and admin['member_count'] == members
    moderator = row('moderator')
    assert moderator['component_count'] == total
    assert moderator['member_count'] == members
    for viewer in ('contributor', 'reviewer'):
        got = row(viewer)
        assert got['component_count'] == total, viewer
        assert 'member_count' not in got, viewer
    # a dataset the catalog shows to everyone signed in: they see its pieces, not its members
    db['datasets'].update_one({'_id': 'dbu_zirkus'}, {'$set': {'visibility': 'catalog'}})
    outsider = row('user')
    assert outsider['component_count'] == total
    assert 'member_count' not in outsider
    assert row('anonymous') is None                 # nothing public yet
    ids.update_one({'_id': iid('beam')}, {'$set': {'is_public': True}})
    anonymous = row('anonymous')
    assert anonymous['component_count'] >= 1 and 'member_count' not in anonymous
    # a withdrawn piece does not count
    before = row('admin')['component_count']
    ids.update_one({'_id': iid('beam')}, {'$set': {'withdrawn': {
        'at': '2026-01-01T00:00:00Z', 'by_user_id': 'x', 'reason': 'test'}}})
    assert row('admin')['component_count'] == before - 1


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
