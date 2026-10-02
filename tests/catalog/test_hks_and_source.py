"""HKS descriptor (decision 8.6), geometry source and fingerprint (8.47),
and the runner's command line."""

from __future__ import annotations

import os

import numpy as np
import pytest
import trimesh

from apps.catalog.geometry_source import (
    NoGeometry,
    load_source,
    source_fingerprint,
    stored_files,
)
from apps.catalog.proxies.sampling import sample_surface
from apps.descriptors.hks import HKS_EIGS, HKS_TIMES, compute_hks, hks_time_grid
from main_geometry import _limit, _parse_args, parse_stages


def box_geometry(mesh):
    return {'meshes': [{'vertices': mesh.vertices.tolist(),
                        'faces': mesh.faces.tolist()}]}


def source_of(mesh):
    return load_source({'_id': 's', 'geometry': box_geometry(mesh)})


def test_hks_has_fixed_length_unit_norm_and_is_deterministic():
    mesh = trimesh.creation.box(extents=(300, 200, 100))
    first, second = compute_hks(source_of(mesh)), compute_hks(source_of(mesh))
    assert len(first) == 2 * HKS_TIMES
    assert first == second
    assert np.linalg.norm(first) == pytest.approx(1.0, abs=1e-6)


def test_hks_is_scale_invariant_and_tells_shapes_apart():
    box = trimesh.creation.box(extents=(300, 200, 100))
    big = trimesh.creation.box(extents=(600, 400, 200))
    ball = trimesh.creation.icosphere(subdivisions=3, radius=100)
    a, b, c = (np.array(compute_hks(source_of(m))) for m in (box, big, ball))
    # the same shape at another size is far closer than another shape
    assert np.linalg.norm(a - b) < np.linalg.norm(a - c) / 3


def test_hks_time_grid_is_one_frozen_grid():
    grid = hks_time_grid()
    assert len(grid) == HKS_TIMES and HKS_EIGS == 64
    assert np.all(np.diff(grid) > 0)
    assert grid[0] == pytest.approx(5.187876e-03)
    assert grid[-1] == pytest.approx(3.454702e-01)


def test_hks_of_a_sparse_cloud_raises():
    sparse = load_source({'_id': 's', 'geometry': {'point_clouds': [
        {'points': [[i, i % 3, 0] for i in range(10)]}]}})
    with pytest.raises(ValueError, match='surface points'):
        compute_hks(sparse)


def test_surface_sample_is_seeded_and_area_uniform():
    mesh = trimesh.creation.box(extents=(400, 100, 10))
    source = source_of(mesh)
    a, b = sample_surface(source, 4000), sample_surface(source, 4000)
    assert np.array_equal(a.points, b.points)
    top = np.isclose(a.points[:, 2], 5).mean() \
        + np.isclose(a.points[:, 2], -5).mean()
    assert top == pytest.approx(2 * 400 * 100 / mesh.area, abs=0.05)


def test_source_prefers_meshes_then_clouds_then_authored_proxies():
    mesh = trimesh.creation.box(extents=(10, 10, 10))
    cloud = {'points': [[0, 0, 0], [1, 1, 1], [2, 0, 1], [0, 2, 3]]}
    authored = {'primitive': 'box', 'params': {'size': [4, 4, 4]},
                'placement': {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0],
                              'z': [0, 0, 1]},
                'fit': {'method': 'authored'}}
    both = {'_id': 's', 'geometry': {**box_geometry(mesh),
                                     'point_clouds': [cloud],
                                     'proxies': [authored]}}
    assert load_source(both).kind == 'meshes'
    assert load_source({'_id': 's', 'geometry': {
        'point_clouds': [cloud], 'proxies': [authored]}}).kind \
        == 'point_clouds'
    assert load_source({'_id': 's', 'geometry': {
        'proxies': [authored]}}).kind == 'authored'
    with pytest.raises(NoGeometry):
        load_source({'_id': 's', 'geometry': {}})


def test_all_meshes_are_component_geometry():
    a = trimesh.creation.box(extents=(10, 10, 10))
    b = trimesh.creation.box(extents=(10, 10, 10))
    b.apply_translation([100, 0, 0])
    geometry = {'meshes': box_geometry(a)['meshes'] + box_geometry(b)['meshes']}
    source = load_source({'_id': 's', 'geometry': geometry})
    assert len(source.meshes) == 2
    assert source.points()[:, 0].max() == pytest.approx(105)


