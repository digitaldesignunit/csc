"""
The geometry runner off the server (decision 8.45): a worker pulls stale
snapshots through the API, computes and uploads; a result computed from
changed geometry is refused.
"""

from __future__ import annotations

import os

import pytest
import trimesh

from apps.catalog.geometry_stages import VERSIONS
from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from apps.catalog.remote_runner import (
    HEAVY_STAGES,
    RemoteError,
    RemoteRunner,
    run_remote,
)
from support import iid, seed_05_catalog

BEAM = iid('beam')


@pytest.fixture
def worker(api, db, auth_headers, member_headers, make_user, login):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    contributor, _ = member_headers({'dbu_zirkus': ['contributor']})
    admin = make_user(username='geometry-svc', role='admin')
    token = login(admin['username']).json()['access_token']
    runner = RemoteRunner(client=api, token=token, log=lambda _m: None)
    return {'runner': runner, 'db': db, 'contributor': contributor,
            'api': api, 'token': token}


def block_geometry():
    mesh = trimesh.creation.box(extents=(300, 200, 150))
    return {'meshes': [{'vertices': mesh.vertices.tolist(),
                        'faces': mesh.faces.tolist()}],
            'point_clouds': [], 'proxies': []}


def draft(worker):
    response = worker['api'].post(
        f'/identities/{BEAM}/snapshots', json={'geometry': block_geometry()},
        headers={'Authorization': worker['contributor']['Authorization'],
                 'X-CSC-Client': 'web/0.6.0.0'})
    assert response.status_code == 201, response.text
    return response.json()['_id']


def test_only_admins_reach_the_runner_routes(worker):
    api = worker['api']
    plain = {'Authorization': worker['contributor']['Authorization']}
    for method, path in (('get', '/geometry/stale'),
                         ('get', '/geometry/work/x'),
                         ('post', '/geometry/results/x')):
        assert getattr(api, method)(path, headers=plain).status_code == 403
    assert api.get('/geometry/stale', headers={}).status_code in (401, 403)


def test_a_worker_computes_and_uploads_the_heavy_stages(worker):
    sid = draft(worker)
    runner, db = worker['runner'], worker['db']
    items, _ = runner.stale(HEAVY_STAGES, 100)
    mine = [i for i in items if i['snapshot_id'] == sid]
    assert len(mine) == 1 and set(mine[0]['stale']) == set(HEAVY_STAGES)

    visited, uploaded, refused = run_remote(
        runner, list(HEAVY_STAGES), None, snapshot=sid)
    assert (visited, uploaded, refused) == (1, 1, 0)

    stored = db['component_snapshots'].find_one({'_id': sid})
    proxy = stored['geometry']['proxies'][0]
    assert proxy['primitive'] == 'box' and proxy['role'] == 'primary'
    assert 'hks' in stored['descriptors']
    assert stored['complexity_source'] == 'derived'
    for stage in HEAVY_STAGES:
        stamp = stored['derivation'][stage]
        assert stamp['version'] == VERSIONS[stage] and not stamp['error']
    # the server's own stamps: nothing is stale afterwards
    left, _ = runner.stale(HEAVY_STAGES, 100)
    assert sid not in [i['snapshot_id'] for i in left]
    # the files are on the server's disk and served
    face = proxy['deviation_maps']['faces']['+z']
    served = worker['api'].get(
        f'/snapshots/{sid}/proxies/0/faces/%2Bz',
        headers={'Authorization': f'Bearer {worker["token"]}'})
    assert served.status_code == 200
    assert served.content[:8] == b'\x89PNG\r\n\x1a\n'
    assert face['file'].startswith(f'proxies/{sid}/0/')
    preview = worker['api'].get(
        f'/snapshots/{sid}/preview',
        headers={'Authorization': f'Bearer {worker["token"]}'})
    assert preview.status_code == 200


def test_a_result_from_changed_geometry_is_refused(worker):
    sid = draft(worker)
    runner, db = worker['runner'], worker['db']
    work = runner.work(sid, HEAVY_STAGES)
    # a moderator edits the geometry while the worker computes
    changed = block_geometry()
    changed['meshes'][0]['vertices'][0][0] += 5.0
    db['component_snapshots'].update_one(
        {'_id': sid}, {'$set': {'geometry.meshes': changed['meshes']}})
    from apps.catalog.geometry_stages import Env, run_stages
    outcome = run_stages(work['snapshot'], work['identity'], Env(),
                         ['proxies'], force=True)
    with pytest.raises(RemoteError, match='409'):
        runner.upload(work, outcome)
    stored = db['component_snapshots'].find_one({'_id': sid})
    assert not stored['geometry'].get('proxies')


