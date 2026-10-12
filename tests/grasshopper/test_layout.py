"""Reinforcement layouts in Grasshopper, outside Rhino (RL9, RL11): the
inverse placement, the document unit, the target snapshot of a new layout and
the stored layouts read back into bars."""

from __future__ import annotations

import json

import numpy as np
import pytest

from csc_gh import build as b
from csc_gh import layout as lay
from csc_gh.read import placement_matrix

UUID_A = '11111111-1111-4111-8111-111111111111'
UUID_B = '22222222-2222-4222-8222-222222222222'
UUID_C = '33333333-3333-4333-9333-333333333333'


def _plane(rng):
    """A random right-handed placement {o, x, y, z}."""
    q, r = np.linalg.qr(rng.normal(size=(3, 3)))
    q = q * np.sign(np.diag(r))
    if np.linalg.det(q) < 0:
        q[:, 2] = -q[:, 2]
    origin = rng.uniform(-5000, 5000, size=3)
    return {'o': origin.tolist(), 'x': q[:, 0].tolist(),
            'y': q[:, 1].tolist(), 'z': q[:, 2].tolist()}


def _passport(snapshot_id=UUID_A, placement=None):
    snapshot = {'_id': snapshot_id, 'identity_id': UUID_B}
    if placement is not None:
        snapshot['csc_placement'] = placement
    return {'identity': {'_id': UUID_B}, 'snapshots': [snapshot]}


# POINTS ----------------------------------------------------------------------
def test_stored_to_placed_is_the_placement_matrix():
    plane = {'o': [10, 20, 30], 'x': [0, 1, 0], 'y': [-1, 0, 0],
             'z': [0, 0, 1]}
    placed = lay.points_to_document([(0, 0, 0), (1, 0, 0), (0, 0, 2)], plane)
    assert placed[0] == pytest.approx((10, 20, 30))
    assert placed[1] == pytest.approx((10, 21, 30))       # + x axis
    assert placed[2] == pytest.approx((10, 20, 32))
    # the same matrix the Fetch components use for the mesh
    matrix = placement_matrix(plane)
    assert (matrix @ np.array([1, 0, 0, 1]))[:3] == pytest.approx(placed[1])


@pytest.mark.parametrize('seed', range(6))
def test_placed_to_stored_to_placed_is_the_identity(seed):
    rng = np.random.default_rng(seed)
    plane = _plane(rng)
    stored = rng.uniform(-3000, 3000, size=(25, 3))
    placed = lay.points_to_document(stored, plane)
    back = lay.points_to_stored(placed, plane)
    assert np.allclose(back, stored, atol=1e-6)
    again = lay.points_to_document(back, plane)
    assert np.allclose(again, placed, atol=1e-6)


def test_without_a_placement_nothing_moves_and_nothing_is_scaled():
    assert lay.points_to_stored([(1, 2, 3)]) == [(1.0, 2.0, 3.0)]
    assert lay.points_to_document([(1000, 2000, 3000)]) == [
        (1000.0, 2000.0, 3000.0)]
    # document units are millimetres, 1:1 (no scale argument any more)
    with pytest.raises(TypeError):
        lay.points_to_stored([(1, 2, 3)], None, 1000.0)


def test_a_bad_point_is_refused():
    with pytest.raises(b.BuildError):
        lay.points_to_stored([(0, float('nan'), 0)])


def test_bars_to_stored_leaves_the_diameters_alone():
    plane = {'o': [0, 0, 5], 'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]}
    bars = [{'spec': 'BSt III', 'diameter_mm': 8.0,
             'points': [(0, 0, 5), (2, 0, 5)]}]
    out = lay.bars_to_stored(bars, plane)
    assert out[0]['diameter_mm'] == 8.0 and out[0]['spec'] == 'BSt III'
    assert out[0]['points'] == [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0)]
    assert bars[0]['points'] == [(0, 0, 5), (2, 0, 5)]          # not changed


