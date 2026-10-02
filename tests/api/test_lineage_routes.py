"""
Provenance, lineage and materials on the real routes (spec section 2.10,
3.1.1 -- 3.1.3, 3.8, I16 -- I18, I25, I30; decisions 8.8, 8.19, 8.31 --
8.36; plan P4).

The migrated test catalog: the ZirKuS beam (``dbu_zirkus``) is cut into
pieces A and B, which are merged into G --- three generations with a merge.
"""

from __future__ import annotations

import pytest

from apps.catalog.invariants import Corpus, check_all
from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import iid, seed_05_catalog

BEAM = iid('beam')
STONE = iid('stone')
FELD = iid('feld')
P4_INVARIANTS = {'I16', 'I17', 'I18', 'I25'}


@pytest.fixture
def world(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    contributor, contributor_id = member_headers(
        {'dbu_zirkus': ['contributor']})
    moderator, moderator_id = member_headers(
        {'dbu_zirkus': ['moderator', 'contributor']})
    outsider, _ = member_headers({'schoenes_neues_feld': ['moderator']})
    beam_v1 = db['component_snapshots'].find_one({'identity_id': BEAM,
                                                  'version': 1})
    geometry = {'meshes': beam_v1['geometry']['meshes'], 'point_clouds': [],
                'proxies': []}
    return {'api': api, 'db': db, 'contributor': contributor,
            'contributor_id': contributor_id, 'moderator': moderator,
            'moderator_id': moderator_id, 'outsider': outsider,
            'admin': auth_headers('admin'), 'geometry': geometry}


def _identity(db, identity_id):
    return db['component_identities'].find_one({'_id': identity_id})


def _violations(db):
    corpus = Corpus(identities=list(db['component_identities'].find({})),
                    snapshots=list(db['component_snapshots'].find({})),
                    evidence=list(db['component_evidence'].find({})),
                    datasets=list(db['datasets'].find({})),
                    materials=list(db['materials'].find({})),
                    users=list(db['users'].find({})))
    return [v for v in check_all(corpus)
            if v.severity == 'error' and v.invariant in P4_INVARIANTS]


def _cut(world, parents, headers=None, **fields):
    body = {'dataset': 'dbu_zirkus', 'parent_identities': parents,
            'snapshot': {'geometry': world['geometry']}, **fields}
    return world['api'].post('/identities', json=body,
                             headers=headers or world['contributor'])


def _publish_v0(world, created, author=None):
    """The author submits (7.0), a moderator publishes."""
    api, sid = world['api'], created['snapshot']['_id']
    submitted = api.post(f'/snapshots/{sid}/submit',
                         headers=author or world['contributor'])
    assert submitted.status_code == 200, submitted.text
    published = api.post(f'/snapshots/{sid}/publish?promote=1',
                         headers=world['moderator'])
    assert published.status_code == 200, published.text
    return published.json()


# CUTS (8.8, 8.34) ------------------------------------------------------------
def test_a_cut_ends_its_parent_only_when_published(world):
    api, db = world['api'], world['db']
    created = _cut(world, [BEAM],
                   original_function='IfcBuildingElementPart')
    assert created.status_code == 201, created.text
    child = created.json()
    assert 'original_function' not in child['identity']['inherited_fields']
    assert 'origin' in child['identity']['inherited_fields']
    assert child['identity']['inherited_from'] == BEAM
    assert child['identity']['origin']['kind'] == _identity(db, BEAM)['origin']['kind']
    assert child['snapshot']['status'] == 'draft'
    # a draft child leaves the parent in circulation
    assert _identity(db, BEAM)['exit'] is None

    v0 = _publish_v0(world, created.json())
    beam = _identity(db, BEAM)
    assert beam['exit']['kind'] == 'split'
    assert beam['exit']['at'] == v0['effective_from']
    assert beam['exit']['recorded_by_user_id'] is None
    assert db['change_log'].find_one({'record_id': BEAM,
                                      'cause': 'derived_exit'})
    assert _violations(db) == []

    # the cut was recorded by mistake: withdrawing the child undoes it
    child_id = child['identity']['_id']
    withdrawn = api.post(f'/identities/{child_id}/withdraw',
                         json={'reason': 'not cut after all'},
                         headers=world['moderator'])
    assert withdrawn.status_code == 200, withdrawn.text
    assert _identity(db, BEAM)['exit'] is None
    assert api.post(f'/identities/{child_id}/reinstate',
                    headers=world['moderator']).status_code == 200
    assert _identity(db, BEAM)['exit']['kind'] == 'split'
    # the server-set split is not undone by hand
    assert api.delete(f'/identities/{BEAM}/exit',
                      headers=world['moderator']).status_code == 409


def test_a_cut_needs_a_parent_in_circulation(world):
    api = world['api']
    installed = _cut(world, [STONE], headers=world['admin'])
    assert installed.status_code == 409
    assert 're-enters first' in installed.json()['detail']
    # an unpublished parent: a fresh child cannot be cut again yet
    child = _cut(world, [BEAM]).json()
    grandchild = _cut(world, [child['identity']['_id']])
    assert grandchild.status_code == 409
    assert 'publish it first' in grandchild.json()['detail']
    # no access to a parent's dataset beyond reading it
    assert _cut(world, [BEAM], headers=world['outsider']).status_code == 403
    assert api.post('/identities', json={
        'dataset': 'dbu_zirkus', 'snapshot': {'geometry': world['geometry']}},
        headers=world['contributor']).status_code == 422


# THREE GENERATIONS WITH A MERGE (8.31 -- 8.33) -------------------------------
def test_three_generations_with_a_merge(world):
    api, db, mod = world['api'], world['db'], world['moderator']
    a = _cut(world, [BEAM]).json()
    b = _cut(world, [BEAM]).json()
    _publish_v0(world, a)
    _publish_v0(world, b)
    a_id, b_id = a['identity']['_id'], b['identity']['_id']
    g = _cut(world, [a_id, b_id])
    assert g.status_code == 201, g.text
    g = g.json()
    g_id = g['identity']['_id']
    assert set(g['identity']['inherited_fields']) >= {
        'origin', 'manufactured_at', 'material', 'original_function'}
    _publish_v0(world, g)
    assert _identity(db, a_id)['exit']['kind'] == 'merged'
    assert _identity(db, b_id)['exit']['kind'] == 'merged'

    # the beam's manufacture date is corrected: three generations follow
    fixed = api.patch(f'/identities/{BEAM}',
                      json={'manufactured_at': '1972-01-01T00:00:00Z',
                            'manufactured_precision': 'year'}, headers=mod)
    assert fixed.status_code == 200, fixed.text
    for piece in (a_id, b_id, g_id):
        assert _identity(db, piece)['manufactured_at'] == \
            '1972-01-01T00:00:00Z'
        entry = db['change_log'].find_one(
            {'record_id': piece, 'cause': 'inherited_from_parent'})
        assert entry is not None
    assert _violations(db) == []

    # A makes the date its own: the merged grandchild lets go (8.33)
    own = api.patch(f'/identities/{a_id}',
                    json={'manufactured_at': '1975-01-01T00:00:00Z'},
                    headers=mod)
    assert own.status_code == 200, own.text
    assert 'manufactured_at' not in own.json()['inherited_fields']
    assert 'manufactured_at' not in _identity(db, g_id)['inherited_fields']
    assert _identity(db, g_id)['manufactured_at'] == '1972-01-01T00:00:00Z'
    # taking it back is refused while the parents disagree
    back = api.patch(f'/identities/{g_id}', json={
        'inherited_fields': [*_identity(db, g_id)['inherited_fields'],
                             'manufactured_at']}, headers=mod)
    assert back.status_code == 409
    # A takes it back from the beam: then G can too
    a_units = _identity(db, a_id)['inherited_fields']
    assert api.patch(f'/identities/{a_id}', json={
        'inherited_fields': [*a_units, 'manufactured_at']},
        headers=mod).status_code == 200
    assert api.patch(f'/identities/{g_id}', json={
        'inherited_fields': [*_identity(db, g_id)['inherited_fields'],
                             'manufactured_at']},
        headers=mod).status_code == 200
    assert _violations(db) == []

    # withdrawing G returns A and B to circulation
    assert api.post(f'/identities/{g_id}/withdraw', json={'reason': 'x'},
                    headers=mod).status_code == 200
    assert _identity(db, a_id)['exit'] is None
    assert _violations(db) == []


# MATERIAL CLASS (I25, 8.32) --------------------------------------------------
def test_material_class_derives_assigns_and_travels(world):
    api, db, mod = world['api'], world['db'], world['moderator']
    child = _cut(world, [BEAM]).json()
    child_id = child['identity']['_id']
    assigned = api.patch(f'/identities/{BEAM}',
                         json={'material_class': '17 01 07'}, headers=mod)
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()['material_class_source'] == 'assigned'
    # the class travels with the material to the child (8.32)
    assert _identity(db, child_id)['material_class'] == '17 01 07'
    assert _identity(db, child_id)['material_class_source'] == 'assigned'
    reset = api.patch(f'/identities/{BEAM}', json={'material_class': None},
                      headers=mod)
    assert reset.json()['material_class'] == '17 01 01'
    assert reset.json()['material_class_source'] == 'derived'
    assert api.patch(f'/identities/{BEAM}', json={'material': 'nope'},
                     headers=mod).status_code == 422
    assert api.patch(f'/identities/{BEAM}', json={'properties': {}},
                     headers=mod).status_code == 422
    assert api.patch(f'/identities/{BEAM}', json={'trade_name': 'x'},
                     headers=world['contributor']).status_code == 403
    assert _violations(db) == []


# CIRCULATION (3.1.3, 8.19) ---------------------------------------------------
def test_exit_undo_and_reentry(world):
    api, db, mod = world['api'], world['db'], world['moderator']
    out = api.post(f'/identities/{BEAM}/exit', json={
        'kind': 'installed', 'at': '2026-07-01T00:00:00Z',
        'construction_work': {'name': 'Pavilion 2026'}}, headers=mod)
    assert out.status_code == 200, out.text
    assert out.json()['exit']['recorded_by_user_id'] == world['moderator_id']
    assert api.post(f'/identities/{BEAM}/snapshots',
                    json={'geometry': world['geometry']},
                    headers=mod).status_code == 409
    assert api.post(f'/identities/{BEAM}/exit', json={
        'kind': 'merged', 'at': '2026-07-01T00:00:00Z'},
        headers=mod).status_code == 409
    back = api.post(f'/identities/{BEAM}/reenter', json={'origin': {
        'kind': 'deinstallation', 'at': '2026-09-01T00:00:00Z',
        'at_precision': 'day', 'position_in_work': 'roof, axis 3',
        'connection_types': ['bolted'],
        'detachability': {'class': 'improved'}}}, headers=mod)
    assert back.status_code == 200, back.text
    beam = back.json()
    assert beam['exit'] is None
    assert beam['past_cycles'][-1]['exit']['kind'] == 'installed'
    assert beam['origin']['detachability']['class'] == 'improved'
    # the next state starts at the re-entry (8.19)
    state = api.post(f'/identities/{BEAM}/snapshots',
                     json={'geometry': world['geometry']}, headers=mod)
    assert state.status_code == 201, state.text
    assert state.json()['effective_from'] == '2026-09-01T00:00:00Z'
    # a mistaken exit is undone; terminal exits cannot re-enter
    assert api.post(f'/identities/{FELD}/exit', json={
        'kind': 'recycled', 'at': '2026-07-01T00:00:00Z'},
        headers=world['admin']).status_code == 200
    assert api.post(f'/identities/{FELD}/reenter', json={
        'origin': {'kind': 'unknown'}},
        headers=world['admin']).status_code == 409
    assert api.delete(f'/identities/{FELD}/exit',
                      headers=world['admin']).status_code == 200
    assert _identity(db, FELD)['exit'] is None
    # I16: works-related origin fields only for deinstallation / demolition
    assert api.patch(f'/identities/{FELD}', json={'origin': {
        'kind': 'offcut', 'position_in_work': 'x'}},
        headers=world['admin']).status_code == 422
    assert _violations(db) == []


# CHANGE LOG (8.36) -----------------------------------------------------------
def test_change_log_and_as_of(world):
    api, db, mod = world['api'], world['db'], world['moderator']
    before = _identity(db, BEAM)
    assert api.patch(f'/identities/{BEAM}', json={'manufacturer': 'Acme'},
                     headers=mod).status_code == 200
    changes = api.get(f'/identities/{BEAM}/changes', headers=mod)
    assert changes.status_code == 200
    latest = changes.json()[0]
    assert latest['cause'] == 'patch'
    assert latest['changes'] == [{'path': 'manufacturer', 'old': None,
                                  'new': 'Acme'}]
    assert api.get(f'/identities/{BEAM}/changes',
                   headers=world['outsider']).status_code in (401, 403)
    then = api.get(f'/identities/{BEAM}',
                   params={'as_of': latest['at'][:-1] + 'Z',
                           'expand': 'none'}, headers=mod)
    assert then.status_code == 200
    earlier = api.get(f'/identities/{BEAM}', params={
        'as_of': '2026-01-01T00:00:01Z'}, headers=mod)
    assert earlier.status_code == 200
    assert 'manufacturer' not in earlier.json() or \
        earlier.json()['manufacturer'] == before.get('manufacturer')


# MATERIALS (8.35) ------------------------------------------------------------
def test_materials_admin_delete_merge_retire(world):
    api, db, admin = world['api'], world['db'], world['admin']
    new = {'_id': 'glulam', 'label': 'Glulam', 'group': 'bio-based',
           'default_class': '17 02 01'}
    assert api.post('/materials', json=new,
                    headers=world['moderator']).status_code == 403
    assert api.post('/materials', json=new, headers=admin).status_code == 201
    assert api.post('/materials', json=new, headers=admin).status_code == 409
    # in use: no delete
    assert api.delete('/materials/concrete',
                      headers=admin).status_code == 409
    # unused: delete
    assert api.delete('/materials/glulam', headers=admin).status_code == 200
    # merge concrete into a new material: every piece moves, logged
    assert api.post('/materials', json={**new, '_id': 'concrete_new',
                                        'label': 'Concrete (new)',
                                        'group': 'mineral',
                                        'default_class': '17 01 07'},
                    headers=admin).status_code == 201
    using = db['component_identities'].count_documents({'material': 'concrete'})
    merged = api.post('/materials/concrete/merge',
                      json={'into': 'concrete_new'}, headers=admin)
    assert merged.status_code == 200, merged.text
    assert merged.json()['identities_moved'] == using
    assert db['component_identities'].count_documents(
        {'material': 'concrete'}) == 0
    assert db['change_log'].count_documents(
        {'cause': 'material_merge'}) == using
    listed = [m['_id'] for m in api.get('/materials').json()]
    assert 'concrete' not in listed and 'concrete_new' in listed
    assert 'concrete' in [m['_id'] for m in api.get(
        '/materials', params={'include_merged': True,
                              'include_retired': True}).json()]
    # retire: hidden from the list, kept by its pieces
    assert api.patch('/materials/steel', json={'retired': True},
                     headers=admin).status_code == 200
    assert 'steel' not in [m['_id'] for m in api.get('/materials').json()]
    assert _violations(db) == []
