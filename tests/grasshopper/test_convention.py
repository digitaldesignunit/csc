"""The user-text convention of the Rhino document (csc_convention): the tag
values a bake writes, the read-back of a moved tag, the D2P type map, and the
refusals for everything that is read from a document (untrusted text)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

from libns import namespace

# the libraries as a component sees them: one namespace, no imports
_NS = namespace(('csc_ply', 'csc_build', 'csc_read', 'csc_convention'))
c = r = SimpleNamespace(**_NS)

UUID_I = '11111111-1111-4111-8111-111111111111'
UUID_S = '22222222-2222-4222-8222-222222222222'
UUID_S2 = '33333333-3333-4333-8333-333333333333'

# a piece lying on its side, off the origin (stored coordinates)
FRAME = {'o': [100.0, 200.0, 300.0], 'x': [0.0, 1.0, 0.0],
         'y': [-1.0, 0.0, 0.0], 'z': [0.0, 0.0, 1.0]}


def _rot_z(degrees, origin):
    a = np.radians(degrees)
    c_, s = np.cos(a), np.sin(a)
    return {'o': list(origin), 'x': [c_, s, 0.0], 'y': [-s, c_, 0.0],
            'z': [0.0, 0.0, 1.0]}


def _passport(snapshot_id=UUID_S, identity_id=UUID_I, frame=FRAME, **extra):
    snapshot = {'_id': snapshot_id, 'name': 'Lintel', 'frame': frame,
                'bbx': [400, 200, 50], 'color': [10, 20, 30]}
    if frame is None:
        del snapshot['frame']
    snapshot.update(extra)
    return {'identity': {'_id': identity_id, 'original_function': 'IfcBeam'},
            'snapshots': [snapshot]}


def _get(values):
    return lambda key: values.get(key)


# PLANES ----------------------------------------------------------------------
def test_a_plane_is_checked_and_cleaned():
    plane = c.check_plane({'o': [1, 2, 3], 'x': [1, 0, 0], 'y': [0, 1, 0],
                           'z': [0, 0, 1], 'extra': 'ignored'})
    assert plane == {'o': [1.0, 2.0, 3.0], 'x': [1.0, 0.0, 0.0],
                     'y': [0.0, 1.0, 0.0], 'z': [0.0, 0.0, 1.0]}


@pytest.mark.parametrize('bad', [
    None, 5, [], 'x', {}, {'o': [0, 0, 0]},
    {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0]},              # no z
    {'o': [0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]},  # 2 numbers
    {'o': [0, 0, 'a'], 'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]},
    {'o': [0, 0, True], 'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]},
    {'o': [0, 0, float('nan')], 'x': [1, 0, 0], 'y': [0, 1, 0],
     'z': [0, 0, 1]},
    {'o': [0, 0, float('inf')], 'x': [1, 0, 0], 'y': [0, 1, 0],
     'z': [0, 0, 1]},
    {'o': [1e12, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]},
    {'o': [0, 0, 0], 'x': [2, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]},  # scaled
    {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [1, 0, 0], 'z': [0, 0, 1]},  # not perp
    {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, -1]},  # mirror
    {'o': [0, 0, 0], 'x': [0, 0, 0], 'y': [0, 0, 0], 'z': [0, 0, 0]},
])
def test_a_bad_plane_is_refused(bad):
    with pytest.raises(c.ConventionError):
        c.check_plane(bad)


@pytest.mark.parametrize('bad', [
    '', '   ', None, 'not json', '[1, 2]', '{"o": 1}', 'null', '{',
    '[' * 5000 + ']' * 5000,                       # deep nesting
    '{"o":[0,0,0],"x":[1,0,0],"y":[0,1,0],"z":[0,0,1],"pad":"' + 'a' * 5000
    + '"}',                                          # over the size cap
])
def test_a_bad_placement_text_is_refused(bad):
    with pytest.raises(c.ConventionError):
        c.parse_placement(bad)


def test_a_placement_text_round_trips():
    plane = _rot_z(33.0, (5.5, -2.25, 1e5))
    again = c.parse_placement(c.placement_text(plane))
    for key in ('o', 'x', 'y', 'z'):
        assert np.allclose(again[key], plane[key], atol=1e-8)
    assert len(c.placement_text(plane)) < c.MAX_PLACEMENT_CHARS


# THE TWO PLANES --------------------------------------------------------------
def test_an_unplaced_piece_stands_in_its_frame_at_the_world_plane():
    passport = _passport()
    placed = c.resolve_placement(passport)
    assert placed == r.canonical_placement(FRAME)
    plane = c.piece_plane(placed, FRAME)
    for key, want in (('o', [0, 0, 0]), ('x', [1, 0, 0]), ('y', [0, 1, 0]),
                      ('z', [0, 0, 1])):
        assert np.allclose(plane[key], want, atol=1e-12)


def test_a_piece_with_its_own_placement_keeps_it():
    own = _rot_z(20.0, (1.0, 2.0, 3.0))
    passport = r.with_placement(_passport(), own)
    assert c.resolve_placement(passport) == r.placement_of(passport)
    assert c.resolve_placement(_passport(frame=None)) is None


@pytest.mark.parametrize('degrees,origin', [(0, (0, 0, 0)), (90, (10, 0, 0)),
                                            (-37.5, (1e3, -2e3, 50.0))])
def test_plane_and_placement_are_inverse_for_any_frame(degrees, origin):
    frame = {'o': [3.0, -4.0, 5.0], 'x': [0.0, 0.0, 1.0],
             'y': [1.0, 0.0, 0.0], 'z': [0.0, 1.0, 0.0]}
    plane = _rot_z(degrees, origin)
    placed = c.placement_from_piece_plane(plane, frame)
    back = c.piece_plane(placed, frame)
    for key in ('o', 'x', 'y', 'z'):
        assert np.allclose(back[key], plane[key], atol=1e-9)


def test_the_canonical_piece_sits_at_the_tag_plane():
    """The document position of a stored point is M(F(point)) with M the
    tag plane: the box centre goes to the plane origin."""
    passport = _passport()
    moved = _rot_z(40.0, (500.0, 600.0, 0.0))
    placed = c.placement_from_piece_plane(moved, FRAME)
    t = r.placement_matrix(placed)                    # stored -> document
    centre = r.apply_matrix([FRAME['o']], t)[0]
    assert np.allclose(centre, moved['o'], atol=1e-9)
    # an axis of the frame (here frame x) ends up on the plane's x axis
    tip = r.apply_matrix([np.add(FRAME['o'], FRAME['x'])], t)[0]
    assert np.allclose(tip - centre, moved['x'], atol=1e-9)
    assert passport                                   # (unused fixture)


# WRITING ---------------------------------------------------------------------
def test_the_tag_values_carry_ids_plane_and_optionally_the_passport():
    passport = _passport()
    values = c.tag_values(passport)
    assert set(values) == {c.KEY_IDENTITY, c.KEY_SNAPSHOT, c.KEY_PLACEMENT}
    assert values[c.KEY_IDENTITY] == UUID_I
    assert values[c.KEY_SNAPSHOT] == UUID_S
    assert c.parse_placement(values[c.KEY_PLACEMENT])['o'] == [0.0] * 3
    full = c.tag_values(passport, with_passport=True)
    assert json.loads(full[c.KEY_COMPONENT])['identity']['_id'] == UUID_I
    assert all(isinstance(v, str) for v in full.values())


def test_the_part_values_are_the_two_ids_only():
    assert c.part_values(_passport()) == {c.KEY_IDENTITY: UUID_I,
                                          c.KEY_SNAPSHOT: UUID_S}


@pytest.mark.parametrize('passport', [
    _passport(snapshot_id='not-a-uuid'), _passport(identity_id='../x'),
    {'identity': {}, 'snapshots': [{}]}, 'nope'])
def test_a_passport_without_ids_cannot_be_written(passport):
    with pytest.raises(c.ConventionError):
        c.part_values(passport)


def test_a_passport_without_a_frame_cannot_be_written():
    with pytest.raises(c.ConventionError, match='no frame'):
        c.tag_values(_passport(frame=None))


# READING ---------------------------------------------------------------------
def test_an_object_without_the_identity_key_is_not_a_piece():
    assert c.read_tags(_get({})) is None
    assert c.read_tags(_get({c.KEY_IDENTITY: ''})) is None
    assert c.read_tags(_get({c.KEY_SNAPSHOT: UUID_S})) is None


def test_tags_read_back_what_was_written():
    passport = _passport()
    tags = c.read_tags(_get(c.tag_values(passport, with_passport=True)))
    assert tags['problems'] == []
    assert tags['identity_id'] == UUID_I and tags['snapshot_id'] == UUID_S
    assert tags['placement'] is not None
    assert tags['passport']['snapshots'][0]['_id'] == UUID_S


def test_ids_are_normalised_and_bad_ones_are_reported():
    tags = c.read_tags(_get({c.KEY_IDENTITY: ' ' + UUID_I.upper() + ' ',
                             c.KEY_SNAPSHOT: UUID_S}))
    assert tags['identity_id'] == UUID_I
    tags = c.read_tags(_get({c.KEY_IDENTITY: '../../admin',
                             c.KEY_SNAPSHOT: UUID_S + '/x'}))
    assert tags['identity_id'] is None and tags['snapshot_id'] is None
    assert len(tags['problems']) == 2


def test_bad_values_are_reported_and_left_out():
    tags = c.read_tags(_get({
        c.KEY_IDENTITY: UUID_I, c.KEY_SNAPSHOT: UUID_S,
        c.KEY_PLACEMENT: '{"o": "nope"}',
        c.KEY_COMPONENT: '{"identity": 5}'}))
    assert tags['placement'] is None and tags['passport'] is None
    assert len(tags['problems']) == 2
    huge = c.read_tags(_get({
        c.KEY_IDENTITY: UUID_I, c.KEY_SNAPSHOT: UUID_S,
        c.KEY_COMPONENT: 'x' * (c.MAX_COMPONENT_CHARS + 1)}))
    assert huge['passport'] is None
    assert any('too long' in p for p in huge['problems'])


def test_a_snapshot_is_picked_by_its_id():
    passport = _passport()
    passport['snapshots'].append({'_id': UUID_S2, 'frame': FRAME})
    picked = c.select_snapshot(passport, UUID_S2)
    assert [s['_id'] for s in picked['snapshots']] == [UUID_S2, UUID_S]
    assert c.select_snapshot(passport, UUID_I) is None
    assert c.select_snapshot('nope', UUID_S) is None


# THE ROUND TRIP --------------------------------------------------------------
@pytest.mark.parametrize('own', [None, _rot_z(25.0, (7.0, 8.0, 9.0))])
def test_a_moved_tag_gives_the_moved_placement_back(own):
    base = _passport()
    if own:
        base = r.with_placement(base, own)
    passport = c.load_passport(base)
    tags = c.read_tags(_get(c.tag_values(passport, with_passport=True)))
    # unmoved: the placement the piece was drawn with comes back exactly
    again, problems = c.passport_for_tags(
        tags, c.parse_placement(c.placement_text(
            c.piece_plane(c.resolve_placement(passport), FRAME))))
    assert problems == []
    want = c.resolve_placement(passport)
    for key in ('o', 'x', 'y', 'z'):
        assert np.allclose(r.placement_of(again)[key], want[key], atol=1e-8)
    # the user rotates and moves the piece: the tag plane moves with it
    move = r.placement_matrix(_rot_z(70.0, (1000.0, -500.0, 20.0)))
    plane_now = c._plane_of_matrix(
        move @ r.placement_matrix(c.piece_plane(want, FRAME)))
    moved, problems = c.passport_for_tags(tags, plane_now)
    assert problems == []
    got = r.placement_matrix(r.placement_of(moved))
    assert np.allclose(got, move @ r.placement_matrix(want), atol=1e-8)


def test_the_passport_comes_from_the_tag_or_from_the_fetch():
    passport = _passport()
    plane = c.piece_plane(c.resolve_placement(passport), FRAME)
    tags_with = c.read_tags(_get(c.tag_values(passport, with_passport=True)))
    tags_without = c.read_tags(_get(c.tag_values(passport)))
    calls = []

    def fetch(identity_id, snapshot_id):
        calls.append((identity_id, snapshot_id))
        return passport

    again, _ = c.passport_for_tags(tags_with, plane, fetch)
    assert again is not None and calls == []           # no network needed
    again, problems = c.passport_for_tags(tags_without, plane, fetch)
    assert again is not None and calls == [(UUID_I, UUID_S)]
    nothing, problems = c.passport_for_tags(tags_without, plane)
    assert nothing is None and any('no passport' in p for p in problems)


def test_a_fetch_that_fails_or_answers_wrongly_gives_no_piece():
    passport = _passport()
    plane = c.piece_plane(c.resolve_placement(passport), FRAME)
    tags = c.read_tags(_get(c.tag_values(passport)))

    def boom(identity_id, snapshot_id):
        raise RuntimeError('offline')

    none, problems = c.passport_for_tags(tags, plane, boom)
    assert none is None and any('offline' in p for p in problems)
    other = _passport(snapshot_id=UUID_S2)
    none, problems = c.passport_for_tags(tags, plane, lambda i, s: other)
    assert none is None
    stranger = _passport(identity_id=UUID_S2)
    none, _ = c.passport_for_tags(tags, plane, lambda i, s: stranger)
    assert none is None
    none, _ = c.passport_for_tags(tags, plane, lambda i, s: None)
    assert none is None


def test_a_component_text_naming_another_piece_is_ignored():
    """The passport on a tag must hold the tag's own ids: a pasted text of
    another identity cannot make a piece say it is somebody else."""
    stranger = _passport(identity_id=UUID_S2)
    values = c.tag_values(_passport())
    values[c.KEY_COMPONENT] = json.dumps(stranger)
    tags = c.read_tags(_get(values))
    plane = c.parse_placement(values[c.KEY_PLACEMENT])
    own = _passport()
    got, problems = c.passport_for_tags(tags, plane, lambda i, s: own)
    assert got['identity']['_id'] == UUID_I
    assert any('csc_component does not hold' in p for p in problems)
    got, _ = c.passport_for_tags(tags, plane)
    assert got is None


def test_a_piece_without_a_frame_is_not_rebuilt_and_a_bad_plane_is_refused():
    passport = _passport()
    tags = c.read_tags(_get(c.tag_values(passport, with_passport=True)))
    tags['passport'] = c.load_passport(_passport(frame=None))
    got, problems = c.passport_for_tags(
        tags, c.parse_placement(c.placement_text(r.canonical_placement(
            FRAME))))
    assert got is None and any('no frame' in p for p in problems)
    tags = c.read_tags(_get(c.tag_values(passport, with_passport=True)))
    got, problems = c.passport_for_tags(tags, {'o': [0, 0, 0]})
    assert got is None and any('tag plane' in p for p in problems)


def test_a_tag_without_valid_ids_gives_no_piece():
    tags = c.read_tags(_get({c.KEY_IDENTITY: 'bad', c.KEY_SNAPSHOT: UUID_S}))
    got, problems = c.passport_for_tags(tags, r.canonical_placement(FRAME))
    assert got is None and problems


def test_the_library_is_one_namespace_with_csc_read():
    """csc_convention runs after csc_read in a component (no import)."""
    ns = namespace(('csc_ply', 'csc_build', 'csc_read', 'csc_convention'))
    assert ns['KEY_PLACEMENT'] == 'csc_placement'
    assert ns['PLACEMENT_KEY'] == 'csc_placement'


# D2P TYPES -------------------------------------------------------------------
def test_every_original_function_has_its_own_two_letter_d2p_id():
    functions = list(c.VOCAB['original_function'])
    ids = [c.d2p_type_id(f) for f in functions]
    assert all(len(i) == 2 and i.isalpha() and i.isupper() for i in ids)
    assert set(c.D2P_TYPE_IDS) == set(functions)
    # a debris class shares nothing with the fallback of an unknown type
    assert c.d2p_type_id('CscDebris') == 'RB'
    unique = [i for f, i in zip(functions, ids)
              if f != 'IfcBuildingElementProxy']
    assert len(set(unique)) == len(unique)


@pytest.mark.parametrize('value', [None, '', 'IfcSomethingNew', 'panel', 5])
def test_an_unknown_or_missing_type_falls_back(value):
    assert c.d2p_type_id(value) == c.D2P_FALLBACK_ID == 'OT'
    assert c.d2p_type_name(None) == 'Other'


def test_type_names_read_well():
    assert c.d2p_type_name('IfcPipeSegment') == 'Pipe Segment'
    assert c.d2p_type_name('IfcBeam') == 'Beam'
    assert c.d2p_type_name('CscDebris') == 'Debris'
    assert c.d2p_type_name(None) == 'Other'
    assert c.d2p_type_name('IfcBuildingElementProxy') == \
        'Building Element Proxy'
