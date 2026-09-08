"""Tests for planar outline extraction feeding the radial signature."""

from __future__ import annotations

import numpy as np
import pytest
import trimesh

from apps.descriptors import radial_signature as rs
from apps.descriptors.geometry import (
    create_mesh_from_extrusion,
    convex_hull_from_points,
)
from apps.descriptors.outline import (
    PANEL_POLICY,
    PANEL_SLAB_FRACTION,
    SOLID_POLICY,
    _largest_loop,
    _polygon_area,
    outline_from_component,
    policy_for,
    section_outline_from_mesh,
    section_outline_from_points,
)
from apps.descriptors.registry import compute_descriptor
from apps.descriptors.specs import RADIAL_SIGNATURE

# An L-shaped panel: 100 x 100 with a 60 x 60 bite taken out, so the true
# area is 6400 while the convex hull is 8200. Any outline that reports the
# hull area has thrown away the concavity the signature exists to capture.
L_PROFILE = [[0, 0], [100, 0], [100, 40], [40, 40], [40, 100], [0, 100]]
L_AREA = 6400.0
L_HULL_AREA = 8200.0
PANEL_THICKNESS = 10.0

# A beam: a 100 x 200 profile swept 2000 along its longest axis. Its profile
# plane and its PCA plane are different planes, which is the whole reason
# non-planar components are cut rather than handed their authored profile.
BEAM_PROFILE = [[-50, -100], [50, -100], [50, 100], [-50, 100]]
BEAM_LENGTH = 2000.0
BEAM_PROFILE_AREA = 100.0 * 200.0
BEAM_SECTION_AREA = BEAM_LENGTH * 200.0

IDENTITY_FRAME = {
    'o': [0.0, 0.0, 0.0],
    'x': [1.0, 0.0, 0.0],
    'y': [0.0, 1.0, 0.0],
    'z': [0.0, 0.0, 1.0],
}

# Maps the beam's sweep axis (model Z, the longest) onto PCA X, leaving the
# 100 direction on PCA Z where a real PCA frame would put it.
BEAM_FRAME = {
    'o': [0.0, 0.0, 0.0],
    'x': [0.0, 0.0, 1.0],
    'y': [0.0, 1.0, 0.0],
    'z': [1.0, 0.0, 0.0],
}


def _l_mesh():
    return create_mesh_from_extrusion(L_PROFILE, PANEL_THICKNESS)


def _rotated_l_mesh(degrees):
    """The same panel, turned within its own plane."""
    angle = np.deg2rad(degrees)
    rotation = np.array([
        [np.cos(angle), -np.sin(angle)],
        [np.sin(angle), np.cos(angle)],
    ])
    profile = np.asarray(L_PROFILE, dtype=float) @ rotation.T
    return create_mesh_from_extrusion(profile.tolist(), PANEL_THICKNESS)


def _beam_mesh():
    return create_mesh_from_extrusion(BEAM_PROFILE, BEAM_LENGTH)


def _surface_points(mesh, count=6000, seed=0):
    """Points sampled over a whole surface, as a scan would be."""
    points, _ = trimesh.sample.sample_surface(mesh, count, seed=seed)
    return np.asarray(points, dtype=np.float64)


def _l_surface_points(count=6000, seed=0):
    return _surface_points(_l_mesh(), count, seed)


def _l_two_face_points(count=4000, seed=1):
    """Points on the two large faces only, with no material at mid-depth."""
    rng = np.random.default_rng(seed)
    candidates = rng.uniform([0, 0], [100, 100], size=(count * 4, 2))
    inside = ~((candidates[:, 0] > 40) & (candidates[:, 1] > 40))
    xy = candidates[inside][:count]
    z = rng.choice([-5.0, 5.0], size=len(xy))
    return np.column_stack([xy, z])


def _flatten(points, **kwargs):
    """Panel-style call: keep every point rather than a thin slab."""
    kwargs.setdefault('slab_fraction', PANEL_SLAB_FRACTION)
    return section_outline_from_points(points, **kwargs)


def _area(outline):
    return _polygon_area(np.asarray(outline, dtype=np.float64))


def _component(geometry, ctype='panel', pca_frame=IDENTITY_FRAME):
    return {
        '_id': 'snap-1',
        'type': ctype,
        'pca_frame': pca_frame,
        'geometry': geometry,
        'descriptors': {},
    }