def test_a_changed_context_is_refused(worker):
    sid = draft(worker)
    runner, db = worker['runner'], worker['db']
    work = runner.work(sid, HEAVY_STAGES)
    db['component_snapshots'].update_one(
        {'_id': sid}, {'$set': {'shape_class': 'planar',
                                'shape_class_source': 'assigned'}})
    from apps.catalog.geometry_stages import Env, run_stages
    outcome = run_stages(work['snapshot'], work['identity'], Env(),
                         ['proxies'], force=True)
    with pytest.raises(RemoteError, match='409'):
        runner.upload(work, outcome)


def test_an_outdated_worker_is_refused(worker):
    sid = draft(worker)
    runner, api = worker['runner'], worker['api']
    work = runner.work(sid, HEAVY_STAGES)
    import json
    body = {'stages': ['proxies'],
            'source_fingerprint': work['source_fingerprint'],
            'context': work['context'],
            'versions': {'proxies': VERSIONS['proxies'] + 1},
            'set': {'fitted_proxies': []}}
    response = api.post(f'/geometry/results/{sid}',
                        data={'result': json.dumps(body)},
                        headers={'Authorization': f'Bearer {worker["token"]}'})
    assert response.status_code == 409
    assert 'server_versions' in response.json()['detail']


def test_the_server_refuses_fields_outside_the_stages(worker):
    sid = draft(worker)
    runner, api = worker['runner'], worker['api']
    work = runner.work(sid, HEAVY_STAGES)
    import json
    body = {'stages': ['descriptors'],
            'source_fingerprint': work['source_fingerprint'],
            'context': work['context'],
            'versions': {'descriptors': VERSIONS['descriptors']},
            'set': {'frame': None, 'descriptors': {'hks': [0.0]}}}
    response = api.post(f'/geometry/results/{sid}',
                        data={'result': json.dumps(body)},
                        headers={'Authorization': f'Bearer {worker["token"]}'})
    assert response.status_code == 422
    body['set'] = {'descriptors': {'owner': 'x'}}
    response = api.post(f'/geometry/results/{sid}',
                        data={'result': json.dumps(body)},
                        headers={'Authorization': f'Bearer {worker["token"]}'})
    assert response.status_code == 422


# WHAT A WORKER MAY WRITE (decision 8.54) -------------------------------------
def json_copy(value):
    import json
    return json.loads(json.dumps(value))


def _local(worker, sid, stages=('proxies',)):
    from apps.catalog.geometry_stages import Env, run_stages
    work = worker['runner'].work(sid, HEAVY_STAGES)
    outcome = run_stages(work['snapshot'], work['identity'], Env(),
                         list(stages), force=True)
    return work, outcome


def _post(worker, sid, body, files=None):
    import json
    return worker['api'].post(
        f'/geometry/results/{sid}', data={'result': json.dumps(body)},
        files=files or None,
        headers={'Authorization': f'Bearer {worker["token"]}'})


def _good(worker, sid):
    work, outcome = _local(worker, sid)
    body = worker['runner'].result_body(work, outcome)
    files = [('files', (n, d, 'application/octet-stream'))
             for n, d in outcome.write_files.items()]
    return work, outcome, body, files


def test_a_good_result_is_accepted(worker):
    sid = draft(worker)
    _, _, body, files = _good(worker, sid)
    assert _post(worker, sid, body, files).status_code == 200


def test_traversal_and_foreign_file_names_are_refused(worker):
    sid = draft(worker)
    _, outcome, body, files = _good(worker, sid)
    other = '11111111-1111-1111-1111-111111111111'
    evil = json_copy(body)
    face = evil['set']['fitted_proxies'][0]['deviation_maps']['faces']['+z']
    face['file'] = f'proxies/{sid}/../{other}/0/+z.png'
    assert _post(worker, sid, evil, files).status_code == 422
    foreign = json_copy(body)
    foreign['set']['fitted_proxies'][0]['deviation_maps']['faces']['+z'][
        'file'] = f'proxies/{other}/0/+z.png'
    assert _post(worker, sid, foreign, files).status_code == 422
    bad_files = files + [('files', (f'proxies/{sid}/../x.png', b'x',
                                    'application/octet-stream'))]
    assert _post(worker, sid, body, bad_files).status_code == 422
    stored = worker['db']['component_snapshots'].find_one({'_id': sid})
    assert not [p for p in stored['geometry'].get('proxies', [])
                if p['fit']['method'] != 'authored']