def test_the_unit_warning_says_that_nothing_is_scaled():
    assert lay.unit_warning(1.0, 'Millimeters') is None
    text = lay.unit_warning(1000.0, 'Meters')
    assert 'Meters' in text and 'millimetres' in text and '1:1' in text
    assert 'draw at that scale' in text
    assert 'Inches' in lay.unit_warning(25.4, 'Inches')
    # the factor stays checked for the later unit-aware task
    for bad in (0, -1, float('nan'), 'x', None):
        with pytest.raises(b.BuildError):
            lay.unit_factor(bad)
    assert lay.unit_factor('25.4') == 25.4


# THE TARGET OF A NEW LAYOUT (RL9) ---------------------------------------------
def test_a_passport_with_a_placement_means_the_inverse_placement():
    plane = _plane(np.random.default_rng(1))
    target = lay.layout_target(_passport(UUID_A, plane))
    assert target['snapshot_id'] == UUID_A
    assert target['conversion'] == 'inverse placement'
    assert target['placement']['o'] == pytest.approx(plane['o'])
    assert 'inverse placement' in target['remark'] and UUID_A in \
        target['remark']
    # an explicit SnapshotID that agrees is fine, in any case
    again = lay.layout_target(_passport(UUID_A, plane), UUID_A.upper())
    assert again['snapshot_id'] == UUID_A


def test_a_passport_without_a_placement_converts_nothing():
    target = lay.layout_target(_passport(UUID_A))
    assert target['conversion'] == 'none' and target['placement'] is None
    assert target['snapshot_id'] == UUID_A and 'no placement' in \
        target['remark']
    as_text = lay.layout_target(json.dumps(_passport(UUID_C)))
    assert as_text['snapshot_id'] == UUID_C


def test_only_a_snapshot_id_converts_nothing_either():
    target = lay.layout_target(None, UUID_A)
    assert target['snapshot_id'] == UUID_A and target['placement'] is None
    assert target['conversion'] == 'none' and 'no ComponentPassport' in \
        target['remark']
    for empty in ('', '  ', None):
        assert lay.layout_target(empty, UUID_A)['snapshot_id'] == UUID_A
    # nothing at all: the record builder reports the missing id
    assert lay.layout_target()['snapshot_id'] is None


def test_a_snapshot_id_that_disagrees_with_the_passport_is_an_error():
    with pytest.raises(b.BuildError) as info:
        lay.layout_target(_passport(UUID_A, _plane(np.random.default_rng(2))),
                          UUID_C)
    text = str(info.value)
    assert UUID_A in text and UUID_C in text and 'one version' in text


def test_a_bad_passport_or_placement_is_refused():
    with pytest.raises(b.BuildError):
        lay.layout_target('not json')
    with pytest.raises(b.BuildError):
        lay.layout_target({'identity': {}, 'snapshots': [{'_id': 'x'}]})
    skew = {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [1, 1, 0], 'z': [0, 0, 1]}
    with pytest.raises(b.BuildError) as info:
        lay.layout_target(_passport(UUID_A, skew))
    assert 'csc_placement' in str(info.value)


# STORED LAYOUTS (RL11) ---------------------------------------------------------
def _row(record_id, observed_at, snapshot_id=UUID_A, bars=None,
         status='published', basis='drawing'):
    bars = [{'spec': 'BSt III', 'diameter_mm': 8,
             'points': [[0, 0, 0], [100, 0, 0]]}] if bars is None else bars
    return {'_id': record_id, 'method': 'reinforcement_layout',
            'status': status, 'observed_at': observed_at,
            'position': {'kind': 'none', 'snapshot_id': snapshot_id},
            'payload': {'basis': basis, 'bars': bars}}


def test_a_record_is_read_into_bars_with_the_defaults():
    row = _row('r1', '2024-05-03T00:00:00Z', bars=[
        {'diameter_mm': 12, 'points': [[0, 0, 0], [0, 10, 0], [0, 10, 5]]},
        {'spec': 'BSt III', 'diameter_mm': 8.5, 'diameter_known': False,
         'cover_mm': 25, 'points': [[1, 2, 3], [4, 5, 6]]}])
    bars, skipped = lay.bars_of_record(row)
    assert skipped == []
    assert bars[0] == {'spec': None, 'diameter_mm': 12.0,
                       'diameter_known': True, 'cover_mm': None,
                       'points': [(0.0, 0.0, 0.0), (0.0, 10.0, 0.0),
                                  (0.0, 10.0, 5.0)]}
    assert bars[1]['diameter_known'] is False and bars[1]['cover_mm'] == 25.0
    assert bars[1]['spec'] == 'BSt III'