def _panel(geometry, pca_frame=IDENTITY_FRAME):
    return _component(geometry, 'panel', pca_frame)


def _inline_mesh(mesh):
    return {'v': mesh.vertices.tolist(), 'f': mesh.faces.tolist()}


def _tetra_preview():
    return [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


# POLICY ---------------------------------------------------------------------

def test_only_panels_are_rest_aligned():
    assert policy_for(_component({}, 'panel')) is PANEL_POLICY
    for ctype in ('beam', 'column', 'slab', 'rubble', 'brick', 'other'):
        assert policy_for(_component({}, ctype)) is SOLID_POLICY
    # An untyped document is not assumed to be planar.
    assert policy_for({'geometry': {}}) is SOLID_POLICY


def test_panel_policy_flattens_and_aligns_solid_policy_does_neither():
    assert PANEL_POLICY.rest_align and not SOLID_POLICY.rest_align
    assert PANEL_POLICY.use_extrusion_profile
    assert not SOLID_POLICY.use_extrusion_profile
    assert PANEL_POLICY.slab_fraction == 1.0
    assert 0.0 < SOLID_POLICY.slab_fraction < 1.0
    assert PANEL_POLICY.widen_sparse_slab
    assert not SOLID_POLICY.widen_sparse_slab


# LOOP SELECTION -------------------------------------------------------------

def test_largest_loop_picks_the_outer_boundary():
    outer = np.array([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], float)
    hole = np.array([[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]], float)
    assert _largest_loop([hole, outer]) is outer


def test_largest_loop_prefers_closed_loops_over_bigger_open_ones():
    closed = np.array([[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]], float)
    open_bigger = np.array([[0, 0], [50, 0], [50, 50]], float)
    assert _largest_loop([open_bigger, closed]) is closed


def test_largest_loop_returns_none_without_usable_loops():
    assert _largest_loop([]) is None
    assert _largest_loop([np.array([[0, 0], [1, 1]], float)]) is None


# MESH SECTIONING ------------------------------------------------------------

def test_mesh_section_recovers_the_true_outline_not_the_hull():
    outline = section_outline_from_mesh(_l_mesh())
    assert _area(outline) == pytest.approx(L_AREA, rel=1e-9)
    assert _area(outline) < L_HULL_AREA


def test_mesh_section_of_a_box_matches_its_footprint():
    mesh = trimesh.creation.box(extents=[80.0, 40.0, 6.0])
    assert _area(section_outline_from_mesh(mesh)) == pytest.approx(
        3200.0, rel=1e-9)


def test_mesh_section_is_independent_of_depth():
    thin = section_outline_from_mesh(create_mesh_from_extrusion(
        L_PROFILE, 1.0))
    thick = section_outline_from_mesh(create_mesh_from_extrusion(
        L_PROFILE, 40.0))
    assert _area(thin) == pytest.approx(_area(thick), rel=1e-9)


def test_mesh_section_cuts_the_centre_even_when_offset_from_zero():
    """Geometry stored without a PCA frame can sit anywhere on Z."""
    mesh = trimesh.creation.box(extents=[80.0, 40.0, 6.0])
    mesh.apply_translation([0.0, 0.0, 500.0])
    assert _area(section_outline_from_mesh(mesh)) == pytest.approx(
        3200.0, rel=1e-9)


def test_mesh_section_rejects_a_mesh_with_no_depth():
    flat = trimesh.Trimesh(
        vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        faces=[[0, 1, 2]],
    )
    with pytest.raises(ValueError, match='no extent'):
        section_outline_from_mesh(flat)


# POINT CLOUD SECTIONING -----------------------------------------------------

def test_flattened_cloud_recovers_the_concavity():
    outline = _flatten(_l_surface_points())
    # Well short of the convex hull, and close to the true L area.
    assert _area(outline) == pytest.approx(L_AREA, rel=0.05)
    assert _area(outline) < 0.85 * L_HULL_AREA


def test_flattened_cloud_does_not_invent_concavities():
    rng = np.random.default_rng(7)
    xy = rng.uniform([0, 0], [100, 40], size=(4000, 2))
    z = rng.uniform(-5, 5, size=len(xy))
    outline = _flatten(np.column_stack([xy, z]))
    assert _area(outline) == pytest.approx(4000.0, rel=0.05)


def test_cloud_section_is_scale_invariant():
    points = _l_surface_points()
    small = _area(_flatten(points))
    large = _area(_flatten(points * 1000.0))
    assert large / 1e6 == pytest.approx(small, rel=1e-6)


def test_sparse_slab_widens_only_when_the_policy_allows_it():
    """A two-sided scan has nothing at mid-depth.

    Panels widen to the silhouette rather than fail; everything else fails,
    because silently swapping a section for a silhouette would return a
    different descriptor than the one asked for.
    """
    points = _l_two_face_points()
    messages = []
    widened = section_outline_from_points(
        points, slab_fraction=0.25, widen_sparse_slab=True,
        logger=messages.append)
    assert any('flattening the full depth' in m for m in messages)
    assert _area(widened) == pytest.approx(L_AREA, rel=0.05)

    with pytest.raises(ValueError, match='fewer than the 32'):
        section_outline_from_points(
            points, slab_fraction=0.25, widen_sparse_slab=False)


def test_thin_slab_is_honoured_when_it_holds_enough_points():
    """An hourglass cloud, whose waist and silhouette genuinely differ.

    A prismatic panel cannot distinguish the two, so this uses a cloud that
    is 40 wide at mid-depth and 100 wide at its ends.
    """
    rng = np.random.default_rng(11)
    count = 20000
    z = rng.uniform(-5.0, 5.0, size=count)
    half_width = 20.0 + 6.0 * np.abs(z)
    xy = rng.uniform(-1.0, 1.0, size=(count, 2)) * half_width[:, None]
    cloud = np.column_stack([xy, z])

    waist = np.asarray(
        section_outline_from_points(cloud, slab_fraction=0.1))
    silhouette = np.asarray(_flatten(cloud))

    def width(outline):
        return outline[:, 0].max() - outline[:, 0].min()

    assert width(silhouette) == pytest.approx(100.0, rel=0.05)
    # The 10% slab spans |z| <= 0.5, so it is 46 wide, not 100.
    assert width(waist) == pytest.approx(46.0, rel=0.05)
    assert _area(waist) < 0.25 * _area(silhouette)


def test_cloud_section_cuts_the_centre_even_when_offset_from_zero():
    rng = np.random.default_rng(3)
    count = 20000
    z = rng.uniform(-5.0, 5.0, size=count) + 500.0
    half_width = 20.0 + 6.0 * np.abs(z - 500.0)
    xy = rng.uniform(-1.0, 1.0, size=(count, 2)) * half_width[:, None]
    waist = np.asarray(section_outline_from_points(
        np.column_stack([xy, z]), slab_fraction=0.1))
    assert waist[:, 0].max() - waist[:, 0].min() == pytest.approx(
        46.0, rel=0.05)


def test_cloud_section_rejects_collinear_points():
    points = np.column_stack([
        np.linspace(0, 10, 50),
        np.linspace(0, 20, 50),
        np.zeros(50),
    ])
    with pytest.raises(ValueError):
        _flatten(points)


def test_cloud_section_rejects_too_few_points():
    with pytest.raises(ValueError, match='at least 3 finite points'):
        _flatten([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])


def test_cloud_section_rejects_malformed_input():
    with pytest.raises(ValueError, match=r'\[x, y, z\] triplets'):
        _flatten([[0.0, 0.0], [1.0, 1.0], [2.0, 3.0]])


def test_cloud_section_ignores_non_finite_points():
    points = np.vstack([
        _l_surface_points(2000),
        [[np.nan, 0.0, 0.0], [np.inf, 1.0, 1.0]],
    ])
    assert _area(_flatten(points)) == pytest.approx(L_AREA, rel=0.06)


# COMPONENT RESOLUTION: PANELS -----------------------------------------------

def test_mesh_outranks_point_cloud_and_extrusion():
    outline, source, reason = outline_from_component(_panel({
        'extrusions': [{'profile': L_PROFILE, 'height': PANEL_THICKNESS}],
        'meshes': [_inline_mesh(_l_mesh())],
        'point_clouds': [{'points': _l_surface_points(200).tolist()}],
    }))
    assert reason is None
    assert source == 'geometry.meshes[0] (section)'
    assert _area(outline) == pytest.approx(L_AREA, rel=1e-9)


def test_point_cloud_outranks_extrusion_when_there_is_no_mesh():
    outline, source, reason = outline_from_component(_panel({
        'extrusions': [{'profile': L_PROFILE, 'height': PANEL_THICKNESS}],
        'point_clouds': [{'points': _l_surface_points().tolist()}],
    }))
    assert reason is None
    assert source == 'geometry.point_clouds[0] (section)'
    assert _area(outline) == pytest.approx(L_AREA, rel=0.05)


def test_mesh_outranks_point_cloud():
    outline, source, reason = outline_from_component(_panel({
        'meshes': [_inline_mesh(_l_mesh())],
        'point_clouds': [{'points': _l_surface_points(200).tolist()}],
    }))
    assert reason is None
    assert source == 'geometry.meshes[0] (section)'
    assert _area(outline) == pytest.approx(L_AREA, rel=1e-9)


def test_cloud_only_component_ignores_a_hull_mesh_from_the_runner():
    """The runner hands cloud-only snapshots a convex hull.

    Sectioning that hull would report the 8200 hull area and silently erase
    the concavity, so the cloud branch has to re-read the raw points.
    """
    points = _l_surface_points()
    outline, source, reason = outline_from_component(
        _panel({'point_clouds': [{'points': points.tolist()}]}),
        mesh=convex_hull_from_points(points),
    )
    assert reason is None
    assert source == 'geometry.point_clouds[0] (section)'
    assert _area(outline) == pytest.approx(L_AREA, rel=0.05)


def test_detailed_ply_outranks_inline_mesh(tmp_path):
    """On-disk detailed.ply is the highest-resolution mesh source."""
    snapshot_id = 'snap-1'
    ply_dir = tmp_path / snapshot_id / '0'
    ply_dir.mkdir(parents=True)
    detailed = create_mesh_from_extrusion(L_PROFILE, PANEL_THICKNESS)
    detailed.export(str(ply_dir / 'detailed.ply'))

    inline = trimesh.creation.box(extents=[80.0, 40.0, 6.0])
    outline, source, reason = outline_from_component(
        _panel({'meshes': [_inline_mesh(inline)]}),
        meshes_dir=str(tmp_path),
    )
    assert reason is None
    assert source == 'meshes/0/detailed.ply (section)'
    assert _area(outline) == pytest.approx(L_AREA, rel=1e-6)


def test_point_cloud_ply_outranks_inline_preview(tmp_path):
    """The full PLY is preferred over the subsampled inline preview."""
    snapshot_id = 'snap-1'
    cloud_dir = tmp_path / snapshot_id
    cloud_dir.mkdir()
    full = trimesh.PointCloud(_l_surface_points())
    (cloud_dir / '0.ply').write_bytes(full.export(file_type='ply'))

    outline, source, reason = outline_from_component(
        _panel({'point_clouds': [{'points': _tetra_preview()}]}),
        point_clouds_dir=str(tmp_path),
    )
    assert reason is None
    assert source == 'point_clouds/0.ply (section)'
    assert _area(outline) == pytest.approx(L_AREA, rel=0.05)


def test_component_without_outline_geometry_reports_a_reason():
    outline, source, reason = outline_from_component(_panel({}))
    assert outline is None and source is None
    assert reason


def test_component_with_empty_point_cloud_reports_a_reason():
    outline, _, reason = outline_from_component(
        _panel({'point_clouds': [{'points': []}]}))
    assert outline is None
    assert 'no points' in reason


def test_degenerate_cloud_reports_a_reason_instead_of_raising():
    outline, _, reason = outline_from_component(_panel({
        'point_clouds': [{'points': [[0.0, 0.0, 0.0]] * 10}],
    }))
    assert outline is None
    assert 'point_clouds[0]' in reason


def test_pca_frame_is_applied_to_cloud_points():
    """A cloud stored with its short axis off Z must still section right."""
    points = _l_surface_points()
    # Store the panel lying on its side: model Y is the short axis.
    swapped = points[:, [0, 2, 1]]
    frame = {
        'o': [0.0, 0.0, 0.0],
        'x': [1.0, 0.0, 0.0],
        'y': [0.0, 0.0, 1.0],
        'z': [0.0, 1.0, 0.0],
    }
    outline, _, reason = outline_from_component(
        _panel({'point_clouds': [{'points': swapped.tolist()}]}, frame))
    assert reason is None
    assert _area(outline) == pytest.approx(L_AREA, rel=0.05)


# COMPONENT RESOLUTION: EVERYTHING ELSE --------------------------------------

def test_beam_is_cut_through_its_pca_plane_not_handed_its_profile():
    """The case that separates the two policies.

    A beam's authored profile is its 100 x 200 cross-section, but its PCA
    plane holds the 2000 x 200 lengthwise cut. Reading the profile would
    silently describe a different plane than every other beam source does.
    """
    geometry = {'extrusions': [
        {'profile': BEAM_PROFILE, 'height': BEAM_LENGTH}]}
    outline, source, reason = outline_from_component(
        _component(geometry, 'beam', BEAM_FRAME))

    assert reason is None
    assert source == 'geometry.extrusions[0] (section)'
    assert _area(outline) == pytest.approx(BEAM_SECTION_AREA, rel=1e-6)
    assert _area(outline) != pytest.approx(BEAM_PROFILE_AREA, rel=0.5)


def test_the_same_extrusion_typed_as_a_panel_uses_its_profile():
    geometry = {'extrusions': [
        {'profile': BEAM_PROFILE, 'height': BEAM_LENGTH}]}
    outline, source, _ = outline_from_component(
        _component(geometry, 'panel', BEAM_FRAME))

    assert source == 'geometry.extrusions[0].profile'
    assert _area(outline) == pytest.approx(BEAM_PROFILE_AREA, rel=1e-9)


def test_beam_mesh_and_beam_extrusion_describe_the_same_plane():
    geometry_from_extrusion = {'extrusions': [
        {'profile': BEAM_PROFILE, 'height': BEAM_LENGTH}]}
    geometry_from_mesh = {'meshes': [_inline_mesh(_beam_mesh())]}

    from_extrusion, _, _ = outline_from_component(
        _component(geometry_from_extrusion, 'beam', BEAM_FRAME))
    from_mesh, _, _ = outline_from_component(
        _component(geometry_from_mesh, 'beam', BEAM_FRAME))

    assert _area(from_extrusion) == pytest.approx(
        _area(from_mesh), rel=1e-9)


def test_solid_cloud_is_sliced_rather_than_flattened():
    points = _surface_points(_beam_mesh(), 8000)
    outline, source, reason = outline_from_component(
        _component({'point_clouds': [{'points': points.tolist()}]},
                   'rubble', BEAM_FRAME))
    assert reason is None
    assert source == 'geometry.point_clouds[0] (section)'
    # The slice through the centre still spans the beam's dominant plane.
    assert _area(outline) == pytest.approx(BEAM_SECTION_AREA, rel=0.1)


def test_solid_cloud_too_sparse_to_slice_reports_a_reason():
    """No widening for solids, so a thin cloud fails with an explanation."""
    points = _surface_points(_beam_mesh(), 150)
    outline, _, reason = outline_from_component(
        _component({'point_clouds': [{'points': points.tolist()}]},
                   'rubble', BEAM_FRAME))
    assert outline is None
    assert 'fewer than the 32' in reason


# SPEC INTEGRATION -----------------------------------------------------------

def _radial(component, mesh=None):
    return compute_descriptor(RADIAL_SIGNATURE, component, mesh)


def test_spec_has_no_type_filter():
    assert RADIAL_SIGNATURE.applicability_filter is None
    for ctype in ('panel', 'beam', 'rubble', 'connector', 'other'):
        assert RADIAL_SIGNATURE.is_applicable(_component({}, ctype))


def test_geometry_gate_accepts_any_type_but_needs_geometry():
    for ctype in ('panel', 'beam', 'rubble'):
        assert rs.is_applicable(
            _component({'meshes': [{}]}, ctype))
        assert not rs.is_applicable(_component({}, ctype))


def test_spec_computes_from_a_mesh_only_panel():
    out = _radial(_panel({'meshes': [_inline_mesh(_l_mesh())]}))
    assert len(out['radial_distance_64']) == 64
    assert all(d > 0 for d in out['radial_distance_64'])


def test_spec_computes_from_a_cloud_only_panel():
    out = _radial(_panel({
        'point_clouds': [{'points': _l_surface_points().tolist()}],
    }))
    assert len(out['radial_distance_64']) == 64
    assert all(d > 0 for d in out['radial_distance_64'])


def test_spec_computes_for_non_panel_types():
    geometry = {'meshes': [_inline_mesh(_beam_mesh())]}
    for ctype in ('beam', 'column', 'rubble', 'brick', 'other'):
        out = _radial(_component(geometry, ctype, BEAM_FRAME))
        assert len(out['radial_distance_64']) == 64
        assert all(d > 0 for d in out['radial_distance_64'])


def test_non_panel_outlines_are_not_rest_rotated():
    """The PCA frame already fixed the orientation; keep it."""
    geometry = {'meshes': [_inline_mesh(_beam_mesh())]}
    outline, _, _ = outline_from_component(
        _component(geometry, 'beam', BEAM_FRAME))

    expected = rs.compute_radial_signatures(
        outline, resolutions=(64,), rest_align=False)[64]
    out = _radial(_component(geometry, 'beam', BEAM_FRAME))

    assert out['radial_distance_64'] == expected['distances']
    assert expected['rest_angle_deg'] == 0.0


def test_panel_outlines_are_still_rest_rotated():
    outline, _, _ = outline_from_component(
        _panel({'meshes': [_inline_mesh(_l_mesh())]}))
    out = _radial(_panel({'meshes': [_inline_mesh(_l_mesh())]}))

    aligned = rs.compute_radial_signatures(
        outline, resolutions=(64,), rest_align=True)[64]
    assert out['radial_distance_64'] == aligned['distances']


def test_rest_alignment_makes_panels_invariant_to_in_plane_rotation():
    """What rest position buys panels, and what solids give up.

    Turning a panel in its own plane must not change its signature. A solid
    keeps the orientation its PCA frame established, so the same turn does
    change it.
    """
    upright = {'meshes': [_inline_mesh(_l_mesh())]}
    turned = {'meshes': [_inline_mesh(_rotated_l_mesh(30.0))]}

    as_panel = [
        np.asarray(_radial(_panel(g))['radial_distance_64'])
        for g in (upright, turned)
    ]
    assert np.allclose(as_panel[0], as_panel[1], rtol=1e-6)

    as_solid = [
        np.asarray(_radial(
            _component(g, 'rubble'))['radial_distance_64'])
        for g in (upright, turned)
    ]
    assert not np.allclose(as_solid[0], as_solid[1], rtol=1e-6)


def test_spec_skips_a_component_with_no_geometry():
    logged = []
    assert compute_descriptor(
        RADIAL_SIGNATURE, _panel({}), None, log=logged.append) == {}
    assert any('cannot compute' in m for m in logged)


def test_mesh_and_cloud_signatures_of_one_panel_agree():
    """The whole point: a scanned panel must match its modelled twin.

    Compared over circular shifts, because `rest_position` does not put the
    two representations in the same canonical rotation: it reliably lands
    them a quarter turn apart on this shape. Errors are scaled by the mean
    ray length rather than per ray, since the rays aimed just past the
    concave corner are only a millimetre or two long and any rounding there
    dwarfs them in relative terms.
    """
    from_mesh = np.asarray(_radial(_panel({
        'meshes': [_inline_mesh(_l_mesh())],
    }))['radial_distance_64'])
    from_cloud = np.asarray(_radial(_panel({
        'point_clouds': [{'points': _l_surface_points().tolist()}],
    }))['radial_distance_64'])

    scale = from_mesh.mean()
    errors = [
        np.abs(from_mesh - np.roll(from_cloud, k)) / scale
        for k in range(len(from_cloud))
    ]
    best = min(errors, key=lambda e: e.max())
    # Typical agreement is tight; the outlier is the rounded concave corner.
    assert best.mean() < 0.03
    assert best.max() < 0.12


def test_mesh_and_cloud_signatures_of_one_beam_agree():
    """Non-panels skip rest alignment, so the rays line up directly."""
    from_mesh = np.asarray(_radial(_component(
        {'meshes': [_inline_mesh(_beam_mesh())]}, 'beam', BEAM_FRAME,
    ))['radial_distance_64'])
    from_cloud = np.asarray(_radial(_component(
        {'point_clouds': [
            {'points': _surface_points(_beam_mesh(), 8000).tolist()}]},
        'beam', BEAM_FRAME,
    ))['radial_distance_64'])

    error = np.abs(from_mesh - from_cloud) / from_mesh.mean()
    assert error.mean() < 0.05
    assert error.max() < 0.15