def test_an_oversized_file_is_413(worker):
    sid = draft(worker)
    _, _, body, files = _good(worker, sid)
    files[0] = ('files', (files[0][1][0], b'0' * (9 * 1024 * 1024),
                          'application/octet-stream'))
    assert _post(worker, sid, body, files).status_code == 413


def test_an_unexpected_file_and_missing_maps_are_422(worker):
    sid = draft(worker)
    _, _, body, files = _good(worker, sid)
    extra = files + [('files', ('notes.txt', b'x', 'text/plain'))]
    assert _post(worker, sid, body, extra).status_code == 422
    assert _post(worker, sid, body, files[:-1]).status_code == 422


def test_an_authored_proxy_is_never_uploaded(worker):
    sid = draft(worker)
    _, _, body, files = _good(worker, sid)
    bad = json_copy(body)
    bad['set']['fitted_proxies'][0]['fit'] = {'method': 'authored'}
    bad['set']['fitted_proxies'][0]['deviation_maps'] = None
    assert _post(worker, sid, bad).status_code == 422


def test_a_snapshot_changed_during_the_store_is_a_409(worker, monkeypatch):
    sid = draft(worker)
    _, _, body, files = _good(worker, sid)
    import apps.catalog.api.geometry_remote as remote
    real = remote.build_update

    def moved(snapshot, outcome):
        worker['db']['component_snapshots'].update_one(
            {'_id': sid}, {'$set': {'etag': 'moved'}})
        return real(snapshot, outcome)
    monkeypatch.setattr(remote, 'build_update', moved)
    response = _post(worker, sid, body, files)
    assert response.status_code == 409
    assert response.json()['detail']['reason'] == 'concurrent'
    folder = os.path.join(os.environ['SNAPSHOT_PROXIES_DIR'], sid)
    assert not os.path.isdir(folder) or not [
        f for _r, _d, fs in os.walk(folder) for f in fs]


def test_an_assigned_value_is_never_overwritten(worker):
    sid = draft(worker)
    runner, db = worker['runner'], worker['db']
    db['component_snapshots'].update_one(
        {'_id': sid}, {'$set': {'complexity': 3,
                                'complexity_source': 'assigned'}})
    work = runner.work(sid, HEAVY_STAGES)
    body = {'stages': ['complexity'],
            'source_fingerprint': work['source_fingerprint'],
            'context': work['context'],
            'versions': {'complexity': VERSIONS['complexity']},
            'set': {'complexity': 0}}
    assert _post(worker, sid, body).status_code == 409
    assert db['component_snapshots'].find_one({'_id': sid})[
        'complexity'] == 3


def test_sources_are_the_servers_and_bodies_are_checked(worker):
    sid = draft(worker)
    runner = worker['runner']
    work = runner.work(sid, HEAVY_STAGES)
    base = {'stages': ['complexity'],
            'source_fingerprint': work['source_fingerprint'],
            'context': work['context'],
            'versions': {'complexity': VERSIONS['complexity']}}
    sneaky = {**base, 'set': {'complexity': 1,
                              'complexity_source': 'assigned'}}
    assert _post(worker, sid, sneaky).status_code == 422
    assert _post(worker, sid, {**base, 'set': {}}).status_code == 422
    for bad in ({'fitted_proxies': 'x'}, {'descriptors': [1]},
                {'complexity': 'high'}, {'frame': {'o': 1}},
                {'bbx': [1, 2]}):
        stage = 'proxies' if 'fitted_proxies' in bad else (
            'descriptors' if 'descriptors' in bad else (
                'frame' if 'frame' in bad or 'bbx' in bad else 'complexity'))
        body = {**base, 'stages': [stage],
                'versions': {stage: VERSIONS[stage]}, 'set': bad}
        assert _post(worker, sid, body).status_code == 422, bad
    assert _post(worker, sid, {'nonsense': 1}).status_code == 422


def test_a_failed_stage_is_stamped_with_its_error_and_nothing_else(worker):
    sid = draft(worker)
    runner = worker['runner']
    work = runner.work(sid, HEAVY_STAGES)
    body = {'stages': ['previews'],
            'source_fingerprint': work['source_fingerprint'],
            'context': work['context'],
            'versions': {'previews': VERSIONS['previews']},
            'errors': {'previews': 'OSError: disk full'}, 'set': {}}
    assert _post(worker, sid, body).status_code == 200
    stamp = worker['db']['component_snapshots'].find_one({'_id': sid})[
        'derivation']['previews']
    assert stamp['error'] == 'OSError: disk full'
    items, _ = runner.stale(['previews'], 100)
    assert sid not in [i['snapshot_id'] for i in items]
    items, _ = runner.stale(['previews'], 100, retry_errors=True)
    assert sid in [i['snapshot_id'] for i in items]


