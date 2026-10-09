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


# FACE ASSIGNMENT BY SURFACE NORMAL (decision 8.119) ---------------------------
def _beam_with_recessed_underside(recess=120.0, consistent=False):
    """3000 x 300 x 200 mm beam (x length, y height, z width) whose
    underside is recessed between x = 1000 and 2000. ``prism_mesh`` winds
    its caps against its sides; ``consistent`` repairs that."""
    profile = [[0, 0], [1000, 0], [1000, recess], [2000, recess], [2000, 0],
               [3000, 0], [3000, 300], [0, 300]]
    mesh = prism_mesh(profile, None, 200)
    if consistent:
        mesh.fix_normals()
        assert mesh.is_winding_consistent and mesh.volume > 0
    mesh.apply_translation(-mesh.bounds.mean(axis=0))
    return mesh


def test_a_recessed_underside_lands_on_its_own_face_not_the_sides():
    from apps.catalog.proxies.sampling import sample_surface
    from apps.catalog.proxies.specs import BOX
    mesh = _beam_with_recessed_underside()
    sample = sample_surface(Source('meshes', 'preview', meshes=[mesh]), 50_000)
    params = {'size': [3000.0, 300.0, 200.0]}
    ceiling = (np.abs(sample.points[:, 1] + 30.0) < 1e-6) & (
        np.abs(sample.points[:, 0]) < 400)             # the recess, x in 1000..2000
    assert ceiling.sum() > 1000
    unwrap = BOX.unwrap(params, sample.points, sample.normals)
    minus_y = list(('+x', '-x', '+y', '-y', '+z', '-z')).index('-y')
    assert (unwrap.face[ceiling] == minus_y).mean() >= 0.9
    # the nearest plane alone sent most of it to the sides
    nearest = BOX.unwrap(params, sample.points)
    assert (nearest.face[ceiling] == minus_y).mean() < 0.9


def test_normals_pointing_inward_are_turned_around_before_assigning():
    from apps.catalog.proxies.sampling import sample_surface
    from apps.catalog.proxies.specs import BOX
    mesh = _beam_with_recessed_underside()
    sample = sample_surface(Source('meshes', 'preview', meshes=[mesh]), 20_000)
    params = {'size': [3000.0, 300.0, 200.0]}
    out = BOX.unwrap(params, sample.points, sample.normals).face
    inward = BOX.unwrap(params, sample.points, -sample.normals).face
    assert np.array_equal(out, inward)


def test_a_point_without_a_usable_normal_goes_to_the_nearest_plane():
    from apps.catalog.proxies.specs import BOX, PRISM
    params = {'size': [100.0, 100.0, 100.0]}
    points = np.array([[49.0, 0.0, 0.0], [0.0, -48.0, 0.0], [0.0, 0.0, 47.0]])
    zero = np.zeros_like(points)
    assert list(BOX.unwrap(params, points, zero).face) == [0, 3, 4]
    prism = {'profile': [[-50, -50], [50, -50], [50, 50], [-50, 50]],
             'height': 100.0}
    face = PRISM.unwrap(prism, points, zero).face
    assert face[2] == 0                                    # top
    assert PRISM.unwrap(prism, points).face.tolist() == face.tolist()


def test_prism_sides_and_caps_are_assigned_by_normal_too():
    from apps.catalog.proxies.sampling import sample_surface
    from apps.catalog.proxies.specs import PRISM
    profile = [[-150, -100], [150, -100], [150, 100], [-150, 100]]
    mesh = prism_mesh(profile, None, 60)
    mesh.apply_translation(-mesh.bounds.mean(axis=0))
    sample = sample_surface(Source('meshes', 'preview', meshes=[mesh]), 20_000)
    unwrap = PRISM.unwrap({'profile': profile, 'height': 60.0}, sample.points,
                          sample.normals)
    flat = np.abs(sample.normals[:, 2]) > 0.99           # whichever way they point
    top = flat & (sample.points[:, 2] > 0)
    bottom = flat & (sample.points[:, 2] < 0)
    assert (unwrap.face[top] == 0).all() and (unwrap.face[bottom] == 1).all()
    sides = ~(top | bottom)
    assert (unwrap.face[sides] >= 2).all()


