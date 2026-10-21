"""File markers follow a geometry PATCH on a draft (0.6.3.1): a mesh or cloud
that was replaced or removed loses its marker and its file; one that is
unchanged keeps both. ``reconcile_markers`` is the rule."""

from __future__ import annotations

import os

import numpy as np
import pytest
import trimesh

from apps.catalog.file_markers import reconcile_markers, remove_files
from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import iid, seed_05_catalog

BEAM = iid('beam')


# THE RULE ----------------------------------------------------------------------
def geometry(meshes=(), clouds=()):
    return {'meshes': [{'v': m} for m in meshes],
            'point_clouds': [{'p': c} for c in clouds]}


def test_markers_of_unchanged_primitives_are_kept():
    old = geometry(['a', 'b'], ['x', 'y'])
    done = reconcile_markers(old, geometry(['a', 'b'], ['x', 'y']),
                             {'0': ['reduced', 'detailed'], '1': ['reduced']}, [0, 1])
    assert done.resolutions == {'0': ['reduced', 'detailed'], '1': ['reduced']}
    assert done.cloud_files == [0, 1] and not done.changed


def test_a_replaced_primitive_loses_its_marker_the_others_keep_theirs():
    done = reconcile_markers(geometry(['a', 'b'], ['x', 'y']),
                             geometry(['a', 'CHANGED'], ['x', 'NEW']),
                             {'0': ['reduced'], '1': ['reduced', 'detailed']}, [0, 1])
    assert done.resolutions == {'0': ['reduced']}
    assert done.dropped_meshes == [(1, 'reduced'), (1, 'detailed')]
    assert done.cloud_files == [0] and done.dropped_clouds == [1]


def test_a_primitive_that_is_gone_loses_its_marker():
    done = reconcile_markers(geometry(['a', 'b'], ['x', 'y']),
                             geometry(['a'], ['x']),
                             {'0': ['reduced'], '1': ['reduced']}, [0, 1])
    assert done.resolutions == {'0': ['reduced']} and done.cloud_files == [0]
    assert done.dropped_meshes == [(1, 'reduced')] and done.dropped_clouds == [1]


def test_a_shifted_primitive_is_another_primitive():
    """The file of index 0 described 'a'; index 0 is 'b' now."""
    done = reconcile_markers(geometry(['a', 'b']), geometry(['b']), {'0': ['reduced']}, [])
    assert done.resolutions == {} and done.dropped_meshes == [(0, 'reduced')]


def test_a_marker_beyond_the_old_geometry_is_dropped():
    done = reconcile_markers(geometry(['a']), geometry(['a', 'b']), {'5': ['reduced']}, [7])
    assert done.resolutions == {} and done.cloud_files == [] and done.changed


def test_no_markers_and_no_geometry_are_fine():
    done = reconcile_markers(None, None, None, None)
    assert done.resolutions == {} and done.cloud_files == [] and not done.changed
    done = reconcile_markers({}, {'meshes': 'not a list'}, {'0': ['reduced']}, [0])
    assert done.changed


def test_a_key_that_is_no_index_is_dropped():
    done = reconcile_markers(geometry(['a']), geometry(['a']), {'x': ['reduced']}, [])
    assert done.resolutions == {} and done.dropped_meshes == [(-1, 'reduced')]


def test_the_files_of_dropped_markers_are_removed_and_a_missing_file_is_fine(tmp_path):
    meshes, clouds = tmp_path / 'meshes', tmp_path / 'clouds'
    (meshes / 'sid' / '1').mkdir(parents=True)
    (meshes / 'sid' / '1' / 'reduced.ply').write_bytes(b'ply')
    (meshes / 'sid' / '0').mkdir(parents=True)
    (meshes / 'sid' / '0' / 'reduced.ply').write_bytes(b'ply')
    (clouds / 'sid').mkdir(parents=True)
    (clouds / 'sid' / '1.ply').write_bytes(b'ply')
    (clouds / 'sid' / '0.ply').write_bytes(b'ply')
    done = reconcile_markers(geometry(['a', 'b'], ['x', 'y']), geometry(['a'], ['x']),
                             {'0': ['reduced'], '1': ['reduced', 'detailed']}, [0, 1])
    assert remove_files(str(meshes), str(clouds), 'sid', done) == 2     # detailed.ply was never there
    assert not (meshes / 'sid' / '1').exists()                           # the empty folder went
    assert (meshes / 'sid' / '0' / 'reduced.ply').exists()
    assert (clouds / 'sid' / '0.ply').exists() and not (clouds / 'sid' / '1.ply').exists()


