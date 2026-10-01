"""
The read routes on a migrated 0.6 catalog (plan P2, read-only catch-up),
and the retired 0.5 write routes.

The catalog is the small 0.5 one of ``support.seed_05_catalog``, migrated
with the real steps, so the routes see exactly what a migrated database
holds.
"""

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import iid, panel_payload, seed_05_catalog, sid


def _migrated(db):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)


def test_list_filters_and_rows(api, db, member_headers):
    _migrated(db)
    user, _ = member_headers({'*': ['contributor']})

    rows = api.get('/identities', headers=user).json()
    # default: published, in circulation --- the split panel / cut and the
    # installed stone are out of circulation
    assert sorted(r['_id'] for r in rows) == sorted(iid(n) for n in ('beam', 'cut2', 'feld'))
    beam = next(r for r in rows if r['_id'] == iid('beam'))
    assert beam['original_function'] == 'IfcBeam'
    assert beam['origin']['kind'] == 'deinstallation'
    assert beam['status'] == 'published' and beam['version'] == 1
    assert beam['frame'] == {'o': [0.0, 0.0, 0.0], 'x': [1.0, 0.0, 0.0],
                             'y': [0.0, 1.0, 0.0], 'z': [0.0, 0.0, 1.0]}
    for gone in ('type', 'consumed_at', 'validated', 'condition', 'pca_frame'):
        assert gone not in beam

    exited = api.get('/identities', params={'circulation': 'exited'},
                     headers=user).json()
    assert sorted(r['_id'] for r in exited) == sorted(iid(n) for n in ('cut', 'panel', 'stone'))
    split = api.get('/identities', params={'circulation': 'all',
                                           'exit_kind': 'split'},
                    headers=user).json()
    assert sorted(r['_id'] for r in split) == sorted(iid(n) for n in ('cut', 'panel'))
    beams = api.get('/identities', params={'original_function': 'IfcBeam'},
                    headers=user).json()
    assert [r['_id'] for r in beams] == [iid('beam')]
    count = api.get('/identities/count', params={'circulation': 'all'},
                    headers=user).json()
    assert count == {'count': 6}

    db['component_snapshots'].update_one({'_id': sid('feld', 1)},
                                         {'$set': {'status': 'pending'}})
    assert iid('feld') not in str(api.get('/identities', headers=user).json())
    anyone = api.get('/identities', params={'status': 'any'}, headers=user)
    assert iid('feld') in str(anyone.json())


def test_passport_snapshots_children_provenance(api, db, member_headers):
    _migrated(db)
    user, _ = member_headers({'*': ['contributor']})

    passport = api.get(f'/identities/{iid("beam")}/compose', params={'snapshots': 'all'},
                       headers=user)
    assert passport.status_code == 200, passport.text
    body = passport.json()
    assert body['identity']['material_class'] == '17 01 01'
    assert [s['version'] for s in body['snapshots']] == [0, 1]
    assert body['snapshots'][0]['effective_from'] == '2024-07-24T00:00:00Z'

    stone = api.get(f'/identities/{iid("stone")}', params={'expand': 'current_snapshot'},
                    headers=user).json()
    capture = stone['snapshots'][0]['capture']
    assert capture['coordinate_system']['name'].startswith('DDU robot')
    assert len(stone['snapshots'][0]['geometry']['meshes']) == 1

    versions = api.get(f'/identities/{iid("feld")}/snapshots', headers=user).json()
    assert [(v['version'], v['status'], v['is_current']) for v in versions] == \
        [(0, 'published', False), (1, 'published', True)]

    children = api.get(f'/identities/{iid("panel")}/children', headers=user).json()
    assert [c['_id'] for c in children] == [iid('cut')]
    graph = api.get(f'/identities/{iid("cut2")}/provenance', headers=user).json()
    nodes = {n['id']: n for n in graph['nodes'] if n['kind'] == 'identity'}
    assert {n['exit_kind'] for n in nodes.values()} == {'split', None}

    snap = api.get(f'/snapshots/{sid("panel")}', headers=user).json()
    assert snap['geometry']['proxies'][0]['primitive'] == 'prism'
    mesh = api.get(f'/snapshots/{sid("panel")}/proxies/0/mesh', headers=user)
    assert mesh.status_code == 200 and mesh.content.startswith(b'ply')
    # the preview (decision 8.23); /primitive stays an alias until P5
    for name in ('preview', 'primitive'):
        preview = api.get(f'/snapshots/{sid("stone")}/meshes/0/{name}',
                          headers=user)
        assert preview.status_code == 200 and preview.content.startswith(b'ply')
        assert '_mesh_0_preview.ply' in preview.headers['content-disposition']


def test_evidence_and_capture_fixture(api, db, member_headers):
    _migrated(db)
    user, _ = member_headers({'*': ['contributor']})
    layouts = api.get(f'/identities/{iid("beam")}/evidence',
                      params={'method': 'reinforcement_layout'}, headers=user)
    assert layouts.status_code == 200, layouts.text
    [layout] = layouts.json()
    assert layout['position']['snapshot_id'] == sid('beam', 1)
    assert layout['payload']['bars'][0]['diameter_mm'] == 8
    inspections = api.get(f'/identities/{iid("feld")}/evidence', headers=user)
    assert {e['method'] for e in inspections.json()} == {'visual_inspection'}

    # the gripper is listed on the capture; its file lives under
    # SNAPSHOT_CAPTURE_DIR (not configured in the tests --> 404)
    fixture = api.get(f'/snapshots/{sid("stone")}/capture/fixtures/0.ply',
                      headers=user)
    assert fixture.status_code == 404
    missing = api.get(f'/snapshots/{sid("stone")}/capture/fixtures/1.ply',
                      headers=user)
    assert missing.json()['detail'] == 'Fixture not found'


def test_stats_vocab_materials(api, db, member_headers):
    _migrated(db)
    user, _ = member_headers({'*': ['contributor']})
    stats = api.get('/identities/stats', params={'circulation': 'all'},
                    headers=user).json()
    assert stats['total'] == 6
    assert {r['label'] for r in stats['byStatus']} == {'published'}
    assert 'IfcPlate' in {r['label'] for r in stats['byOriginalFunction']}

    vocab = api.get('/vocab').json()
    assert {'value': 'IfcBeam', 'label': 'Beam'} in vocab['original_function']
    materials = api.get('/materials').json()
    assert len(materials) == 32
    datasets = api.get('/identities/meta/datasets', headers=user).json()
    assert 'dbu_zirkus' in datasets


def test_05_write_routes_are_retired(api, db, auth_headers):
    admin = auth_headers('admin')
    for method, path, body in (
            ('post', '/identities', panel_payload()),
            ('post', '/identities/x/snapshots', panel_payload()),
            ('patch', '/identities/x', {'material': 'concrete'}),
            ('patch', '/identities/x/current-snapshot', {'name': 'n'}),
            ('post', '/identities/x/consume', None),
            ('post', '/identities/x/restore', None),
            ('delete', '/identities/x', None),
            ('post', '/snapshots/x/validate', None),
            ('delete', '/snapshots/x', None)):
        response = getattr(api, method)(path, json=body, headers=admin) \
            if body is not None else getattr(api, method)(path, headers=admin)
        assert response.status_code == 503, (method, path, response.text)
        assert 'plan P' in response.json()['detail']
