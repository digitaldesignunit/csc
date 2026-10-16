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