def test_explicit_nulls_and_an_empty_proxy_list_are_not_results(worker):
    sid = draft(worker)
    runner = worker['runner']
    work = runner.work(sid, HEAVY_STAGES)
    base = {'source_fingerprint': work['source_fingerprint'],
            'context': work['context']}
    for stage, field in (('frame', 'frame'), ('frame', 'bbx'),
                         ('proxies', 'fitted_proxies'),
                         ('shape_class', 'shape_class'),
                         ('complexity', 'complexity')):
        body = {**base, 'stages': [stage],
                'versions': {stage: VERSIONS[stage]}, 'set': {field: None}}
        assert _post(worker, sid, body).status_code == 422, (stage, field)
    # no proxy is a result only when the primary proxy is authored
    body = {**base, 'stages': ['proxies'],
            'versions': {'proxies': VERSIONS['proxies']},
            'set': {'fitted_proxies': []}}
    assert _post(worker, sid, body).status_code == 422
    stored = worker['db']['component_snapshots'].find_one({'_id': sid})
    assert 'proxies' not in (stored.get('derivation') or {})


def test_a_partly_failed_descriptors_stage_keeps_its_partial_result(worker):
    sid = draft(worker)
    runner, db = worker['runner'], worker['db']
    work = runner.work(sid, HEAVY_STAGES)
    body = {'stages': ['descriptors'],
            'source_fingerprint': work['source_fingerprint'],
            'context': work['context'],
            'versions': {'descriptors': VERSIONS['descriptors']},
            'errors': {'descriptors': 'radial_signature: ValueError'},
            'set': {'descriptors': {'hks': [0.5] * 32}}}
    assert _post(worker, sid, body).status_code == 200
    stored = db['component_snapshots'].find_one({'_id': sid})
    assert stored['descriptors']['hks'] == [0.5] * 32
    stamp = stored['derivation']['descriptors']
    assert stamp['error'] == 'radial_signature: ValueError'
    # the error stamp is current: nothing is listed again
    left, _ = runner.stale(['descriptors'], 100)
    assert sid not in [i['snapshot_id'] for i in left]


def test_a_worker_failure_is_sent_as_an_error_and_converges(worker, monkeypatch):
    import apps.catalog.geometry_stages as stages_mod
    sid = draft(worker)
    runner, db = worker['runner'], worker['db']
    # a draft whose frame is missing and fails on the worker
    db['component_snapshots'].update_one(
        {'_id': sid}, {'$set': {'frame': None, 'bbx': None},
                       '$unset': {'derivation.frame': ''}})

    def boom(*_a, **_k):
        raise OSError('/srv/x/y.ply: unreadable')
    monkeypatch.setattr(stages_mod, '_stage_frame', boom)
    outcome = runner.process(sid, ['frame'], force=True)
    assert 'frame' in outcome.errors
    stored = db['component_snapshots'].find_one({'_id': sid})
    stamp = stored['derivation']['frame']
    assert stamp['error'] and '/srv' not in stamp['error']
    assert stored.get('frame') is None
    # converged: the error is current, dependents are blocked, nothing listed
    items, _ = runner.stale(HEAVY_STAGES, 100)
    mine = [i for i in items if i['snapshot_id'] == sid]
    # what reads the frame is blocked; previews read only the geometry
    assert not mine or set(mine[0]['stale']) == {'previews'}
    visited, uploaded, refused = run_remote(
        runner, list(HEAVY_STAGES), None, snapshot=sid)
    assert refused == 0
    left, _ = runner.stale(HEAVY_STAGES, 100)
    assert sid not in [i['snapshot_id'] for i in left]


def test_a_failing_complexity_on_the_worker_is_stamped(worker, monkeypatch):
    import apps.catalog.geometry_stages as stages_mod
    sid = draft(worker)
    runner, db = worker['runner'], worker['db']
    db['component_snapshots'].update_one(
        {'_id': sid}, {'$set': {'complexity': None,
                                'complexity_source': None},
                       '$unset': {'derivation.complexity': ''}})

    def boom(*_a, **_k):
        raise ValueError('no residual')
    monkeypatch.setattr(stages_mod, '_stage_complexity', boom)
    outcome = runner.process(sid, ['complexity'], force=True)
    assert 'complexity' in outcome.errors
    stored = db['component_snapshots'].find_one({'_id': sid})
    assert stored['derivation']['complexity']['error'] == (
        'ValueError: no residual')
    assert stored.get('complexity') is None
    items, _ = runner.stale(['complexity'], 100)
    assert sid not in [i['snapshot_id'] for i in items]
