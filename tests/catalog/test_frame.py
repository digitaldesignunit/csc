"""Stage 1 of the geometry runner: the frame (spec 4.3, decisions 7.10, 8.15)."""

from __future__ import annotations

import numpy as np
import pytest

from apps.catalog.frame import (
    candidate_frames,
    compute_frame,
    is_standing,
    minimum_volume_box,
)


def box_points(sx, sy, sz, rotation=None, shift=(0.0, 0.0, 0.0)):
    corners = np.array([[x, y, z] for x in (-.5, .5) for y in (-.5, .5)
                        for z in (-.5, .5)]) * [sx, sy, sz]
    if rotation is not None:
        corners = corners @ rotation.T
    return corners + shift


def rot(axis, degrees):
    a = np.radians(degrees)
    c, s = np.cos(a), np.sin(a)
    if axis == 'x':
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == 'y':
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def axes_of(result):
    f = result.frame
    return np.array([f['x'], f['y'], f['z']])


def test_lying_box_keeps_stored_axes():
    result = compute_frame(box_points(400, 200, 50))
    assert np.allclose(axes_of(result), np.eye(3), atol=1e-9)
    assert np.allclose(result.bbx, (400, 200, 50))
    assert np.allclose(result.frame['o'], 0, atol=1e-9)


def test_axis_convention_longest_x_middle_y_shortest_z():
    # stored with the length along z, depth along x: the frame maps it to x/y/z
    points = box_points(50, 200, 400)
    result = compute_frame(points)
    assert np.allclose(result.bbx, (400, 200, 50))
    x, y, z = axes_of(result)
    assert abs(x[2]) == pytest.approx(1.0)       # longest is stored z
    assert abs(y[1]) == pytest.approx(1.0)
    assert abs(z[0]) == pytest.approx(1.0)
    assert np.linalg.det(axes_of(result)) == pytest.approx(1.0)


def test_square_column_stands_and_keeps_the_input_orientation():
    # 200 x 200 x 3000 column, upright in the stored coordinates
    points = box_points(200, 200, 3000)
    standing = compute_frame(points, original_function='IfcColumn')
    assert np.allclose(standing.bbx, (200, 200, 3000))     # z is the length
    assert np.allclose(axes_of(standing)[2], (0, 0, 1), atol=1e-9)
    assert np.linalg.det(axes_of(standing)) == pytest.approx(1.0)
    # the same piece as a beam lies
    beam = compute_frame(points, original_function='IfcBeam')
    assert np.allclose(beam.bbx, (3000, 200, 200))


def test_a_column_stored_lying_is_stood_up():
    points = box_points(3000, 200, 200)
    standing = compute_frame(points, original_function='IfcColumn')
    assert np.allclose(standing.bbx, (200, 200, 3000))
    assert abs(axes_of(standing)[2][0]) == pytest.approx(1.0)


def test_a_short_column_fragment_lies():
    # 300 x 200 x 150: longest / middle = 1.5 < 2, the rule does not apply
    result = compute_frame(box_points(300, 200, 150),
                           original_function='IfcColumn')
    assert np.allclose(result.bbx, (300, 200, 150))


def test_the_column_rule_reads_function_and_elongation_only():
    assert is_standing('IfcColumn', (3000, 200, 200))
    assert is_standing('IfcColumn', (400, 200, 100))          # exactly 2
    assert not is_standing('IfcColumn', (399, 200, 100))
    assert not is_standing('IfcBeam', (3000, 200, 200))
    assert not is_standing(None, (3000, 200, 200))


def test_an_irregular_column_still_stands():
    # a notched column: its hull deficit makes it irregular for stage 2,
    # stage 1 does not care
    points = box_points(200, 200, 3000)
    notch = points[points[:, 2] > 0] + [0, 0, 0]
    result = compute_frame(np.vstack([points, notch * [0.4, 0.4, 1.0]]),
                           original_function='IfcColumn')
    assert result.bbx[2] == pytest.approx(3000)


def test_a_flipped_upload_keeps_the_inputs_up():
    # an asymmetric beam (a stepped profile) stored upside down: the
    # canonical z follows the stored up, never against it (8.53)
    base = box_points(600, 120, 20)
    rib = box_points(600, 30, 60, shift=(0, 0, 40))
    points = np.vstack([base, rib])
    for turn in (rot('x', 180), rot('y', 180), np.eye(3)):
        frame = compute_frame(points @ turn.T, original_function='IfcBeam')
        assert axes_of(frame)[2][2] > 0.5


def test_a_near_horizontal_z_is_not_constrained():
    # a plate stored standing on its edge: canonical z is horizontal, so
    # either sign may win; the rule does not apply (|z . Z| < 0.5)
    points = box_points(600, 20, 300)
    result = compute_frame(points, original_function='IfcPlate')
    z = axes_of(result)[2]
    assert abs(z[2]) < 0.5
    assert np.allclose(result.bbx, (600, 300, 20))


