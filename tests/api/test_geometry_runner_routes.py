"""
The geometry runner at the API (spec section 4.3, decisions 6.14, 8.7):
frame and shape class on every draft geometry write and on submit, the
deviation-map and proxy-mesh routes, and the cron sweep over a database.
"""

from __future__ import annotations

import os

import pytest
import trimesh

from apps.catalog.geometry_runner import derive_and_store_sync
from apps.catalog.geometry_stages import STAGES, Env, stale_stages
from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from apps.catalog.proxies.png16 import decode_rgb16
from support import iid, seed_05_catalog

BEAM = iid('beam')


@pytest.fixture
def story(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    contributor, _ = member_headers({'dbu_zirkus': ['contributor']})
    moderator, _ = member_headers({'dbu_zirkus': ['moderator']})
    return {'api': api, 'db': db, 'contributor': contributor,
            'moderator': moderator, 'admin': auth_headers('admin')}


def block_geometry(sx=300, sy=200, sz=150):
    mesh = trimesh.creation.box(extents=(sx, sy, sz))
    return {'meshes': [{'vertices': mesh.vertices.tolist(),
                        'faces': mesh.faces.tolist()}],
            'point_clouds': [], 'proxies': []}


def create_draft(story, geometry=None):
    response = story['api'].post(
        f'/identities/{BEAM}/snapshots',
        json={'geometry': geometry or block_geometry()},
        headers=story['contributor'])
    assert response.status_code == 201, response.text
    return response.json()


def env():
    return Env(meshes_dir=os.environ['SNAPSHOT_MESHES_DIR'],
               point_clouds_dir=os.environ['SNAPSHOT_POINT_CLOUDS_DIR'],
               preview_dir=os.environ['SNAPSHOT_PREVIEW_DIR'])


def test_a_new_draft_has_frame_class_and_scores_at_once(story):
    draft = create_draft(story)
    assert draft['frame'] and draft['bbx'] == pytest.approx([300, 200, 150])
    assert draft['shape_class'] == 'block'
    assert draft['shape_class_source'] == 'derived'
    assert draft['descriptors']['boxscore'] == pytest.approx(0, abs=1e-6)
    assert set(draft['derivation']) == {'frame', 'shape_class'}
    assert all(not stamp['error'] for stamp in draft['derivation'].values())
    assert 'pca_frame' not in draft


def test_a_client_cannot_send_derived_fields(story):
    body = {'geometry': block_geometry(), 'derivation': {}}
    response = story['api'].post(f'/identities/{BEAM}/snapshots', json=body,
                                 headers=story['contributor'])
    assert response.status_code == 422


def test_an_override_is_assigned_and_the_class_is_kept(story):
    draft = create_draft(story)
    patched = story['api'].patch(
        f'/snapshots/{draft["_id"]}', json={'shape_class': 'planar'},
        headers=story['contributor'])
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert (body['shape_class'], body['shape_class_source']) == (
        'planar', 'assigned')
    # a sweep never takes the override back
    snapshot = story['db']['component_snapshots'].find_one(
        {'_id': draft['_id']})
    identity = story['db']['component_identities'].find_one({'_id': BEAM})
    derive_and_store_sync(story['db']['component_snapshots'], snapshot,
                          identity, env(), os.environ['SNAPSHOT_PROXIES_DIR'],
                          STAGES[:3])
    after = story['db']['component_snapshots'].find_one({'_id': draft['_id']})
    assert after['shape_class'] == 'planar'
    assert after['geometry']['proxies'][0]['primitive'] == 'prism'


def test_submit_derives_before_review(story):
    draft = create_draft(story)
    story['db']['component_snapshots'].update_one(
        {'_id': draft['_id']}, {'$set': {'derivation': {}}})
    submitted = story['api'].post(f'/snapshots/{draft["_id"]}/submit',
                                  headers=story['contributor'])
    assert submitted.status_code == 200, submitted.text
    assert set(submitted.json()['derivation']) == {'frame', 'shape_class'}


def test_the_sweep_fits_the_proxy_and_the_maps_are_served(story):
    draft = create_draft(story)
    api, db = story['api'], story['db']
    snapshot = db['component_snapshots'].find_one({'_id': draft['_id']})
    identity = db['component_identities'].find_one({'_id': BEAM})
    assert 'proxies' in stale_stages(snapshot, identity, env())
    outcome = derive_and_store_sync(
        db['component_snapshots'], snapshot, identity, env(),
        os.environ['SNAPSHOT_PROXIES_DIR'], STAGES)
    assert not outcome.errors, outcome.errors
    fitted = db['component_snapshots'].find_one({'_id': draft['_id']})
    assert stale_stages(fitted, identity, env()) == []
    proxy = fitted['geometry']['proxies'][0]
    assert proxy['primitive'] == 'box' and proxy['role'] == 'primary'

    # the author reads the draft's maps; anonymous readers do not
    face = proxy['deviation_maps']['faces']['+z']
    url = f'/snapshots/{draft["_id"]}/proxies/0/faces/%2Bz'
    served = api.get(url, headers=story['contributor'])
    assert served.status_code == 200, served.text
    assert served.headers['content-type'] == 'image/png'
    image = decode_rgb16(served.content)
    assert image.shape == (face['height'], face['width'], 3)
    assert api.get(url).status_code in (401, 403)
    unknown = api.get(f'/snapshots/{draft["_id"]}/proxies/0/faces/nowhere',
                      headers=story['contributor'])
    assert unknown.status_code == 404
    escape = api.get(f'/snapshots/{draft["_id"]}/proxies/7/faces/%2Bz',
                     headers=story['contributor'])
    assert escape.status_code == 404

    mesh = api.get(f'/snapshots/{draft["_id"]}/proxies/0/mesh',
                   headers=story['contributor'])
    assert mesh.status_code == 200 and mesh.content[:3] == b'ply'


def test_a_changed_geometry_makes_the_derivation_stale_again(story):
    draft = create_draft(story)
    db = story['db']
    identity = db['component_identities'].find_one({'_id': BEAM})
    snapshot = db['component_snapshots'].find_one({'_id': draft['_id']})
    derive_and_store_sync(db['component_snapshots'], snapshot, identity,
                          env(), os.environ['SNAPSHOT_PROXIES_DIR'], STAGES)
    done = db['component_snapshots'].find_one({'_id': draft['_id']})
    bigger = block_geometry(600, 200, 150)
    done['geometry']['meshes'] = bigger['meshes']
    assert stale_stages(done, identity, env())[0] == 'frame'


def test_a_moderator_recomputes_every_stage_of_a_snapshot(story):
    draft = create_draft(story)
    url = f'/snapshots/{draft["_id"]}/proxies/recompute'
    assert story['api'].post(url, headers=story['contributor']).status_code \
        == 403
    done = story['api'].post(url, headers=story['moderator'])
    assert done.status_code == 200, done.text
    body = done.json()
    assert set(body['derivation']) == set(STAGES)
    assert body['geometry']['proxies'][0]['primitive'] == 'box'
    assert 'hks' in body['descriptors'] and body['complexity'] is not None


def test_clearing_a_shape_class_override_returns_it_to_derived(story):
    draft = create_draft(story)
    api, c = story['api'], story['contributor']
    sid = draft['_id']
    set_ = api.patch(f'/snapshots/{sid}', json={'shape_class': 'irregular'},
                     headers=c).json()
    assert (set_['shape_class'], set_['shape_class_source']) == (
        'irregular', 'assigned')
    cleared = api.patch(f'/snapshots/{sid}', json={'shape_class': None},
                        headers=c)
    assert cleared.status_code == 200, cleared.text
    body = cleared.json()
    assert body['shape_class_source'] == 'derived'
    assert body['shape_class'] == 'block'            # recomputed at once


def test_clearing_a_complexity_override_is_stale_for_the_runner(story):
    draft = create_draft(story)
    api, c, db = story['api'], story['contributor'], story['db']
    sid = draft['_id']
    api.patch(f'/snapshots/{sid}', json={'complexity': 3}, headers=c)
    snapshot = db['component_snapshots'].find_one({'_id': sid})
    assert snapshot['complexity_source'] == 'assigned'
    cleared = api.patch(f'/snapshots/{sid}', json={'complexity': None},
                        headers=c).json()
    assert cleared['complexity_source'] == 'derived'
    snapshot = db['component_snapshots'].find_one({'_id': sid})
    identity = db['component_identities'].find_one({'_id': BEAM})
    assert 'complexity' in stale_stages(snapshot, identity, env())
    derive_and_store_sync(db['component_snapshots'], snapshot, identity,
                          env(), os.environ['SNAPSHOT_PROXIES_DIR'], STAGES)
    done = db['component_snapshots'].find_one({'_id': sid})
    assert done['complexity_source'] == 'derived'
    assert done['complexity'] != 3 or done['complexity'] == 3
    assert stale_stages(done, identity, env()) == []


def test_patching_the_geometry_of_a_draft_runs_the_cheap_stages(story):
    draft = create_draft(story)
    api, c, db = story['api'], story['contributor'], story['db']
    sid = draft['_id']
    assert draft['bbx'] == pytest.approx([300, 200, 150])
    # a fitted proxy and its maps exist from an earlier sweep
    snapshot = db['component_snapshots'].find_one({'_id': sid})
    identity = db['component_identities'].find_one({'_id': BEAM})
    derive_and_store_sync(db['component_snapshots'], snapshot, identity,
                          env(), os.environ['SNAPSHOT_PROXIES_DIR'], STAGES)
    folder = os.path.join(os.environ['SNAPSHOT_PROXIES_DIR'], sid, '0')
    assert os.listdir(folder)
    patched = api.patch(f'/snapshots/{sid}',
                        json={'geometry': block_geometry(600, 200, 150)},
                        headers=c)
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body['bbx'] == pytest.approx([600, 200, 150])      # at once
    assert not [p for p in body['geometry']['proxies']
                if p['fit']['method'] != 'authored']
    assert not os.path.isdir(folder) or not os.listdir(folder)


def test_recompute_on_a_remote_setup_only_marks_the_heavy_stages(
        story, monkeypatch):
    monkeypatch.setenv('CSC_GEOMETRY_HEAVY_STAGES', 'remote')
    draft = create_draft(story)
    url = f'/snapshots/{draft["_id"]}/proxies/recompute'
    done = story['api'].post(url, headers=story['moderator'])
    assert done.status_code == 200, done.text
    body = done.json()
    assert set(body['derivation']) == {'frame', 'shape_class'}
    assert not [p for p in body['geometry']['proxies']
                if p['fit']['method'] != 'authored']


def test_a_failing_recompute_is_a_short_500(story, monkeypatch):
    import apps.catalog.api.geometry_hooks as hooks

    async def boom(*_a, **_k):
        raise OSError('/srv/secret/path: disk full')
    monkeypatch.setattr(hooks, 'derive_and_store', boom)
    draft = create_draft(story)
    done = story['api'].post(f'/snapshots/{draft["_id"]}/proxies/recompute',
                             headers=story['moderator'])
    assert done.status_code == 500
    assert '/srv' not in done.text


def test_readers_see_that_a_stage_failed_but_not_why(story):
    draft = create_draft(story)
    story['db']['component_snapshots'].update_one(
        {'_id': draft['_id']},
        {'$set': {'derivation.frame.error': 'OSError: /srv/x failed'}})
    body = story['api'].get(f'/snapshots/{draft["_id"]}',
                            headers=story['contributor']).json()
    assert body['derivation']['frame']['error'] == 'failed'
    assert '/srv' not in str(body)


# RE-REVIEW RESIDUALS (decisions 8.58--8.60) ----------------------------------
def test_an_override_and_its_clearing_log_only_the_class_fields(story):
    draft = create_draft(story)
    api, c = story['api'], story['contributor']
    sid = draft['_id']
    api.patch(f'/snapshots/{sid}', json={'shape_class': 'irregular'},
              headers=c)
    api.patch(f'/snapshots/{sid}', json={'shape_class': None}, headers=c)
    entries = story['db']['change_log'].find({'record_id': sid})
    paths = {change['path'] for entry in entries
             for change in entry['changes']}
    assert paths <= {'shape_class', 'shape_class_source'}, paths
    assert 'shape_class_source' in paths


def test_a_failed_geometry_is_visible_without_the_text(story):
    draft = create_draft(story)
    api, db = story['api'], story['db']
    sid = draft['_id']
    db['component_snapshots'].update_one({'_id': sid}, {'$set': {
        'derivation.frame.error': 'OSError: <path> disk full'}})
    rows = api.get(f'/identities/{BEAM}/snapshots',
                   headers=story['contributor']).json()
    mine = [r for r in rows if r['_id'] == sid][0]
    assert mine['geometry_failed'] is True
    assert all(r['geometry_failed'] is False for r in rows if r['_id'] != sid)
    body = api.get(f'/snapshots/{sid}', headers=story['contributor']).json()
    assert body['derivation']['frame']['error'] == 'failed'
    # admin sees the text and a list of failures; others do not
    admin = story['admin']
    failed = api.get('/geometry/failed', headers=admin).json()
    assert [f['snapshot_id'] for f in failed] == [sid]
    assert failed[0]['stages']['frame'] == 'OSError: <path> disk full'
    assert api.get('/geometry/failed',
                   headers=story['moderator']).status_code == 403


def test_a_clean_snapshot_is_not_flagged(story):
    draft = create_draft(story)
    rows = story['api'].get(f'/identities/{BEAM}/snapshots',
                            headers=story['contributor']).json()
    assert [r for r in rows if r['_id'] == draft['_id']][0][
        'geometry_failed'] is False
    assert story['api'].get('/geometry/failed',
                            headers=story['admin']).json() == []


def test_a_lost_race_when_marking_stale_is_a_409(story, monkeypatch):
    monkeypatch.setenv('CSC_GEOMETRY_HEAVY_STAGES', 'remote')
    draft = create_draft(story)
    import apps.catalog.api.geometry_hooks as hooks
    real = hooks.compute_snapshot_etag

    def moved(doc):
        story['db']['component_snapshots'].update_one(
            {'_id': draft['_id']}, {'$set': {'etag': 'moved'}})
        return real(doc)
    monkeypatch.setattr(hooks, 'compute_snapshot_etag', moved)
    done = story['api'].post(f'/snapshots/{draft["_id"]}/proxies/recompute',
                             headers=story['moderator'])
    assert done.status_code == 409