def test_a_bar_that_cannot_be_read_is_skipped_by_index():
    row = _row('r1', '2024-05-03T00:00:00Z', bars=[
        {'diameter_mm': 8, 'points': [[0, 0, 0]]},               # one point
        {'points': [[0, 0, 0], [1, 0, 0]]},                      # no diameter
        {'diameter_mm': 0, 'points': [[0, 0, 0], [1, 0, 0]]},    # zero
        {'diameter_mm': 8, 'points': [[0, 0], [1, 0]]},          # 2D
        'junk',
        {'diameter_mm': 8, 'points': [[0, 0, 0], [1, 0, 0]]}])
    bars, skipped = lay.bars_of_record(row)
    assert len(bars) == 1 and skipped == [0, 1, 2, 3, 4]
    assert lay.bars_of_record({}) == ([], [])
    assert lay.bars_of_record({'payload': {'bars': 'x'}}) == ([], [])


def test_layouts_come_newest_first_and_tombstones_are_left_out():
    rows = [_row('a', '2024-05-03T00:00:00Z'),
            _row('c', '2026-01-01T00:00:00Z', snapshot_id=UUID_C,
                 basis='scan'),
            _row('b', '2025-06-01T00:00:00Z'),
            {'_id': 'gone', 'kind': 'evidence', 'status': 'withdrawn',
             'withdrawn_at': '2026-02-01T00:00:00Z'},
            _row('empty', '2026-03-01T00:00:00Z', bars=[])]
    layouts, skipped = lay.layouts_of(rows)
    assert [item['id'] for item in layouts] == ['c', 'b', 'a']
    assert skipped == ['gone', 'empty']
    first = layouts[0]
    assert first['basis'] == 'scan' and first['snapshot_id'] == UUID_C
    assert first['status'] == 'published' and len(first['bars']) == 1
    assert lay.layouts_of(None) == ([], [])


def test_layouts_of_one_instant_are_ordered_by_id():
    rows = [_row(i, '2025-01-01T00:00:00Z') for i in ('a', 'c', 'b')]
    assert [x['id'] for x in lay.layouts_of(rows)[0]] == ['c', 'b', 'a']


def test_the_layout_of_the_passports_snapshot_is_placed_the_others_warn():
    plane = {'o': [0, 0, 100], 'x': [1, 0, 0], 'y': [0, 1, 0],
             'z': [0, 0, 1]}
    here, there = lay.layouts_of([_row('h', '2025-01-01T00:00:00Z'),
                                  _row('t', '2024-01-01T00:00:00Z',
                                       snapshot_id=UUID_C)])[0]
    points, warning = lay.layout_points(here, plane, UUID_A)
    assert warning is None
    assert points == [[(0.0, 0.0, 100.0), (100.0, 0.0, 100.0)]]
    points, warning = lay.layout_points(there, plane, UUID_A)
    assert points == [[(0.0, 0.0, 0.0), (100.0, 0.0, 0.0)]]      # untouched
    assert UUID_C in warning and UUID_A in warning and 't' in warning
    # without a placement nothing moves and nothing warns
    points, warning = lay.layout_points(there, None, UUID_A)
    assert warning is None and points == [[(0.0, 0.0, 0.0),
                                           (100.0, 0.0, 0.0)]]


def test_the_status_of_a_request():
    assert lay.status_param(None) == 'published'
    assert lay.status_param('  ') == 'published'
    assert lay.status_param('ALL') == 'all'
    assert lay.status_param('Draft') == 'draft'
    with pytest.raises(b.BuildError):
        lay.status_param('maybe')