def test_fingerprint_follows_geometry_and_files(tmp_path):
    mesh = trimesh.creation.box(extents=(10, 20, 30))
    snapshot = {'_id': 's1', 'geometry': box_geometry(mesh),
                'mesh_ply_resolutions': {'0': ['reduced']}}
    meshes = tmp_path / 'meshes'
    plain = source_fingerprint(snapshot, str(meshes))
    assert plain == source_fingerprint(snapshot, str(meshes))
    (meshes / 's1' / '0').mkdir(parents=True)
    ply = meshes / 's1' / '0' / 'reduced.ply'
    mesh.export(str(ply))
    with_file = source_fingerprint(snapshot, str(meshes))
    assert with_file != plain
    assert stored_files(snapshot, str(meshes)) == {
        'meshes': {'0': 'reduced'}, 'point_clouds': []}
    os.utime(ply, ns=(1, 1))
    assert source_fingerprint(snapshot, str(meshes)) != with_file
    moved = {**snapshot, 'geometry': box_geometry(mesh.copy().apply_scale(2))}
    assert source_fingerprint(moved, str(meshes)) != source_fingerprint(
        snapshot, str(meshes))


def test_fingerprint_ignores_fitted_proxies_and_markers():
    mesh = trimesh.creation.box(extents=(10, 20, 30))
    plain = {'_id': 's', 'geometry': box_geometry(mesh)}
    fitted = {'_id': 's', 'geometry': {**box_geometry(mesh), 'proxies': [
        {'primitive': 'box', 'fit': {'method': 'obb'}, 'params': {}}]},
        'capture': {'markers': [{'label': 'm', 'role': 'rig',
                                 'point': [1, 2, 3]}]}}
    assert source_fingerprint(plain) == source_fingerprint(fitted)


# THE RUNNER'S COMMAND LINE ---------------------------------------------------
def test_default_is_cron_mode_with_a_small_limit():
    args = _parse_args([])
    assert args.stages is None             # all, or the light two (remote)
    assert _limit(args) == 5
    assert _limit(_parse_args(['--all'])) is None
    assert _limit(_parse_args(['--snapshot', 'x'])) is None
    assert _limit(_parse_args(['--limit', '7'])) == 7


def test_limit_must_be_positive(capsys):
    with pytest.raises(SystemExit):
        _limit(_parse_args(['--limit', '0']))
    assert '--limit' in capsys.readouterr().err


def test_stages_can_be_given_with_an_equals_sign():
    assert _parse_args(['--stages=proxies']).stages == ['proxies']
    assert _parse_args(['--stages', 'frame,previews']).stages == [
        'frame', 'previews']


def test_the_orphan_sweep_deletes_only_snapshot_named_entries(tmp_path):
    from main_geometry import _sweep_orphans
    live = '11111111-1111-1111-1111-111111111111'
    gone = '22222222-2222-2222-2222-222222222222'
    previews, proxies = tmp_path / 'previews', tmp_path / 'proxies'
    for folder in (previews, proxies):
        folder.mkdir()
    for name in (live, gone, 'notes', 'meshes'):
        (proxies / name).mkdir()
        (proxies / name / 'x.png').write_bytes(b'x')
    for name in (live, gone, 'logo'):
        (previews / f'{name}.webp').write_bytes(b'x')
    (previews / 'readme.txt').write_text('keep')
    _sweep_orphans(str(previews), str(proxies), {live})
    assert sorted(p.name for p in proxies.iterdir()) == sorted(
        [live, 'notes', 'meshes'])
    assert sorted(p.name for p in previews.iterdir()) == sorted(
        [f'{live}.webp', 'logo.webp', 'readme.txt'])
    _sweep_orphans(str(previews), str(proxies), set())    # empty database
    assert (proxies / live).exists() and (previews / f'{live}.webp').exists()


def test_unknown_stages_are_refused():
    with pytest.raises(SystemExit):
        _parse_args(['--stages', 'frame,teleport'])
    assert parse_stages('shape_class,frame') == ['shape_class', 'frame']
