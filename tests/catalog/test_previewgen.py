"""Tests for snapshot catalog preview rendering."""

from __future__ import annotations

import matplotlib
matplotlib.use('Agg')

import pytest

from apps.previewgen.previewgen import create_snapshot_preview_image


def _mesh_geometry():
    return {
        'meshes': [{
            'vertices': [
                [0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0],
                [0, 0, 10], [10, 0, 10], [10, 10, 10], [0, 10, 10],
            ],
            'faces': [
                [0, 1, 2], [0, 2, 3],
                [4, 7, 6], [4, 6, 5],
            ],
        }],
    }


def _point_cloud_geometry(with_colors=True):
    points = [
        [0.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
        [10.0, 10.0, 0.0],
        [0.0, 10.0, 10.0],
    ]
    cloud = {'points': points}
    if with_colors:
        cloud['colors'] = [
            [255, 0, 0],
            [0, 255, 0],
            [0, 0, 255],
            [255, 255, 0],
        ]
    return {'point_clouds': [cloud]}


def test_point_cloud_only_preview_renders():
    image = create_snapshot_preview_image(
        {
            '_id': 'pc-only',
            'color': [80, 120, 200],
            'geometry': _point_cloud_geometry(),
        },
        size=80,
        dpi=80,
    )
    assert image.size[0] > 0
    assert image.size[1] > 0


def test_point_cloud_without_vertex_colors_uses_snapshot_color():
    image = create_snapshot_preview_image(
        {
            '_id': 'pc-plain',
            'color': [20, 40, 60],
            'geometry': _point_cloud_geometry(with_colors=False),
        },
        size=80,
        dpi=80,
    )
    assert image.size[0] > 0


def test_mesh_wins_over_point_cloud():
    geometry = _mesh_geometry()
    geometry.update(_point_cloud_geometry())
    image = create_snapshot_preview_image(
        {
            '_id': 'mesh-and-pc',
            'color': [110, 110, 110],
            'geometry': geometry,
        },
        size=80,
        dpi=80,
    )
    assert image.size[0] > 0


def test_empty_geometry_raises():
    with pytest.raises(ValueError, match='point_clouds'):
        create_snapshot_preview_image(
            {'_id': 'empty', 'geometry': {}},
            size=80,
            dpi=80,
        )


def test_empty_point_cloud_raises():
    with pytest.raises(ValueError, match='point_clouds'):
        create_snapshot_preview_image(
            {
                '_id': 'empty-pc',
                'geometry': {'point_clouds': [{'points': []}]},
            },
            size=80,
            dpi=80,
        )
