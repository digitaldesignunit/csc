"""Validation tests for snapshot geometry models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.catalog.models import SnapshotGeometry, SnapshotReinforcement


def _minimal_extrusion_geometry() -> dict:
    return {
        'extrusions': [{
            'profile': [[0, 0], [100, 0], [100, 50]],
            'height': 10,
        }],
    }


def test_reinforcement_valid_object():
    bar = SnapshotReinforcement(
        spec='B500B',
        diameter=12.0,
        points=[[0, 0, 0], [2400, 0, 0]],
    )
    assert bar.spec == 'B500B'
    assert bar.diameter == 12.0
    assert len(bar.points) == 2


def test_reinforcement_strips_spec():
    bar = SnapshotReinforcement(
        spec='  B500B  ',
        diameter=8.0,
        points=[[0, 0, 0], [1, 0, 0]],
    )
    assert bar.spec == 'B500B'


def test_reinforcement_rejects_empty_spec():
    with pytest.raises(ValidationError):
        SnapshotReinforcement(
            spec='   ',
            diameter=12.0,
            points=[[0, 0, 0], [1, 0, 0]],
        )


def test_reinforcement_rejects_non_positive_diameter():
    with pytest.raises(ValidationError):
        SnapshotReinforcement(
            spec='B500B',
            diameter=0,
            points=[[0, 0, 0], [1, 0, 0]],
        )


def test_reinforcement_requires_at_least_two_points():
    with pytest.raises(ValidationError):
        SnapshotReinforcement(
            spec='B500B',
            diameter=12.0,
            points=[[0, 0, 0]],
        )


def test_reinforcement_rejects_malformed_points():
    with pytest.raises(ValidationError):
        SnapshotReinforcement(
            spec='B500B',
            diameter=12.0,
            points=[[0, 0], [1, 0, 0]],
        )


def test_geometry_accepts_mesh_with_reinforcements():
    geometry = SnapshotGeometry(
        meshes=[{
            'vertices': [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            'faces': [[0, 1, 2]],
        }],
        reinforcements=[{
            'spec': 'B500B',
            'diameter': 12.0,
            'points': [[0, 0, 0], [100, 0, 0]],
        }],
    )
    assert geometry.reinforcements is not None
    assert len(geometry.reinforcements) == 1


def test_geometry_rejects_reinforcements_only():
    with pytest.raises(ValidationError, match='geometry must include'):
        SnapshotGeometry(
            reinforcements=[{
                'spec': 'B500B',
                'diameter': 12.0,
                'points': [[0, 0, 0], [100, 0, 0]],
            }],
        )


def test_geometry_accepts_extrusion_with_multiple_reinforcements():
    geometry = SnapshotGeometry(
        **_minimal_extrusion_geometry(),
        reinforcements=[
            {
                'spec': 'B500B',
                'diameter': 12.0,
                'points': [[0, 0, 0], [100, 0, 0]],
            },
            {
                'spec': 'B500A',
                'diameter': 8.0,
                'points': [[0, 0, 5], [0, 50, 5], [0, 50, -5]],
            },
        ],
    )
    assert len(geometry.reinforcements or []) == 2
