"""
The 0.6 migration steps against a small synthetic 0.5 database.

Covers every step that writes (spec section 8.1) on a throwaway mongod:
a Corian parent split into a child and a grandchild, a robot scan with rig
markers and the gripper mesh (fixture PLY on disk), a ZirKuS beam with a
reinforced v1, a dataset with varying condition grades. After the run the
database passes every invariant, a second run changes nothing, and step 11b
re-attributes the shared account.
"""

from __future__ import annotations

import hashlib

from bson import json_util

from apps.catalog.invariants import Corpus, check_all
from apps.catalog.migration06.mappings import MigrationAbort
from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import T_CUT, iid, seed_05_catalog, sid

def _fingerprint(db):
    digest = hashlib.sha256()
    for name in sorted(db.list_collection_names()):
        for doc in db[name].find({}).sort('_id', 1):
            digest.update(json_util.dumps(doc, sort_keys=True).encode())
    return digest.hexdigest()


def _corpus(db):
    return Corpus(identities=list(db['component_identities'].find({})),
                  snapshots=list(db['component_snapshots'].find({})),
                  evidence=list(db['component_evidence'].find({})),
                  datasets=list(db['datasets'].find({})),
                  materials=list(db['materials'].find({})),
                  users=list(db['users'].find({})))


def test_every_step_on_a_small_05_database(db, tmp_path):
    seed_05_catalog(db)
    meshes, capture = tmp_path / 'meshes', tmp_path / 'capture'
    effector_dir = meshes / sid('stone') / '1'
    effector_dir.mkdir(parents=True)
    (effector_dir / 'detailed.ply').write_bytes(b'ply detailed')
    (effector_dir / 'reduced.ply').write_bytes(b'ply reduced')

    def ctx(**kw):
        return Context(db=db, meshes_dir=meshes, capture_dir=capture,
                       log=lambda _m: None, **kw)

    run(ctx(), CUTOVER_STEPS)
    violations = [v for v in check_all(_corpus(db)) if v.severity == 'error']
    assert violations == []

    ids = {i['_id']: i for i in db['component_identities'].find({})}
    snaps = {s['_id']: s for s in db['component_snapshots'].find({})}
    # exits: split parents at the first child's v0, the robot piece installed
    assert ids[iid('panel')]['exit']['kind'] == 'split'
    assert ids[iid('panel')]['exit']['at'] == T_CUT
    assert ids[iid('cut')]['exit']['kind'] == 'split'
    assert ids[iid('stone')]['exit']['kind'] == 'installed'
    # lineage: the grandchild inherits everything through its parent
    assert ids[iid('cut2')]['inherited_fields'] == [
        'origin', 'manufactured_at', 'material', 'trade_name', 'manufacturer',
        'material_separability', 'original_function']
    assert ids[iid('cut2')]['manufactured_precision'] == 'unknown'
    assert ids[iid('cut2')]['origin']['kind'] == 'offcut'
    # effective_from: Corian at the offcut date, children at the cut
    assert snaps[sid('panel', 0)]['effective_from'] == '2022-10-26T00:00:00Z'
    assert snaps[sid('cut', 0)]['effective_from'] == T_CUT
    assert snaps[sid('beam', 0)]['effective_from'] == '2024-07-24T00:00:00Z'
    # the robot rig left the geometry
    stone = snaps[sid('stone', 0)]
    assert len(stone['geometry']['meshes']) == 1
    assert 'marker_points' not in stone['geometry']
    assert [m['role'] for m in stone['capture']['markers']] == ['rig'] * 4 + ['component']
    assert stone['capture']['fixtures'][0]['file'] == f'capture/{sid("stone")}/fixtures/0.ply'
    assert stone['mesh_ply_resolutions'] == {'0': ['reduced', 'detailed']}
    assert (capture / sid('stone') / 'fixtures' / '0.ply').read_bytes() == b'ply detailed'
    assert not effector_dir.exists()
    # evidence: one layout, two inspections (the grades vary in that dataset)
    methods = sorted(e['method'] for e in db['component_evidence'].find({}))
    assert methods == ['reinforcement_layout', 'visual_inspection', 'visual_inspection']
    assert all('condition' not in s for s in snaps.values())
    # the records went through the real method models (plan P6): defaults
    # filled in as the routes would store them
    layout = db['component_evidence'].find_one(
        {'method': 'reinforcement_layout'})
    assert layout['payload']['bars'][0]['diameter_known'] is True
    assert layout['source_tier'] == 'archival'
    assert layout['summary']['range'] == [8, 8]
    # the fold step (spec 4.4): the properties start from the migrated
    # evidence; a piece with none keeps an empty block
    rebar = ids[iid('beam')]['properties']['rebar_diameter']
    assert (rebar['range'], rebar['source'], rebar['n']) == (
        [8, 8], 'archival', 1)
    assert rebar['evidence_ids'] == [layout['_id']]
    assert ids[iid('panel')]['properties'] == {}
    feld_props = [snaps[sid('feld', v)]['properties'] for v in (0, 1)]
    assert [list(p) for p in feld_props] == [['condition_grade']] * 2
    assert [p['condition_grade']['range'] for p in feld_props] == [[1, 1],
                                                                   [2, 2]]
    # proxies, statuses, datasets, materials
    assert snaps[sid('panel', 0)]['geometry']['proxies'][0]['fit'] == {'method': 'authored'}
    assert {s['status'] for s in snaps.values()} == {'published'}
    assert db['datasets'].count_documents({}) == 5
    assert db['materials'].count_documents({}) == 32
    assert ids[iid('feld')]['material'] == 'timber'

    before = _fingerprint(db)
    run(ctx(), CUTOVER_STEPS)
    assert _fingerprint(db) == before, 'a second run must change nothing'

    # after cutover: mapped records move to a personal account (targets by
    # username), from every source account the mapping lists; the rest stay,
    # and ddu stays enabled (decisions 8.22, 8.24)
    db['component_snapshots'].update_one({'_id': sid('feld', 1)}, {'$set': {
        'added_by_user_id': 'u-admin', 'added_by_username': 'admin'}})
    report = run(ctx(shared_mapping={
        'from': ['ddu', 'admin'], 'moderators': ['alice', 'u-admin'],
        'members': {'ddu_build_with_debris': {'ddu': ['contributor']}},
        'descriptions': {'dbu_zirkus': 'Scans by a partner lab'},
        'datasets': {
        d: 'alice' for d in db['component_identities'].distinct('dataset')
        if d != 'ddu_build_with_debris'}},
        operator_user_id='u-admin'), ['11b'])['11b']
    assert report['snapshots'] == 7
    assert report['left unmapped']['snapshots'] == 1
    snap = db['component_snapshots'].find_one({'_id': sid('panel')})
    assert snap['added_by_user_id'] == 'u-alice'
    assert snap['attribution_corrected']['from_user_id'] == 'u-ddu'
    feld = db['component_snapshots'].find_one({'_id': sid('feld', 1)})
    assert feld['added_by_username'] == 'alice'
    assert feld['attribution_corrected']['from_user_id'] == 'u-admin'
    assert db['component_identities'].count_documents(
        {'created_by_user_id': 'u-ddu'}) == 1          # the stone
    assert db['users'].find_one({'_id': 'u-ddu'})['disabled'] is False
    members = db['datasets'].find_one({'_id': 'dbu_zirkus'})['members']
    assert [(m['user_id'], m['roles']) for m in members] == [
        ('u-alice', ['contributor', 'moderator']), ('u-admin', ['moderator'])]
    stones = db['datasets'].find_one({'_id': 'ddu_build_with_debris'})['members']
    assert [(m['user_id'], m['roles']) for m in stones] == [
        ('u-alice', ['moderator']), ('u-admin', ['moderator']),
        ('u-ddu', ['contributor'])]
    violations = [v for v in check_all(_corpus(db)) if v.severity == 'error']
    assert violations == []
    again = run(ctx(shared_mapping={'moderators': ['alice', 'u-admin'],
                                    'datasets': {}}), ['11b'])['11b']
    assert again['datasets'] == 0
    zirkus = db['datasets'].find_one({'_id': 'dbu_zirkus'})
    assert zirkus['description'] == 'Scans by a partner lab'


