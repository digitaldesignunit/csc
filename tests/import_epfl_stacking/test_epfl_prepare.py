"""prepare.py: the files of a stone as the Grasshopper client would send them (decision 8.146); tiny
spheres made in the tests, never the dataset."""

from __future__ import annotations

import json
import sys

import pytest

import epfl_samples as samples

np = pytest.importorskip('numpy')
trimesh = pytest.importorskip('trimesh')


def stone(tmp_path, stone_id='A0', subdivisions=3, radius=100.0, cloud_points=3000, cloud_unit=0.001):
    root = tmp_path / 'data'
    samples.write_stone(root, stone_id, subdivisions=subdivisions, radius_mm=radius,
                        cloud_points=cloud_points, cloud_unit=cloud_unit)
    mesh = root / 'stones' / 'mesh_high_res' / f'remeshed_high_res_{stone_id}.ply'
    cloud = root / 'stones' / 'pcd_high_res' / f'pcd_high_res_{stone_id}.ply'
    return mesh, cloud


def run(prepare_module, tmp_path, **kw):
    mesh, cloud = stone(tmp_path, **kw)
    out = tmp_path / 'out'
    meta = prepare_module.prepare_stone(kw.get('stone_id', 'A0'), mesh, cloud, out)
    return meta, out / 'stones' / kw.get('stone_id', 'A0')


# READING -------------------------------------------------------------------------------
def test_an_ascii_ply_with_the_material_element_parses_with_its_colours(prepare_module, tmp_path):
    mesh, cloud = stone(tmp_path, subdivisions=2)
    vertices, faces, colors = prepare_module.load_mesh(mesh)
    assert len(faces) == 320 and len(vertices) == 162 and colors.shape == (162, 3)
    assert colors.dtype == np.uint8 and colors[:, 1].tolist() == [120] * 162      # the green of the fixture
    points, point_colors = prepare_module.load_cloud(cloud)
    assert len(points) == 3000 and point_colors.shape == (3000, 3)


def test_a_file_without_faces_is_refused(prepare_module, tmp_path):
    path = tmp_path / 'empty.ply'
    path.write_text('ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\nproperty float y\n'
                    'property float z\nend_header\n0 0 0\n1 0 0\n0 1 0\n', encoding='ascii')
    with pytest.raises(ValueError):
        prepare_module.load_mesh(path)


# UNITS ---------------------------------------------------------------------------------
def test_a_stone_in_metres_is_flagged_and_never_rescaled(prepare_module, tmp_path):
    meta, folder = run(prepare_module, tmp_path, radius=0.1, cloud_unit=1.0)           # a mesh in metres
    assert meta['bbox_mm'] == pytest.approx([0.2, 0.2, 0.2], abs=0.01)                  # as it is
    assert any('outside 20..3000 mm' in f for f in meta['flags'])
    assert len([f for f in meta['flags'] if 'outside' in f]) == 3                       # one per extent


def test_a_stone_in_millimetres_is_not_flagged(prepare_module, tmp_path):
    meta, _ = run(prepare_module, tmp_path)
    assert not [f for f in meta['flags'] if 'outside' in f]
    assert meta['bbox_mm'] == pytest.approx([200, 200, 200], abs=2)


def test_the_size_range_is_the_one_of_the_coordinator(prepare_module):
    assert prepare_module.size_flags([20.0, 3000.0, 1500.0]) == []
    assert len(prepare_module.size_flags([19.9, 3000.1, 100.0])) == 2


def test_a_cloud_in_metres_is_brought_to_the_unit_of_the_mesh(prepare_module, tmp_path):
    meta, folder = run(prepare_module, tmp_path)                                         # cloud in metres
    assert meta['cloud']['scale_to_mesh_unit'] == 1000.0
    assert meta['cloud']['bbox_mm'] == pytest.approx([200, 200, 200], abs=3)
    assert any('multiplied by 1000' in f for f in meta['flags'])
    inline = json.loads((folder / 'preview.json').read_text())['cloud']['points']
    assert max(abs(c) for p in inline for c in p) == pytest.approx(100.0, abs=1)


def test_a_cloud_in_the_unit_of_the_mesh_is_left_as_it_is(prepare_module, tmp_path):
    meta, _ = run(prepare_module, tmp_path, cloud_unit=1.0)
    assert meta['cloud']['scale_to_mesh_unit'] == 1.0
    assert not any('multiplied' in f for f in meta['flags'])


def test_a_cloud_with_stray_points_keeps_its_unit(prepare_module):
    mesh = np.array([160.0, 112.0, 80.0])
    assert prepare_module.cloud_scale(mesh, mesh / 1000 * 1.4) == 1000.0          # a bit larger: stray points
    assert prepare_module.cloud_scale(mesh, mesh / 1000 / 1.4) == 1000.0
    assert prepare_module.cloud_scale(mesh, mesh * 1.3) == 1.0
    assert prepare_module.cloud_scale(mesh, mesh / 100) is None                    # neither
    assert prepare_module.cloud_scale(mesh, mesh / 10000) is None


