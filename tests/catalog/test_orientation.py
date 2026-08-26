"""Tests for snapshot orientation computation."""

from __future__ import annotations

import pytest

from apps.catalog.orientation import (
    compute_snapshot_orientation,
    orientation_result_to_dict,
)


def test_box_extrusion_orientation_returns_pca_frame():
    geometry = {
        'extrusions': [{
            'profile': [
                [-50.0, -30.0],
                [50.0, -30.0],
                [50.0, 30.0],
                [-50.0, 30.0],
            ],
            'height': 10.0,
        }],
    }

    result = compute_snapshot_orientation(geometry, assembly=False)
    payload = orientation_result_to_dict(result)

    assert len(payload['bbx']) == 3
    assert len(payload['bbx_origin']) == 3
    assert set(payload['pca_frame']) == {'o', 'x', 'y', 'z'}
    assert payload['bbx'][0] == 100.0
    assert payload['bbx'][1] == 60.0
    assert payload['bbx'][2] == 10.0


def _box_corner_points(hx: float, hy: float, hz: float):
    return [
        [x, y, z]
        for x in (-hx, hx)
        for y in (-hy, hy)
        for z in (-hz, hz)
    ]


def test_point_cloud_orientation_uses_3d_pca():
    geometry = {
        'point_clouds': [{
            'points': _box_corner_points(50.0, 30.0, 5.0),
        }],
    }

    result = compute_snapshot_orientation(geometry, assembly=False)
    payload = orientation_result_to_dict(result)

    assert set(payload['pca_frame']) == {'o', 'x', 'y', 'z'}
    dims = sorted(payload['bbx'], reverse=True)
    assert dims[0] == 100.0
    assert dims[1] == 60.0
    assert dims[2] == 10.0


def test_point_cloud_assembly_uses_all_clouds():
    geometry = {
        'point_clouds': [
            {'points': _box_corner_points(10.0, 10.0, 10.0)},
            {'points': [[100.0, 0.0, 0.0], [110.0, 0.0, 0.0],
                        [100.0, 10.0, 0.0], [100.0, 0.0, 10.0]]},
        ],
    }

    first_only = compute_snapshot_orientation(geometry, assembly=False)
    combined = compute_snapshot_orientation(geometry, assembly=True)

    assert max(combined.bbx) > max(first_only.bbx)


def test_meshes_take_precedence_over_point_clouds():
    geometry = {
        'meshes': [{
            'vertices': _box_corner_points(50.0, 30.0, 5.0),
            'faces': [
                [0, 1, 2], [0, 2, 3],
                [4, 5, 6], [4, 6, 7],
            ],
        }],
        'point_clouds': [{
            'points': _box_corner_points(5.0, 5.0, 5.0),
        }],
    }

    result = compute_snapshot_orientation(geometry, assembly=False)
    dims = sorted(result.bbx, reverse=True)
    assert dims[0] == 100.0
    assert dims[1] == 60.0
    assert dims[2] == 10.0


def test_unsupported_geometry_raises():
    with pytest.raises(ValueError, match='point_clouds'):
        compute_snapshot_orientation({'marker_points': [[0.0, 0.0, 0.0]]})
