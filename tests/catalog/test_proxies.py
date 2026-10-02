"""Stage 3: proxy fitting, residuals, deviation maps (spec 4.3, App. B)."""

from __future__ import annotations

import numpy as np
import pytest
import trimesh

from apps.catalog.documents import Proxy
from apps.catalog.frame import compute_frame
from apps.catalog.geometry_source import Source
from apps.catalog.proxies.fit import fit_primary
from apps.catalog.proxies.png16 import decode_rgb16, encode_rgb16
from apps.catalog.proxies.primitives import (
    local_mesh,
    prism_mesh,
    proxy_mesh,
    to_local,
    to_stored,
)
from apps.catalog.proxies.robust import ransac_circle


def run(mesh, shape_class):
    source = Source('meshes', 'preview', meshes=[mesh])
    result = compute_frame(source.points())
    return fit_primary(source, result.frame, result.bbx, shape_class,
                       'sid', 0, '2026-10-02T00:00:00Z')


def test_png16_roundtrip():
    rng = np.random.default_rng(1)
    image = rng.integers(0, 65536, size=(7, 11, 3)).astype(np.uint16)
    assert np.array_equal(decode_rgb16(encode_rgb16(image)), image)


def test_ransac_finds_a_circle_among_outliers():
    theta = np.linspace(0, 2 * np.pi, 400, endpoint=False)
    ring = np.column_stack([30 + 12 * np.cos(theta), -5 + 12 * np.sin(theta)])
    noise = np.random.default_rng(3).uniform(-20, 40, size=(60, 2))
    points = np.vstack([ring, noise])
    fit = ransac_circle(points, tolerance=0.3)
    assert fit.radius == pytest.approx(12, abs=0.1)
    assert fit.centre == pytest.approx((30, -5), abs=0.1)
    assert fit.inlier_ratio > 0.85
    assert ransac_circle(points, tolerance=0.3) == fit          # seeded


def test_placement_roundtrip():
    placement = {'o': [10, 20, 30], 'x': [0, 1, 0], 'y': [0, 0, 1],
                 'z': [1, 0, 0]}
    points = np.random.default_rng(0).normal(size=(5, 3))
    assert np.allclose(to_stored(to_local(points, placement), placement),
                       points)


def test_prism_mesh_with_concave_profile_is_watertight():
    profile = [[0, 0], [100, 0], [100, 100], [60, 100], [60, 40], [0, 40]]
    mesh = prism_mesh(profile, None, 20)
    assert mesh.is_watertight
    assert mesh.volume == pytest.approx((100 * 40 + 40 * 60) * 20, rel=1e-6)


def test_prism_mesh_with_a_hole():
    outer = [[-50, -50], [50, -50], [50, 50], [-50, 50]]
    hole = [[-10, -10], [10, -10], [10, 10], [-10, 10]]
    mesh = prism_mesh(outer, [hole], 10)
    assert mesh.volume == pytest.approx((100 * 100 - 20 * 20) * 10, rel=1e-6)


def test_block_gets_a_box_with_obb_fit_and_tiny_residuals():
    doc, files = run(trimesh.creation.box(extents=(300, 200, 150)), 'block')
    assert doc['primitive'] == 'box' and doc['fit']['method'] == 'obb'
    assert doc['params']['size'] == pytest.approx([300, 200, 150])
    assert doc['fit']['p95_mm'] < 1e-6
    assert set(doc['deviation_maps']['faces']) == {'+x', '-x', '+y', '-y',
                                                   '+z', '-z'}
    assert len(files) == 6
    Proxy.model_validate(doc)


def test_linear_round_bar_gets_a_cylinder_with_ransac():
    mesh = trimesh.creation.cylinder(radius=40, height=1200, sections=64)
    doc, _ = run(mesh, 'linear')
    assert doc['primitive'] == 'cylinder' and doc['fit']['method'] == 'ransac'
    assert doc['params']['radius'] == pytest.approx(40, rel=0.02)
    assert doc['params']['height'] == pytest.approx(1200, rel=1e-6)
    assert doc['fit']['inlier_ratio'] >= 0.9
    assert set(doc['deviation_maps']['faces']) == {'top', 'bottom', 'lateral'}
    Proxy.model_validate(doc)


def test_linear_t_beam_gets_a_prism_from_the_section():
    profile = [[-60, 0], [60, 0], [60, 20], [10, 20], [10, 120],
               [-10, 120], [-10, 20], [-60, 20]]
    doc, _ = run(prism_mesh(profile, None, 2000), 'linear')
    assert doc['primitive'] == 'prism'
    assert doc['params']['height'] == pytest.approx(2000, rel=1e-6)
    assert doc['fit']['p95_mm'] < 3.0
    assert 6 <= len(doc['params']['profile']) <= 12
    Proxy.model_validate(doc)


def test_planar_notched_plate_gets_a_prism():
    profile = [[0, 0], [600, 0], [600, 400], [300, 400], [300, 200],
               [0, 200]]
    doc, _ = run(prism_mesh(profile, None, 18), 'planar')
    assert doc['primitive'] == 'prism'
    assert doc['params']['height'] == pytest.approx(18, abs=1e-6)
    assert doc['fit']['p95_mm'] < 3.0
    assert 'top' in doc['deviation_maps']['faces']
    sides = [f for f in doc['deviation_maps']['faces']
             if f.startswith('side')]
    assert len(sides) == len(doc['params']['profile'])
    Proxy.model_validate(doc)


def test_irregular_piece_gets_a_hull_with_a_spherical_map():
    rng = np.random.default_rng(5)
    mesh = trimesh.creation.icosphere(subdivisions=3, radius=100)
    mesh.vertices *= rng.uniform(0.7, 1.0, size=(len(mesh.vertices), 1))
    doc, _ = run(mesh, 'irregular')
    assert doc['primitive'] == 'hull' and doc['fit']['method'] == 'hull'
    assert list(doc['deviation_maps']['faces']) == ['sphere']
    assert doc['deviation_maps']['faces']['sphere']['width'] == 128
    assert doc['fit']['max_mm'] > 0
    Proxy.model_validate(doc)


def test_deviation_map_files_decode_with_the_documented_size():
    doc, files = run(trimesh.creation.box(extents=(400, 200, 100)), 'block')
    face = doc['deviation_maps']['faces']['+z']
    image = decode_rgb16(files[face['file']])
    assert image.shape == (face['height'], face['width'], 3)
    assert image[:, :, 2].sum() > 0                          # occupancy


def test_fit_is_deterministic():
    mesh = trimesh.creation.cylinder(radius=40, height=800, sections=48)
    a, files_a = run(mesh, 'linear')
    b, files_b = run(mesh, 'linear')
    assert a == b and files_a == files_b


def test_authored_proxy_mesh_in_stored_coordinates():
    proxy = {'primitive': 'box', 'params': {'size': [10, 20, 30]},
             'placement': {'o': [100, 0, 0], 'x': [1, 0, 0],
                           'y': [0, 1, 0], 'z': [0, 0, 1]}}
    mesh = proxy_mesh(proxy)
    assert mesh.bounds[0] == pytest.approx([95, -10, -15])
    assert local_mesh('cylinder', {'radius': 5, 'height': 10}).is_watertight