def test_a_cloud_that_fits_neither_unit_is_left_out_and_flagged(prepare_module, tmp_path):
    meta, folder = run(prepare_module, tmp_path, cloud_unit=0.01)                        # 1/100: no unit
    assert meta['cloud']['scale_to_mesh_unit'] is None
    assert any('the cloud is left out' in f for f in meta['flags'])
    preview = json.loads((folder / 'preview.json').read_text())
    assert 'cloud' not in preview and not (folder / 'cloud.ply').exists()


# THE LEVELS OF THE CLIENT (decision 8.95) -----------------------------------------------
def test_the_levels_follow_mesh_levels(prepare_module):
    from csc_gh.build import (MESH_PRIMITIVE_TARGET, MESH_PRIMITIVE_THRESHOLD, MESH_REDUCED_TARGET,
                              MESH_REDUCED_THRESHOLD, mesh_levels)
    assert (MESH_PRIMITIVE_TARGET, MESH_PRIMITIVE_THRESHOLD) == (500, 8000)
    assert (MESH_REDUCED_TARGET, MESH_REDUCED_THRESHOLD) == (10000, 15000)
    assert mesh_levels(400) == {'preview_target': None, 'reduced_target': None, 'save_original': False}
    assert mesh_levels(5000)['reduced_target'] is None and mesh_levels(5000)['save_original']
    assert mesh_levels(20000) == {'preview_target': 500, 'reduced_target': 10000, 'save_original': True}


def test_a_small_mesh_goes_up_inline_only(prepare_module, tmp_path):
    meta, folder = run(prepare_module, tmp_path, subdivisions=2)                         # 320 faces
    assert meta['levels'] == {'preview_faces': 320, 'reduced_faces': None, 'detailed': False}
    assert not (folder / 'detailed.ply').exists() and not (folder / 'reduced.ply').exists()
    assert len(json.loads((folder / 'preview.json').read_text())['mesh']['faces']) == 320


def test_a_middle_mesh_is_its_own_preview_and_has_a_detailed_file(prepare_module, tmp_path):
    meta, folder = run(prepare_module, tmp_path, subdivisions=4)                         # 5120 faces
    assert meta['levels'] == {'preview_faces': 5120, 'reduced_faces': None, 'detailed': True}
    assert (folder / 'detailed.ply').is_file() and not (folder / 'reduced.ply').exists()


def test_a_big_mesh_has_preview_reduced_and_detailed(prepare_module, tmp_path):
    meta, folder = run(prepare_module, tmp_path, subdivisions=5)                         # 20480 faces
    assert meta['faces'] == 20480
    assert meta['levels']['detailed'] is True
    assert abs(meta['levels']['preview_faces'] - 500) <= 25
    assert abs(meta['levels']['reduced_faces'] - 10000) <= 500
    preview = json.loads((folder / 'preview.json').read_text())
    assert len(preview['mesh']['faces']) == meta['levels']['preview_faces']
    assert len(trimesh.load(folder / 'reduced.ply', process=False).faces) == meta['levels']['reduced_faces']
    original = trimesh.load(folder / 'detailed.ply', process=False)
    assert len(original.faces) == 20480                                                  # the original, whole
    assert original.visual.kind == 'vertex'                                              # with its colours


# COLOURS -------------------------------------------------------------------------------
def test_colours_are_kept_on_the_original_and_carried_to_the_reduced_meshes(prepare_module, tmp_path):
    mesh, cloud = stone(tmp_path, subdivisions=5)
    vertices, faces, colors = prepare_module.load_mesh(mesh)
    meta, folder = run(prepare_module, tmp_path / 'again', subdivisions=5)
    detailed = trimesh.load(folder / 'detailed.ply', process=False)
    assert np.array_equal(np.asarray(detailed.visual.vertex_colors)[:, :3], colors)       # unchanged
    reduced = trimesh.load(folder / 'reduced.ply', process=False)
    rcolors = np.asarray(reduced.visual.vertex_colors)[:, :3]
    from scipy.spatial import cKDTree
    distance, nearest = cKDTree(vertices).query(np.asarray(reduced.vertices, dtype=float))
    assert distance.max() < 20.0                                  # still on the stone (a sphere of 100 mm)
    assert np.array_equal(rcolors, colors[nearest])                                       # nearest vertex
    preview = json.loads((folder / 'preview.json').read_text())['mesh']
    assert len(preview['colors']) == len(preview['vertices'])
    # the gradient follows x: low x has a low red, whatever the reduction
    order = np.argsort(np.asarray(reduced.vertices)[:, 0])
    assert rcolors[order[:20], 0].mean() < rcolors[order[-20:], 0].mean()


def test_decimate_keeps_a_mesh_that_is_small_enough(prepare_module):
    vertices, faces = samples.sphere(2, 50.0)
    v, f, c = prepare_module.decimate(vertices, faces, samples.gradient_colors(vertices), 500)
    assert len(f) == 320 and c is not None and len(c) == len(v)