def test_dataset_rename_before_the_datasets_collection(db):
    """Step 11a (decision 8.24): sas_cita_scans becomes beyond_debris; a
    datasets document made under the old slug moves; a rerun is a no-op."""
    db['component_identities'].insert_many([
        {'_id': 'a', 'dataset': 'sas_cita_scans'},
        {'_id': 'b', 'dataset': 'dbu_zirkus'}])
    db['datasets'].insert_one({'_id': 'sas_cita_scans', 'name': 'SAS CITA scans',
                               'visibility': 'catalog', 'members': []})
    ctx = Context(db=db, files=False, log=lambda _m: None)
    assert run(ctx, ['11a'])['11a'] == {'sas_cita_scans -> beyond_debris': 1}
    assert db['component_identities'].find_one({'_id': 'a'})['dataset'] == 'beyond_debris'
    moved = db['datasets'].find_one({'_id': 'beyond_debris'})
    assert moved['name'] == 'Beyond Debris' and moved['visibility'] == 'catalog'
    assert db['datasets'].find_one({'_id': 'sas_cita_scans'}) is None
    assert run(ctx, ['11a'])['11a'] == {'sas_cita_scans -> beyond_debris': 0}


def test_11b_rejects_unknown_dataset_roles(db):
    seed_05_catalog(db)
    ctx = Context(db=db, files=False, log=lambda _m: None)
    run(ctx, CUTOVER_STEPS)
    ctx.shared_mapping = {'datasets': {}, 'members': {
        'dbu_zirkus': {'alice': ['owner']}}}
    try:
        run(ctx, ['11b'])
    except MigrationAbort as exc:
        assert 'owner' in str(exc)
    else:
        raise AssertionError('an unknown role must abort')


def test_usernames_become_lowercase_and_clashes_abort(db):
    """Step 15 (decision 8.28)."""
    seed_05_catalog(db)
    db['users'].update_one({'_id': 'u-alice'}, {'$set': {'username': 'Alice'}})
    db['component_snapshots'].update_one(
        {'_id': sid('beam', 1)},
        {'$set': {'added_by_user_id': 'u-alice', 'added_by_username': 'Alice'}})
    ctx = Context(db=db, files=False, log=lambda _m: None)
    report = run(ctx, ['15'])['15']
    assert report == {'users': 1, 'added_by_username': 1,
                      'recorded_by_username': 0}
    assert db['users'].find_one({'_id': 'u-alice'})['username'] == 'alice'
    assert run(ctx, ['15'])['15']['users'] == 0
    db['users'].insert_one({'_id': 'u-alice2', 'username': 'ALICE'})
    try:
        run(ctx, ['15'])
    except MigrationAbort as exc:
        assert 'alice' in str(exc)
    else:
        raise AssertionError('a clash must abort')