def test_the_surface_sample_follows_the_deviation_map_cells():
    from apps.catalog.proxies.fit import (
        RESIDUAL_SAMPLE_MAX,
        RESIDUAL_SAMPLE_MIN,
        residual_sample_size,
    )
    small = Source('meshes', 'preview',
                   meshes=[trimesh.creation.box(extents=(300, 200, 150))])
    assert residual_sample_size(small, (300, 200, 150)) == RESIDUAL_SAMPLE_MIN
    # a beam of about 12 m^2 at 11 mm cells: about 3 points per cell
    beam = Source('meshes', 'preview',
                  meshes=[trimesh.creation.box(extents=(4400, 300, 300))])
    size = residual_sample_size(beam, (4400, 300, 300))
    cell = (4400 / 400.0) ** 2
    assert size == pytest.approx(3 * 2 * (4400 * 300 * 2 + 300 * 300) / cell,
                                 abs=2)
    assert RESIDUAL_SAMPLE_MIN < size <= RESIDUAL_SAMPLE_MAX
    huge = Source('meshes', 'preview',
                  meshes=[trimesh.creation.box(extents=(20000, 3000, 3000))])
    assert residual_sample_size(huge, (20000, 3000, 3000)) == RESIDUAL_SAMPLE_MAX
    cloud = Source('point_clouds', 'preview', clouds=[np.zeros((10, 3))])
    assert residual_sample_size(cloud, (300, 200, 150)) == RESIDUAL_SAMPLE_MIN


def test_a_recess_deeper_than_the_half_height_needs_the_normal_side():
    """The ceiling of a 200 mm recess lies above the beam's middle: the
    nearest plane is the top one. Consistent normals still say it faces down;
    with mixed winding no side is trusted and the nearest of the two opposite
    faces wins (the documented limit)."""
    from apps.catalog.proxies.sampling import sample_surface
    from apps.catalog.proxies.specs import BOX
    params = {'size': [3000.0, 300.0, 200.0]}
    minus_y = ('+x', '-x', '+y', '-y', '+z', '-z').index('-y')
    mesh = _beam_with_recessed_underside(recess=200.0, consistent=True)
    sample = sample_surface(Source('meshes', 'preview', meshes=[mesh]), 50_000)
    ceiling = (np.abs(sample.points[:, 1] - 50.0) < 1e-6) & (
        np.abs(sample.points[:, 0]) < 400)
    assert ceiling.sum() > 1000
    face = BOX.unwrap(params, sample.points, sample.normals).face
    assert (face[ceiling] == minus_y).mean() >= 0.9
    # the same with the normals turned around
    face = BOX.unwrap(params, sample.points, -sample.normals).face
    assert (face[ceiling] == minus_y).mean() >= 0.9


# DISTANCE TO THE ASSIGNED FACE, THE OUTLINE CAP (decision 8.121) ---------------
def test_a_recess_shows_its_full_depth_on_its_own_face():
    from apps.catalog.proxies.deviation import build_deviation_maps
    from apps.catalog.proxies.sampling import sample_surface
    from apps.catalog.proxies.specs import BOX
    mesh = _beam_with_recessed_underside(recess=120.0, consistent=True)
    sample = sample_surface(Source('meshes', 'preview', meshes=[mesh]), 100_000)
    params = {'size': [3000.0, 300.0, 200.0]}
    ceiling = (np.abs(sample.points[:, 1] + 30.0) < 1e-6) & (
        np.abs(sample.points[:, 0]) < 400)
    unwrap = BOX.unwrap(params, sample.points, sample.normals)
    assert (unwrap.distance[ceiling] == pytest.approx(-120.0, abs=1e-6))
    # the nearest-plane distance understates it where a side plane is closer
    assert np.abs(BOX.sdf(params, sample.points)[ceiling]).max() < 120.0
    # and the stored map of that face holds -120 in the recess
    doc, files = build_deviation_maps(
        BOX, params, sample.points, sample.normals,
        BOX.sdf(params, sample.points), 30.0, 'p/sid/0')
    face = doc['faces']['-y']
    image = decode_rgb16(files[face['file']])
    scale, offset = face['distance']['scale_mm'], face['distance']['offset_mm']
    occupied = image[:, :, 2] > 0
    depth = image[:, :, 0].astype(float) * scale + offset
    middle = occupied[:, image.shape[1] // 2 - 3:image.shape[1] // 2 + 3]
    assert depth[:, image.shape[1] // 2 - 3:image.shape[1] // 2 + 3][middle].mean() \
        == pytest.approx(-120.0, abs=1.0)
    assert depth[occupied].max() == pytest.approx(0.0, abs=1.0)    # the rim


def test_the_distance_is_to_the_assigned_face_of_every_primitive():
    from apps.catalog.proxies.specs import BOX, CYLINDER, PRISM
    box = BOX.unwrap({'size': [100.0, 100.0, 100.0]},
                     np.array([[40.0, 0.0, 0.0], [0.0, -45.0, 0.0]]),
                     np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0]]))
    assert box.distance == pytest.approx([-10.0, -5.0])
    prism_params = {'profile': [[-50, -50], [50, -50], [50, 50], [-50, 50]],
                    'height': 100.0}
    prism = PRISM.unwrap(prism_params,
                         np.array([[0.0, -40.0, 0.0], [0.0, 0.0, 45.0],
                                   [0.0, 0.0, -48.0], [60.0, 0.0, 0.0]]),
                         np.array([[0.0, -1.0, 0.0], [0.0, 0.0, 1.0],
                                   [0.0, 0.0, -1.0], [1.0, 0.0, 0.0]]))
    assert prism.distance == pytest.approx([-10.0, -5.0, -2.0, 10.0])
    cylinder = CYLINDER.unwrap({'radius': 50.0, 'height': 100.0},
                               np.array([[30.0, 0.0, 0.0], [0.0, 0.0, 48.0],
                                         [0.0, 0.0, -49.0], [55.0, 0.0, 0.0]]))
    assert cylinder.distance == pytest.approx([-20.0, -2.0, -1.0, 5.0])


