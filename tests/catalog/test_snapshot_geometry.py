"""Validation tests for snapshot geometry models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.catalog.documents import Geometry
from apps.catalog.models import SnapshotGeometry


def _minimal_extrusion_geometry() -> dict:
    return {
        'extrusions': [{
            'profile': [[0, 0], [100, 0], [100, 50]],
            'height': 10,
        }],
    }


def _bar() -> dict:
    return {'spec': 'B500B', 'diameter': 12.0,
            'points': [[0, 0, 0], [100, 0, 0]]}


def test_geometry_accepts_extrusion():
    geometry = SnapshotGeometry(**_minimal_extrusion_geometry())
    assert len(geometry.extrusions) == 1


def test_geometry_accepts_mesh_with_marker_points():
    geometry = SnapshotGeometry(
        meshes=[{
            'vertices': [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            'faces': [[0, 1, 2]],
        }],
        marker_points=[[0, 0, 0]],
    )
    assert geometry.marker_points == [[0, 0, 0]]


def test_geometry_rejects_marker_points_only():
    with pytest.raises(ValidationError, match='geometry must include'):
        SnapshotGeometry(marker_points=[[0, 0, 0]])


@pytest.mark.parametrize('extra', [
    {},
    _minimal_extrusion_geometry(),
])
def test_geometry_rejects_reinforcements(extra):
    """Reinforcement is evidence (decision 7.8): the error says where it
    belongs, whether or not the geometry has a representation."""
    with pytest.raises(ValidationError) as caught:
        SnapshotGeometry(**extra, reinforcements=[_bar()])
    message = str(caught.value)
    assert 'geometry.reinforcements is not accepted' in message
    assert 'reinforcement_layout' in message
    assert '7.8' in message


def test_geometry_rejects_empty_reinforcements_key():
    """Even an empty list or null says the client still sends the old key."""
    for value in ([], None):
        with pytest.raises(ValidationError, match='reinforcement_layout'):
            SnapshotGeometry(**_minimal_extrusion_geometry(),
                             reinforcements=value)


def test_the_stored_geometry_block_gives_the_same_answer():
    """The block every write goes through (``documents.Geometry``) names the
    evidence record too, not just "extra inputs are not permitted"."""
    mesh = {'vertices': [[0, 0, 0], [1, 0, 0], [0, 1, 0]], 'faces': [[0, 1, 2]]}
    assert Geometry(meshes=[mesh]).meshes
    with pytest.raises(ValidationError) as caught:
        Geometry(meshes=[mesh], reinforcements=[_bar()])
    assert 'reinforcement_layout' in str(caught.value) and '7.8' in str(caught.value)
