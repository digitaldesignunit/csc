"""Tests for descriptor-based component map embeddings."""

import numpy as np
import pytest

from apps.catalog.component_map import (
    build_component_map,
    extract_radial_feature,
    extract_scalar_feature,
)
from apps.descriptors import radial_signature as rs


def _radial_descriptors() -> dict:
    out = {}
    for n in rs.SUPPORTED_RESOLUTIONS:
        out[rs.radial_distance_key(n)] = [float(i + 1) for i in range(n)]
        out[rs.radial_tangent_key(n)] = [[1.0, 0.0] for _ in range(n)]
    return out


def test_extract_radial_requires_all_resolutions():
    descriptors = _radial_descriptors()
    vec = extract_radial_feature(descriptors)
    assert vec is not None
    assert vec.shape == (sum(rs.SUPPORTED_RESOLUTIONS),)

    del descriptors[rs.radial_distance_key(64)]
    assert extract_radial_feature(descriptors) is None


def test_extract_radial_requires_tangents_present():
    descriptors = _radial_descriptors()
    del descriptors[rs.radial_tangent_key(32)]
    assert extract_radial_feature(descriptors) is None


def test_extract_scalar_requires_all_scores():
    descriptors = {
        'boxscore': 0.1,
        'spherescore': 0.2,
        'linescore': 0.3,
        'planescore': 0.4,
    }
    vec = extract_scalar_feature(descriptors)
    assert vec is not None
    np.testing.assert_allclose(vec, [0.1, 0.2, 0.3, 0.4])

    del descriptors['linescore']
    assert extract_scalar_feature(descriptors) is None


def test_build_component_map_omits_missing_and_reports_coverage():
    rows = [
        {
            '_id': 'a',
            'name': 'With radial',
            'type': 'panel',
            'catalog_number': 1,
            'descriptors': _radial_descriptors(),
        },
        {
            '_id': 'b',
            'name': 'Missing radial',
            'type': 'beam',
            'catalog_number': 2,
            'descriptors': {'boxscore': 0.5},
        },
        {
            '_id': 'c',
            'name': 'Also radial',
            'type': 'panel',
            'catalog_number': 3,
            'descriptors': _radial_descriptors(),
        },
        {
            '_id': 'd',
            'name': 'Also radial shifted',
            'type': 'panel',
            'catalog_number': 4,
            'descriptors': {
                **_radial_descriptors(),
                rs.radial_distance_key(16): [
                    float(i + 10) for i in range(16)
                ],
            },
        },
    ]

    payload = build_component_map(rows, basis='radial_signature', method='pca')
    assert payload['total'] == 4
    assert payload['displayed'] == 3
    assert payload['basis_label'] == 'radial signature'
    assert payload['method'] == 'pca'
    assert {p['id'] for p in payload['points']} == {'a', 'c', 'd'}
    for point in payload['points']:
        assert isinstance(point['x'], float)
        assert isinstance(point['y'], float)


def test_build_component_map_scalars_basis():
    rows = [
        {
            '_id': 'a',
            'descriptors': {
                'boxscore': 1.0,
                'spherescore': 0.0,
                'linescore': 0.0,
                'planescore': 0.0,
            },
        },
        {
            '_id': 'b',
            'descriptors': {
                'boxscore': 0.0,
                'spherescore': 1.0,
                'linescore': 0.0,
                'planescore': 0.0,
            },
        },
        {
            '_id': 'c',
            'descriptors': {
                'boxscore': 0.0,
                'spherescore': 0.0,
                'linescore': 1.0,
                'planescore': 0.0,
            },
        },
        {
            '_id': 'skip',
            'descriptors': {'boxscore': 1.0},
        },
    ]
    payload = build_component_map(rows, basis='scalars', method='pca')
    assert payload['total'] == 4
    assert payload['displayed'] == 3
    assert payload['basis_label'] == 'scalar descriptors'
    assert len(payload['points']) == 3


def test_umap_falls_back_to_pca_for_tiny_sets():
    rows = [
        {
            '_id': 'a',
            'descriptors': {
                'boxscore': 1.0,
                'spherescore': 0.0,
                'linescore': 0.0,
                'planescore': 0.0,
            },
        },
        {
            '_id': 'b',
            'descriptors': {
                'boxscore': 0.0,
                'spherescore': 1.0,
                'linescore': 0.0,
                'planescore': 0.0,
            },
        },
    ]
    payload = build_component_map(rows, basis='scalars', method='umap')
    assert payload['requested_method'] == 'umap'
    assert payload['method'] == 'pca'
    assert payload['displayed'] == 2


def test_umap_embedding_when_available():
    umap = pytest.importorskip('umap')
    assert umap is not None
    rows = []
    for i in range(12):
        rows.append({
            '_id': f'id-{i}',
            'descriptors': {
                'boxscore': float(i),
                'spherescore': float(i % 3),
                'linescore': float((i * 2) % 5),
                'planescore': float((i * 3) % 7),
            },
        })
    payload = build_component_map(rows, basis='scalars', method='umap')
    assert payload['method'] == 'umap'
    assert payload['displayed'] == 12
    assert len(payload['points']) == 12