def test_the_residual_figures_stay_the_distance_to_the_nearest_surface():
    from apps.catalog.proxies.fit import residual_sample_size
    from apps.catalog.proxies.sampling import sample_surface
    from apps.catalog.proxies.specs import BOX
    mesh = _beam_with_recessed_underside(recess=120.0, consistent=True)
    source = Source('meshes', 'preview', meshes=[mesh])
    result = compute_frame(source.points())
    doc, _ = fit_primary(source, result.frame, result.bbx, 'block', 'sid', 0,
                         '2026-10-07T00:00:00Z')
    sample = sample_surface(source, residual_sample_size(source, result.bbx))
    placement = doc['placement']
    local = to_local(sample.points, placement)
    absolute = np.abs(BOX.sdf(doc['params'], local))
    assert doc['fit']['p95_mm'] == pytest.approx(np.percentile(absolute, 95))
    assert doc['fit']['max_mm'] == pytest.approx(absolute.max())
    assert doc['fit']['rms_mm'] == pytest.approx(np.sqrt(np.mean(absolute ** 2)))


def test_the_planar_outline_is_fitted_from_at_most_50000_points(monkeypatch):
    from apps.catalog.proxies import specs
    from apps.catalog.proxies.specs import OUTLINE_INPUT_MAX
    seen = []
    original = specs._outline
    monkeypatch.setattr(specs, '_outline', lambda xy, extent: (
        seen.append(len(xy)), original(xy, extent))[1])
    profile = [[0, 0], [1200, 0], [1200, 700], [1800, 700], [1800, 0],
               [4340, 0], [4340, 2410], [0, 2410]]
    mesh = prism_mesh(profile, None, 200)
    mesh.apply_translation(-mesh.bounds.mean(axis=0))
    doc, _ = run(mesh, 'planar')
    assert doc['primitive'] == 'prism'
    assert doc['fit']['n_points'] > 0
    assert seen and max(seen) <= OUTLINE_INPUT_MAX
    assert OUTLINE_INPUT_MAX == 50_000


# THE OUTLINE NEVER HANGS (8.127) -------------------------------------------------
def test_thin_keeps_one_point_per_cell_even_for_a_small_set():
    from apps.catalog.proxies.specs import _thin
    xy = np.array([[0.1, 0.1], [0.4, 0.3], [0.9, 0.2], [5.2, 5.1], [5.6, 5.9]])
    assert len(_thin(xy, 1.0)) == 2


def test_simplify_gives_up_where_the_topology_keeps_too_many_vertices():
    """A fine zigzag cannot be simplified without crossing itself: no
    tolerance up to the cap reaches the vertex limit, and it must not loop
    on towards a tolerance of many extents (8.127)."""
    from shapely.geometry import LineString
    from apps.catalog.proxies.specs import (
        OUTLINE_MAX_VERTICES, _outline, _simplify)
    zigzag = LineString([(1.6 * i, 1000.0 * (i % 2)) for i in range(600)])
    polygon = zigzag.buffer(0.3, cap_style='flat', join_style='mitre')
    assert len(polygon.exterior.coords) > OUTLINE_MAX_VERTICES
    assert _simplify(polygon, 1000.0) is None
    # a simple outline is simplified as before
    square = LineString([(0, 0), (1000, 0), (1000, 800), (0, 800), (0, 0)])
    simple = _simplify(square.buffer(1.0), 1000.0)
    assert simple is not None and len(simple.exterior.coords) <= OUTLINE_MAX_VERTICES