# THE CLOUD (thinning and staging) -------------------------------------------------------
def test_a_big_cloud_is_thinned_inline_and_staged_whole(prepare_module, tmp_path):
    meta, folder = run(prepare_module, tmp_path, cloud_points=20000)
    assert meta['cloud'] == {'points': 20000, 'scale_to_mesh_unit': 1000.0, 'inline_points': 5000,
                             'staged': True, 'bbox_mm': meta['cloud']['bbox_mm']}
    inline = json.loads((folder / 'preview.json').read_text())['cloud']
    assert len(inline['points']) == 5000 and len(inline['colors']) == 5000
    full = trimesh.load(folder / 'cloud.ply', process=False)
    assert len(full.vertices) == 20000 and len(full.colors) == 20000                      # whole, coloured
    assert max(abs(full.vertices.min()), full.vertices.max()) == pytest.approx(100.0, abs=1)


def test_a_small_cloud_goes_up_inline_only(prepare_module, tmp_path):
    meta, folder = run(prepare_module, tmp_path, cloud_points=3000)
    assert meta['cloud']['inline_points'] == 3000 and meta['cloud']['staged'] is False
    assert not (folder / 'cloud.ply').exists()


def test_the_staging_threshold_is_the_clients(prepare_module):
    from csc_gh.build import POINT_CLOUD_INLINE_MAX, POINT_CLOUD_STAGING_THRESHOLD
    assert (POINT_CLOUD_INLINE_MAX, POINT_CLOUD_STAGING_THRESHOLD) == (5000, 5000)


# THE STONE'S OWN FACTS ------------------------------------------------------------------
def test_a_mesh_that_is_not_watertight_is_counted_and_goes_up_as_it_is(prepare_module, tmp_path):
    vertices, faces = samples.sphere(3, 100.0)
    mesh = tmp_path / 'data' / 'stones' / 'mesh_high_res' / 'remeshed_high_res_B1.ply'
    samples.write_mesh_ply(mesh, vertices, faces[:-6], samples.gradient_colors(vertices))   # a hole
    cloud = tmp_path / 'data' / 'stones' / 'pcd_high_res' / 'pcd_high_res_B1.ply'
    pts, cols = samples.cloud_on_sphere(2000, 100.0)
    samples.write_cloud_ply(cloud, pts * 0.001, cols)
    meta = prepare_module.prepare_stone('B1', mesh, cloud, tmp_path / 'out')
    assert meta['watertight'] is False and meta['volume_cm3'] is None
    assert meta['faces'] == len(faces) - 6
    assert any('not watertight' in f for f in meta['flags'])


def test_a_watertight_mesh_has_its_volume_in_cm3(prepare_module, tmp_path):
    meta, _ = run(prepare_module, tmp_path, subdivisions=4)
    assert meta['watertight'] is True
    assert meta['volume_cm3'] == pytest.approx(4 / 3 * np.pi * 100 ** 3 / 1000, rel=0.02)


def test_the_colour_of_the_stone_is_the_mean_of_the_scan(prepare_module, tmp_path):
    meta, _ = run(prepare_module, tmp_path)
    points, point_colors = prepare_module.load_cloud(tmp_path / 'data' / 'stones' / 'pcd_high_res' /
                                                     'pcd_high_res_A0.ply')
    assert meta['mean_color'] == [int(round(float(c))) for c in point_colors.mean(axis=0)]


def test_a_second_pass_skips_what_is_done_and_force_does_it_again(prepare_module, tmp_path, capsys):
    stone(tmp_path)
    args = type('A', (), dict(data=tmp_path / 'data', out=tmp_path / 'out', only=None, limit=None, jobs=1,
                              force=False))()
    assert prepare_module.main(args) == 0
    prepared = json.loads((tmp_path / 'out' / 'prepare.json').read_text())
    assert [s['id'] for s in prepared['stones']] == ['A0']
    capsys.readouterr()
    prepare_module.main(args)
    assert '0 to prepare' in capsys.readouterr().out
    args.force = True
    prepare_module.main(args)
    assert '1 to prepare' in capsys.readouterr().out
    report = (tmp_path / 'out' / 'report.md').read_text()
    assert 'Stones prepared: 1' in report and 'Point cloud unit: x1000' in report


def test_prepare_json_lists_every_stone_done_also_after_a_run_for_one(prepare_module, tmp_path):
    for sid in ('A0', 'A1'):
        stone(tmp_path, stone_id=sid)
    args = type('A', (), dict(data=tmp_path / 'data', out=tmp_path / 'out', only=None, limit=None, jobs=1,
                              force=False))()
    prepare_module.main(args)
    args.only, args.force = 'A1', True
    prepare_module.main(args)
    prepared = json.loads((tmp_path / 'out' / 'prepare.json').read_text())
    assert [s['id'] for s in prepared['stones']] == ['A0', 'A1']