def test_cube_frame_is_the_identity_for_stored_axes():
    # all three extents tie: any swap and sign is allowed, the closest wins
    result = compute_frame(box_points(100, 100, 100))
    assert np.allclose(axes_of(result), np.eye(3), atol=1e-9)


def test_cube_rotated_by_ninety_degrees_stays_closest():
    result = compute_frame(box_points(100, 100, 100, rotation=rot('z', 90)))
    assert np.allclose(axes_of(result), np.eye(3), atol=1e-9)


def test_flipped_upload_gets_the_closest_signs_not_a_flip():
    # the same beam stored upside down (180 degrees about its x axis)
    upright = compute_frame(box_points(600, 120, 60))
    flipped = compute_frame(box_points(600, 120, 60, rotation=rot('x', 180)))
    assert np.allclose(axes_of(upright), np.eye(3), atol=1e-9)
    # the box is symmetric, so the frame closest to the stored axes is
    # still the identity: stored coordinates are never re-oriented
    assert np.allclose(axes_of(flipped), np.eye(3), atol=1e-9)
    assert np.allclose(flipped.bbx, (600, 120, 60))


def test_tilted_piece_maps_to_the_canonical_orientation():
    r = rot('z', 30)
    result = compute_frame(box_points(600, 120, 60, rotation=r))
    x, y, z = axes_of(result)
    assert np.allclose(x, r[:, 0], atol=1e-7)
    assert np.allclose(y, r[:, 1], atol=1e-7)
    assert np.allclose(z, r[:, 2], atol=1e-7)
    assert np.allclose(result.bbx, (600, 120, 60), atol=1e-6)


def test_frame_origin_is_the_box_centre():
    result = compute_frame(box_points(400, 200, 50, shift=(10, -20, 30)))
    assert np.allclose(result.frame['o'], (10, -20, 30), atol=1e-9)


def test_near_equal_extents_may_swap_within_tolerance():
    # 400 x 392 x 50: 8 mm apart is within max(2 %, 3 mm) = 8 mm: tied
    swapped = box_points(392, 400, 50)
    result = compute_frame(swapped)
    # closest to the stored axes: x stays x although y is (slightly) longer
    assert np.allclose(axes_of(result), np.eye(3), atol=1e-9)
    assert result.bbx[0] == pytest.approx(392)


def test_clearly_longer_extent_still_leads():
    result = compute_frame(box_points(300, 400, 50))
    assert result.bbx[0] == pytest.approx(400)
    assert abs(axes_of(result)[0][1]) == pytest.approx(1.0)


def test_candidates_are_right_handed_and_deterministic():
    axes, _, extents, _ = minimum_volume_box(box_points(100, 100, 100))
    first = [(x.tolist(), y.tolist(), z.tolist())
             for x, y, z, _ in candidate_frames(axes, extents, False)]
    second = [(x.tolist(), y.tolist(), z.tolist())
              for x, y, z, _ in candidate_frames(axes, extents, False)]
    assert first == second
    assert len(first) == 24                       # 6 permutations x 4 signs
    for x, y, z in first:
        assert np.dot(np.cross(x, y), z) > 0


def test_same_input_gives_the_same_frame():
    points = box_points(500, 130, 70, rotation=rot('z', 17))
    a, b = compute_frame(points), compute_frame(points)
    assert a.frame == b.frame and a.bbx == b.bbx


def test_hull_scores_for_a_box_are_near_zero_boxscore():
    result = compute_frame(box_points(400, 200, 50))
    assert result.scores['boxscore'] == pytest.approx(0.0, abs=1e-6)
    assert set(result.scores) == {'boxscore', 'spherescore', 'linescore',
                                  'planescore'}
    assert result.obb_extents == pytest.approx((400.0, 200.0, 50.0))


def test_flat_point_set_still_gets_a_frame():
    xs, ys = np.meshgrid(np.linspace(-200, 200, 9), np.linspace(-100, 100, 5))
    points = np.column_stack([xs.ravel(), ys.ravel(), np.zeros(xs.size)])
    result = compute_frame(points)
    assert result.bbx[0] == pytest.approx(400)
    assert result.bbx[2] == pytest.approx(0, abs=1e-9)
    assert result.scores == {}                    # no hull, no scores


def test_random_coplanar_points_get_a_frame_without_scores():
    rng = np.random.default_rng(4)
    points = np.column_stack([rng.uniform(0, 500, 200),
                              rng.uniform(0, 300, 200), np.zeros(200)])
    result = compute_frame(points)
    assert result.bbx[2] == pytest.approx(0, abs=1e-6)
    assert result.bbx[0] >= 450
    assert result.scores == {}
    assert np.linalg.det(axes_of(result)) == pytest.approx(1.0)


def test_the_four_corners_of_a_sheet_get_a_frame():
    corners = np.array([[0, 0, 0], [500, 0, 0], [500, 300, 0], [0, 300, 0.0]])
    result = compute_frame(corners)
    assert result.bbx == pytest.approx((500, 300, 0), abs=1e-6)
    assert result.scores == {}