def test_a_smooth_planar_wall_is_fitted_in_seconds():
    """The IFC wall of the demo instance (a box of 8 vertices, 6850 x 1310 x
    120): its concave hull of random points is jagged and the simplification
    stalled above the vertex limit for ever. It is a prism with a clean
    outline or the box, never a hang."""
    import time
    from apps.catalog.proxies.specs import OUTLINE_MAX_VERTICES
    wall = trimesh.creation.box(extents=(6850.0, 1310.0, 120.0))
    started = time.time()
    doc, _ = run(wall, 'planar')
    assert time.time() - started < 60
    assert doc['primitive'] in ('box', 'prism')
    if doc['primitive'] == 'prism':
        assert len(doc['params']['profile']) <= OUTLINE_MAX_VERTICES


def test_a_planar_piece_whose_outline_cannot_be_simplified_keeps_the_box(
        monkeypatch):
    from apps.catalog.proxies import specs
    monkeypatch.setattr(specs, '_simplify', lambda polygon, extent: None)
    wall = trimesh.creation.box(extents=(2000.0, 900.0, 100.0))
    doc, _ = run(wall, 'planar')
    assert doc['primitive'] == 'box'


# PLANAR PRISM ACCEPTANCE (decision 8.121 d) ------------------------------------
def _slab(profile, thickness=200.0):
    mesh = prism_mesh(profile, None, thickness)
    mesh.apply_translation(-mesh.bounds.mean(axis=0))
    return mesh


def test_a_plain_wall_gets_the_box_not_a_ragged_prism():
    wall = _slab([[0, 0], [4340, 0], [4340, 2410], [0, 2410]])
    doc, files = run(wall, 'planar')
    assert doc['primitive'] == 'box' and doc['fit']['method'] == 'obb'
    assert doc['fit']['p95_mm'] < 1.0
    assert len(files) == 6
    Proxy.model_validate(doc)


def test_a_notched_wall_keeps_its_prism():
    wall = _slab([[0, 0], [1200, 0], [1200, 700], [1800, 700], [1800, 0],
                  [4340, 0], [4340, 2410], [3300, 2410], [3300, 1700],
                  [2600, 1700], [2600, 2410], [0, 2410]])
    doc, _ = run(wall, 'planar')
    assert doc['primitive'] == 'prism'
    assert doc['fit']['p95_mm'] < 0.006 * 200.0 * 2          # 0.5 - 1.1 mm measured


def test_a_planar_piece_the_prism_describes_better_than_the_box_keeps_it():
    l_plate = _slab([[0, 0], [1000, 0], [1000, 300], [300, 300], [300, 1000],
                     [0, 1000]], thickness=50.0)
    doc, _ = run(l_plate, 'planar')
    assert doc['primitive'] == 'prism'


def test_the_planar_prism_is_accepted_within_a_thickness_and_beating_the_box():
    from apps.catalog.proxies.fit import (
        PRISM_PLANAR_TOLERANCE,
        Residuals,
        _accept,
    )

    def stats(p95, rms=None):
        rms = p95 if rms is None else rms
        return Residuals(n=1, rms=rms, p95=p95, maximum=p95, inlier_ratio=1.0)
    bbx = (4000.0, 2000.0, 100.0)
    assert PRISM_PLANAR_TOLERANCE == 1.0
    assert _accept('prism', 'planar', stats(99.0), bbx)               # no box to beat
    assert not _accept('prism', 'planar', stats(101.0), bbx)          # off by over a thickness
    assert _accept('prism', 'planar', stats(20.0), bbx, lambda: stats(30.0))
    assert _accept('prism', 'planar', stats(30.0), bbx, lambda: stats(30.0))
    assert not _accept('prism', 'planar', stats(31.0), bbx, lambda: stats(30.0))
    # a notch is a few per cent of the surface: the box ties the p95 at 0,
    # the rms tells the prism that follows the notch from the box
    assert _accept('prism', 'planar', stats(1.0, rms=0.6), bbx,
                   lambda: stats(0.0, rms=50.0))
    assert _accept('box', 'planar', stats(1e6), bbx)                  # the last fit always stands
    assert _accept('prism', 'linear', stats(10.0), bbx)               # the linear rule is its own
