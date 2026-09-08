"""Tests for point-cloud geometry loading in descriptor computation."""

from __future__ import annotations

import numpy as np
import pytest

from apps.descriptors.boxscore import compute_boxscore
from apps.descriptors.geometry import (
    convex_hull_from_points,
    load_point_cloud_mesh_for_descriptor,
    load_snapshot_mesh,
)
from apps.descriptors.linescore import compute_linescore
from apps.descriptors.planescore import compute_planescore
from apps.descriptors.spherescore import compute_spherescore


def _box_points(hx=50.0, hy=30.0, hz=10.0, per_edge=5):
    """Dense-ish sampling of a box surface, corners included."""
    xs = np.linspace(-hx, hx, per_edge)
    ys = np.linspace(-hy, hy, per_edge)
    zs = np.linspace(-hz, hz, per_edge)
    grid = np.array([[x, y, z] for x in xs for y in ys for z in zs])
    on_surface = (
        (np.abs(grid[:, 0]) == hx)
        | (np.abs(grid[:, 1]) == hy)
        | (np.abs(grid[:, 2]) == hz)
    )
    return grid[on_surface].tolist()


def _tetra_points():
    return [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def _snapshot(geometry, snapshot_id='snap-1'):
    return {'_id': snapshot_id, 'geometry': geometry}


# CONVEX HULL HELPER ---------------------------------------------------------

def test_convex_hull_of_box_points_matches_box_volume():
    hull = convex_hull_from_points(_box_points())
    assert hull.is_volume
    assert hull.volume == pytest.approx(100.0 * 60.0 * 20.0, rel=1e-6)


def test_convex_hull_accepts_numpy_input():
    hull = convex_hull_from_points(np.array(_tetra_points()))
    assert len(hull.faces) == 4


def test_convex_hull_drops_non_finite_points():
    points = _tetra_points() + [[np.nan, 0.0, 0.0], [np.inf, 1.0, 1.0]]
    hull = convex_hull_from_points(points)
    assert hull.volume == pytest.approx(1.0 / 6.0, rel=1e-6)


def test_convex_hull_rejects_too_few_points():
    with pytest.raises(ValueError, match='at least 4 finite points'):
        convex_hull_from_points([[0, 0, 0], [1, 0, 0], [0, 1, 0]])


def test_convex_hull_rejects_wrong_shape():
    with pytest.raises(ValueError, match=r'\[x, y, z\] triplets'):
        convex_hull_from_points([[0, 0], [1, 0], [0, 1], [1, 1]])


def test_convex_hull_rejects_coplanar_points():
    coplanar = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0], [2, 2, 0]]
    with pytest.raises(ValueError, match='degenerate'):
        convex_hull_from_points(coplanar)


def test_convex_hull_accepts_thin_but_solid_cloud():
    """A real panel scan is thin, not flat; it must still hull."""
    hull = convex_hull_from_points(_box_points(500.0, 250.0, 6.0))
    assert hull.volume == pytest.approx(1000.0 * 500.0 * 12.0, rel=1e-6)


def test_point_cloud_loader_applies_pca_frame():
    pca_frame = {
        'o': [0.0, 0.0, 0.0],
        'x': [0.0, 1.0, 0.0],
        'y': [-1.0, 0.0, 0.0],
        'z': [0.0, 0.0, 1.0],
    }
    hull = load_point_cloud_mesh_for_descriptor(
        _box_points(), pca_frame=pca_frame)
    extents = np.sort(hull.bounds[1] - hull.bounds[0])
    assert extents == pytest.approx([20.0, 60.0, 100.0], rel=1e-6)


# SNAPSHOT LOADING PRIORITY --------------------------------------------------

def test_point_cloud_only_snapshot_loads_hull():
    mesh = load_snapshot_mesh(
        _snapshot({'point_clouds': [{'points': _box_points()}]}))
    assert mesh is not None
    assert len(mesh.faces) > 0
    assert mesh.volume == pytest.approx(100.0 * 60.0 * 20.0, rel=1e-6)


def test_inline_mesh_supersedes_point_cloud():
    geometry = {
        'meshes': [{
            'vertices': _tetra_points(),
            'faces': [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]],
        }],
        'point_clouds': [{'points': _box_points()}],
    }
    mesh = load_snapshot_mesh(_snapshot(geometry))
    assert mesh is not None
    # Tetra volume, not the much larger point-cloud box.
    assert mesh.volume == pytest.approx(1.0 / 6.0, rel=1e-6)


def test_extrusion_supersedes_point_cloud():
    geometry = {
        'extrusions': [{
            'profile': [[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]],
            'height': 2.0,
        }],
        'point_clouds': [{'points': _box_points()}],
    }
    mesh = load_snapshot_mesh(_snapshot(geometry))
    assert mesh is not None
    assert mesh.volume == pytest.approx(8.0, rel=1e-6)


def test_empty_point_cloud_yields_no_mesh():
    assert load_snapshot_mesh(
        _snapshot({'point_clouds': [{'points': []}]})) is None


def test_degenerate_point_cloud_yields_no_mesh():
    geometry = {'point_clouds': [{'points': [[0, 0, 0], [1, 0, 0]]}]}
    assert load_snapshot_mesh(_snapshot(geometry)) is None


def test_point_cloud_ply_on_disk_supersedes_inline_preview(tmp_path):
    import trimesh

    snapshot_id = 'snap-ply'
    cloud_dir = tmp_path / snapshot_id
    cloud_dir.mkdir()
    full = trimesh.PointCloud(np.array(_box_points()))
    (cloud_dir / '0.ply').write_bytes(full.export(file_type='ply'))

    # Inline preview is a much smaller subsample of the same object.
    geometry = {'point_clouds': [{'points': _tetra_points()}]}
    mesh = load_snapshot_mesh(
        _snapshot(geometry, snapshot_id),
        point_clouds_dir=str(tmp_path),
    )
    assert mesh is not None
    assert mesh.volume == pytest.approx(100.0 * 60.0 * 20.0, rel=1e-6)


# SCORES ON POINT-CLOUD HULLS ------------------------------------------------

def test_all_scores_compute_on_point_cloud_hull():
    mesh = load_snapshot_mesh(
        _snapshot({'point_clouds': [{'points': _box_points()}]}))
    assert mesh is not None

    # A box-shaped cloud: hull fills its OBB, so boxscore is ~0.
    assert compute_boxscore(mesh) == pytest.approx(0.0, abs=1e-6)
    assert compute_spherescore(mesh) > 0.0
    assert 0.0 < compute_linescore(mesh) <= 100.0
    assert 0.0 < compute_planescore(mesh) <= 100.0


def test_point_cloud_and_mesh_scores_agree_for_same_shape():
    """Scores are hull/OBB based, so a cloud and a mesh of one shape match."""
    points = _box_points()
    cloud_mesh = load_snapshot_mesh(
        _snapshot({'point_clouds': [{'points': points}]}))

    hull = convex_hull_from_points(points)
    mesh_geometry = {
        'meshes': [{
            'vertices': hull.vertices.tolist(),
            'faces': hull.faces.tolist(),
        }],
    }
    real_mesh = load_snapshot_mesh(_snapshot(mesh_geometry))

    assert compute_boxscore(cloud_mesh) == pytest.approx(
        compute_boxscore(real_mesh), abs=1e-9)
    assert compute_linescore(cloud_mesh) == pytest.approx(
        compute_linescore(real_mesh), abs=1e-9)
