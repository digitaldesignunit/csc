"""Tests for snapshot orientation computation."""

from __future__ import annotations

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