# THE ROUTE ---------------------------------------------------------------------
@pytest.fixture
def story(api, db, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    contributor, _ = member_headers({'dbu_zirkus': ['contributor']})
    return {'api': api, 'db': db, 'c': contributor}


def box(size):
    mesh = trimesh.creation.box(extents=(size, 200, 150))
    return {'vertices': mesh.vertices.tolist(), 'faces': mesh.faces.tolist()}


def cloud(seed):
    return {'points': (np.random.default_rng(seed).random((10, 3)) * 100).tolist()}


def draft(story, meshes, clouds):
    geometry_doc = {'meshes': meshes, 'point_clouds': clouds, 'proxies': []}
    response = story['api'].post(f'/identities/{BEAM}/snapshots',
                                 json={'geometry': geometry_doc}, headers=story['c'])
    assert response.status_code == 201, response.text
    return response.json()['_id']


def ply(seed=1):
    points = np.random.default_rng(seed).random((300, 3)) * 100
    return ('x.ply', trimesh.PointCloud(points).export(file_type='ply'),
            'application/octet-stream')


def put_cloud(story, sid, index):
    done = story['api'].put(f'/snapshots/{sid}/point_clouds/{index}.ply',
                            files={'point_cloud_file': ply(index)}, headers=story['c'])
    assert done.status_code == 200, done.text


def put_mesh(story, sid, index, level='reduced'):
    done = story['api'].put(f'/snapshots/{sid}/meshes/{index}/{level}',
                            files={'mesh_file': ply(index)}, headers=story['c'])
    assert done.status_code == 200, done.text


def stored(story, sid):
    return story['db']['component_snapshots'].find_one({'_id': sid})


def cloud_path(sid, index):
    return os.path.join(os.environ['SNAPSHOT_POINT_CLOUDS_DIR'], sid, f'{index}.ply')


def mesh_path(sid, index, level='reduced'):
    return os.path.join(os.environ['SNAPSHOT_MESHES_DIR'], sid, str(index), f'{level}.ply')


def patch(story, sid, meshes, clouds):
    done = story['api'].patch(
        f'/snapshots/{sid}', headers=story['c'],
        json={'geometry': {'meshes': meshes, 'point_clouds': clouds, 'proxies': []}})
    assert done.status_code == 200, done.text
    return done.json()


def test_replacing_the_meshes_and_clouds_clears_the_markers_and_the_files(story):
    sid = draft(story, [box(300), box(400)], [cloud(1), cloud(2)])
    for index in (0, 1):
        put_cloud(story, sid, index)
        put_mesh(story, sid, index)
    put_mesh(story, sid, 1, 'detailed')
    assert os.path.isfile(cloud_path(sid, 1)) and os.path.isfile(mesh_path(sid, 1, 'detailed'))
    body = patch(story, sid, [box(500), box(600)], [cloud(8), cloud(9)])
    assert body['mesh_ply_resolutions'] == {} and body['point_cloud_files'] == []
    row = stored(story, sid)
    assert row['mesh_ply_resolutions'] == {} and row['point_cloud_files'] == []
    for index in (0, 1):
        assert not os.path.exists(cloud_path(sid, index))
        assert not os.path.exists(mesh_path(sid, index))
    assert not os.path.exists(mesh_path(sid, 1, 'detailed'))


def test_a_patch_that_keeps_the_primitives_keeps_markers_and_files(story):
    sid = draft(story, [box(300)], [cloud(1)])
    put_cloud(story, sid, 0)
    put_mesh(story, sid, 0)
    body = patch(story, sid, [box(300)], [cloud(1)])
    assert body['mesh_ply_resolutions'] == {'0': ['reduced']}
    assert body['point_cloud_files'] == [0]
    assert os.path.isfile(cloud_path(sid, 0)) and os.path.isfile(mesh_path(sid, 0))


def test_only_the_replaced_primitive_loses_its_marker_and_file(story):
    sid = draft(story, [box(300), box(400)], [cloud(1), cloud(2)])
    for index in (0, 1):
        put_cloud(story, sid, index)
        put_mesh(story, sid, index)
    body = patch(story, sid, [box(300), box(450)], [cloud(1), cloud(7)])
    assert body['mesh_ply_resolutions'] == {'0': ['reduced']}
    assert body['point_cloud_files'] == [0]
    assert os.path.isfile(mesh_path(sid, 0)) and not os.path.exists(mesh_path(sid, 1))
    assert os.path.isfile(cloud_path(sid, 0)) and not os.path.exists(cloud_path(sid, 1))


def test_fewer_primitives_leave_no_marker_past_the_new_list(story):
    sid = draft(story, [box(300), box(400)], [cloud(1), cloud(2)])
    for index in (0, 1):
        put_cloud(story, sid, index)
        put_mesh(story, sid, index)
    body = patch(story, sid, [box(300)], [cloud(1)])
    assert body['mesh_ply_resolutions'] == {'0': ['reduced']}
    assert body['point_cloud_files'] == [0]
    assert not os.path.exists(cloud_path(sid, 1)) and not os.path.exists(mesh_path(sid, 1))


def test_the_cloud_is_served_from_the_new_inline_points_after_the_patch(story):
    sid = draft(story, [box(300)], [cloud(1)])
    put_cloud(story, sid, 0)
    patch(story, sid, [box(300)], [cloud(5)])
    served = story['api'].get(f'/snapshots/{sid}/point_clouds/0.ply', headers=story['c'])
    assert served.status_code == 200
    assert served.content[:3] == b'ply'


def test_a_patch_without_geometry_leaves_markers_alone(story):
    sid = draft(story, [box(300)], [cloud(1)])
    put_cloud(story, sid, 0)
    put_mesh(story, sid, 0)
    done = story['api'].patch(f'/snapshots/{sid}', json={'color': [10, 20, 30]},
                              headers=story['c'])
    assert done.status_code == 200, done.text
    assert done.json()['point_cloud_files'] == [0]
    assert done.json()['mesh_ply_resolutions'] == {'0': ['reduced']}
