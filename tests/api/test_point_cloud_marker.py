"""The marker for an uploaded full point cloud (0.6.2, decision 8.148): the
upload route lists the cloud's index in ``point_cloud_files`` (like
``mesh_ply_resolutions`` for meshes), the delete route takes it out, and an
import resumes from it without reading the file."""

from __future__ import annotations

import numpy as np
import pytest
import trimesh

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import iid, seed_05_catalog

BEAM = iid('beam')


@pytest.fixture
def story(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    contributor, _ = member_headers({'dbu_zirkus': ['contributor']})
    return {'api': api, 'db': db, 'c': contributor}


def draft(story, clouds=1):
    mesh = trimesh.creation.box(extents=(300, 200, 150))
    thin = np.random.default_rng(0).random((10, 3)) * 100
    geometry = {'meshes': [{'vertices': mesh.vertices.tolist(),
                            'faces': mesh.faces.tolist()}],
                'point_clouds': [{'points': thin.tolist()}
                                 for _ in range(clouds)],
                'proxies': []}
    response = story['api'].post(f'/identities/{BEAM}/snapshots',
                                 json={'geometry': geometry},
                                 headers=story['c'])
    assert response.status_code == 201, response.text
    return response.json()


def stored(story, snapshot_id):
    return story['db']['component_snapshots'].find_one({'_id': snapshot_id})


def cloud_file():
    points = np.random.default_rng(1).random((3000, 3)) * 100
    return ('cloud.ply', trimesh.PointCloud(points).export(file_type='ply'),
            'application/octet-stream')


def put(story, snapshot_id, index=0):
    return story['api'].put(
        f'/snapshots/{snapshot_id}/point_clouds/{index}.ply',
        files={'point_cloud_file': cloud_file()}, headers=story['c'])


def test_a_new_version_has_no_cloud_file_marked(story):
    created = draft(story)
    assert created['point_cloud_files'] == []
    assert stored(story, created['_id'])['point_cloud_files'] == []


def test_the_upload_marks_the_cloud_and_the_snapshot_serves_it(story):
    created = draft(story)
    reply = put(story, created['_id'])
    assert reply.status_code == 200, reply.text
    assert reply.json()['point_cloud_files'] == [0]
    got = story['api'].get(f'/snapshots/{created["_id"]}', headers=story['c'])
    assert got.status_code == 200 and got.json()['point_cloud_files'] == [0]


def test_a_second_upload_of_the_same_cloud_keeps_one_entry(story):
    created = draft(story)
    assert put(story, created['_id']).status_code == 200
    assert put(story, created['_id']).json()['point_cloud_files'] == [0]


def test_each_cloud_is_marked_on_its_own_and_listed_in_order(story):
    created = draft(story, clouds=2)
    assert put(story, created['_id'], 1).json()['point_cloud_files'] == [1]
    assert put(story, created['_id'], 0).json()['point_cloud_files'] == [0, 1]


def test_the_marker_changes_the_etag(story):
    created = draft(story)
    before = stored(story, created['_id'])['etag']
    assert put(story, created['_id']).status_code == 200
    assert stored(story, created['_id'])['etag'] != before


def test_the_delete_takes_the_marker_out(story):
    created = draft(story, clouds=2)
    put(story, created['_id'], 0)
    put(story, created['_id'], 1)
    gone = story['api'].delete(f'/snapshots/{created["_id"]}/point_clouds/0.ply',
                               headers=story['c'])
    assert gone.status_code == 200, gone.text
    assert gone.json()['point_cloud_files'] == [1]
    assert stored(story, created['_id'])['point_cloud_files'] == [1]


def test_a_refused_upload_leaves_no_marker(story):
    created = draft(story)
    bad = story['api'].put(
        f'/snapshots/{created["_id"]}/point_clouds/3.ply',
        files={'point_cloud_file': cloud_file()}, headers=story['c'])
    assert bad.status_code == 400
    notply = story['api'].put(
        f'/snapshots/{created["_id"]}/point_clouds/0.ply',
        files={'point_cloud_file': ('cloud.ply', b'not a ply file',
                                    'application/octet-stream')},
        headers=story['c'])
    assert notply.status_code == 400
    assert stored(story, created['_id'])['point_cloud_files'] == []


def test_a_client_cannot_set_the_marker(story):
    created = draft(story)
    got = story['api'].patch(f'/snapshots/{created["_id"]}',
                             json={'point_cloud_files': [0]},
                             headers=story['c'])
    assert got.status_code in (400, 422), got.text
    assert stored(story, created['_id'])['point_cloud_files'] == []


def test_uploads_at_once_do_not_lose_each_others_markers(story):
    """Each marker is one atomic update of its own list entry: eight clouds
    uploaded at the same time are all marked (decision 8.160, the lost update
    of the T1 review)."""
    from concurrent.futures import ThreadPoolExecutor
    created = draft(story, clouds=8)
    with ThreadPoolExecutor(8) as pool:
        replies = list(pool.map(lambda i: put(story, created['_id'], i), range(8)))
    assert [r.status_code for r in replies] == [200] * 8, [r.text for r in replies]
    assert stored(story, created['_id'])['point_cloud_files'] == list(range(8))
    with ThreadPoolExecutor(8) as pool:
        gone = list(pool.map(lambda i: story['api'].delete(
            f'/snapshots/{created["_id"]}/point_clouds/{i}.ply', headers=story['c']), range(0, 8, 2)))
    assert [r.status_code for r in gone] == [200] * 4
    assert stored(story, created['_id'])['point_cloud_files'] == [1, 3, 5, 7]


def test_the_etag_follows_the_markers(story):
    from apps.catalog.etag import compute_snapshot_etag
    created = draft(story, clouds=2)
    put(story, created['_id'], 0)
    put(story, created['_id'], 1)
    doc = stored(story, created['_id'])
    assert doc['point_cloud_files'] == [0, 1] and doc['etag'] == compute_snapshot_etag(doc)


def test_mesh_manifests_of_one_snapshot_survive_uploads_at_once(story):
    from concurrent.futures import ThreadPoolExecutor
    created = draft(story)
    mesh = trimesh.creation.box(extents=(300, 200, 150)).export(file_type='ply')

    def upload(resolution):
        return story['api'].put(
            f'/snapshots/{created["_id"]}/meshes/0/{resolution}',
            files={'mesh_file': (f'{resolution}.ply', mesh, 'application/octet-stream')},
            headers=story['c'])

    with ThreadPoolExecutor(2) as pool:
        replies = list(pool.map(upload, ['detailed', 'reduced']))
    assert [r.status_code for r in replies] == [200, 200], [r.text for r in replies]
    doc = stored(story, created['_id'])
    assert doc['mesh_ply_resolutions'] == {'0': ['reduced', 'detailed']}
    from apps.catalog.etag import compute_snapshot_etag
    assert doc['etag'] == compute_snapshot_etag(doc)
    gone = story['api'].delete(f'/snapshots/{created["_id"]}/meshes/0/reduced', headers=story['c'])
    assert gone.status_code == 200 and stored(story, created['_id'])['mesh_ply_resolutions'] == {'0': ['detailed']}
    gone = story['api'].delete(f'/snapshots/{created["_id"]}/meshes/0/detailed', headers=story['c'])
    assert gone.status_code == 200 and stored(story, created['_id'])['mesh_ply_resolutions'] == {}
