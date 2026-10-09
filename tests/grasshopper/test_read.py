"""The read-side helpers (csc_read): passports, frames, proxies, filters."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from csc_gh import read as r

BACKEND = Path(__file__).resolve().parents[2] / 'src' / 'backend'

FRAME = {'o': [10, 20, 30], 'x': [0, 1, 0], 'y': [-1, 0, 0], 'z': [0, 0, 1]}


def _passport(**snapshot):
    snap = {'_id': 's1', 'name': 'Lintel', 'frame': FRAME,
            'bbx': [400, 200, 50], 'complexity': 1, 'fragment': False,
            'shape_class': 'linear', 'properties': {}}
    snap.update(snapshot)
    return {'identity': {'_id': 'i1', 'original_function': 'IfcBeam',
                         'material': 'concrete', 'dataset': 'ds',
                         'material_class': '17 01 01'},
            'snapshots': [snap]}


# PASSPORT --------------------------------------------------------------------
def test_a_passport_loads_from_text_or_dict_and_legacy_rows():
    passport = _passport()
    assert r.load_passport(json.dumps(passport))['snapshots'][0]['_id'] == 's1'
    assert r.load_passport(passport) is not None
    legacy = {'identity': passport['identity'],
              'snapshot': passport['snapshots'][0]}
    assert r.load_passport(legacy)['snapshots'][0]['_id'] == 's1'
    for bad in ('nope', '[]', {'identity': 1}, {'identity': {}}, None, 5):
        assert r.load_passport(bad) is None
    identity, snapshot = r.parts(json.dumps(passport))
    assert identity['_id'] == 'i1' and snapshot['name'] == 'Lintel'
    assert r.parts('x') == (None, None)


def _prop(*values):
    return {'range': list(values)}


def test_condition_grade_follows_the_web_badge():
    assert r.condition_grade({}) is None
    assert r.condition_grade({'properties': {
        'condition_grade': _prop(3, 2)}}) == 2           # the lowest end
    assert r.condition_grade({'properties': {
        'condition_grade': _prop(1)}}) == 1
    assert r.condition_grade({'properties': {
        'spalling': _prop(1, 2), 'cracking': _prop(0)}}) == 1   # 3 - 2
    assert r.condition_grade({'properties': {'corrosion': _prop(3)}}) == 0
    assert r.condition_grade({'properties': {
        'condition_grade': _prop(3), 'spalling': _prop(3)}}) == 3
    assert r.condition_grade({'properties': {
        'condition_grade': {'range': ['x']}}}) is None
    assert r.condition_grade({'properties': {'spalling': _prop(0)}}) == 3


def test_capture_markers_keep_label_and_role():
    snapshot = {'capture': {'markers': [
        {'label': 'a', 'role': 'rig', 'point': [1, 2, 3]},
        {'label': 'b', 'role': 'component', 'point': [4, 5]}]}}
    assert r.capture_markers(snapshot) == [('a', 'rig', (1.0, 2.0, 3.0))]
    assert r.capture_markers({}) == []


# FRAMES AND PLACEMENT --------------------------------------------------------
def test_frame_matrices_are_rigid_and_inverse():
    placement = r.placement_matrix(FRAME)
    canonical = r.canonical_matrix(FRAME)
    assert np.allclose(placement @ canonical, np.eye(4), atol=1e-12)
    points = np.array([[10, 20, 30], [11, 22, 33], [0, 0, 0.0]])
    moved = r.apply_matrix(points, canonical)
    assert np.allclose(moved[0], 0)                  # the frame origin
    assert np.allclose(moved[1], [2, -1, 3])         # along y is x now
    assert np.allclose(r.apply_matrix(moved, placement), points)
    assert r.matrix_rows(np.eye(4))[3] == [0.0, 0.0, 0.0, 1.0]


def test_the_canonical_placement_is_the_world_plane_moved():
    plane = r.canonical_placement(FRAME)
    canonical = r.canonical_matrix(FRAME)
    # the placement matrix of that plane is the canonical matrix itself
    assert np.allclose(r.placement_matrix(plane), canonical)
    assert r.frame_ok(plane)


def test_the_placement_key_lives_in_the_passport_only():
    passport = _passport()
    assert r.PLACEMENT_KEY == 'csc_placement'
    assert r.placement_of(passport) is None
    placed = r.with_placement(passport, FRAME)
    assert r.placement_of(placed) == {k: [float(v) for v in FRAME[k]]
                                      for k in 'oxyz'}
    assert 'csc_placement' not in passport['snapshots'][0]   # a copy
    assert r.placement_of(json.dumps(placed)) is not None
    with pytest.raises(ValueError):
        r.with_placement(passport, {'o': [0, 0, 0]})
    with pytest.raises(ValueError):
        r.with_placement('x', FRAME)


def test_box_of_needs_frame_and_extents():
    frame, size = r.box_of(_passport()['snapshots'][0])
    assert frame == FRAME and size == [400.0, 200.0, 50.0]
    assert r.box_of({'frame': FRAME}) is None
    assert r.box_of({'bbx': [1, 2, 3]}) is None
    assert r.box_of({'frame': {'o': 1}, 'bbx': [1, 2, 3]}) is None


# PROXIES ---------------------------------------------------------------------
def _proxy(kind, params, **extra):
    placement = {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0],
                 'z': [0, 0, 1]}
    return {'primitive': kind, 'role': 'primary', 'params': params,
            'placement': placement, 'fit': {'method': 'authored'}, **extra}


@pytest.mark.parametrize('kind, params, expected', [
    ('box', {'size': [1, 2, 3]}, True),
    ('box', {'size': [1, 2, 0]}, False),
    ('box', {'size': [1, 2]}, False),
    ('prism', {'profile': [[0, 0], [1, 0], [1, 1]], 'height': 2}, True),
    ('prism', {'profile': [[0, 0], [1, 0]], 'height': 2}, False),
    ('prism', {'profile': [[0, 0], [1, 0], [1, 1]], 'height': -1}, False),
    ('cylinder', {'radius': 1, 'height': 2}, True),
    ('cylinder', {'radius': 0, 'height': 2}, False),
    ('hull', {'vertices': [[0, 0, 0]] * 4, 'faces': [[0, 1, 2]] * 4}, True),
    ('hull', {'vertices': [[0, 0, 0]] * 3, 'faces': [[0, 1, 2]] * 4}, False),
    ('sphere', {}, False),
])
def test_which_proxies_are_drawable(kind, params, expected):
    assert r.drawable_proxy(_proxy(kind, params)) is expected


def test_a_proxy_without_a_frame_is_not_drawable():
    proxy = _proxy('box', {'size': [1, 2, 3]})
    proxy['placement'] = {'o': [0, 0, 0]}
    assert not r.drawable_proxy(proxy)
    assert not r.drawable_proxy(None)


def test_authored_only_and_the_drawable_list():
    box = _proxy('box', {'size': [1, 2, 3]})
    fitted = _proxy('cylinder', {'radius': 1, 'height': 2})
    fitted['fit'] = {'method': 'ransac'}
    assert r.authored_only({'geometry': {'proxies': [box]}})
    assert not r.authored_only({'geometry': {'proxies': [fitted]}})
    assert not r.authored_only({'geometry': {'meshes': [{}], 'proxies': [box]}})
    assert not r.authored_only({'geometry': {'point_clouds': [{}],
                                             'proxies': [box]}})
    assert not r.authored_only({})
    listed = r.drawable_proxies({'geometry': {'proxies': [
        {'primitive': 'box', 'params': {}}, box, fitted]}})
    assert [i for i, _ in listed] == [1, 2]


def test_proxy_points_equal_the_servers_meshes():
    sys.path.insert(0, str(BACKEND))
    try:
        from apps.catalog.proxies.primitives import proxy_mesh
    except Exception as error:   # the client-only stack
        pytest.skip('backend stack not importable here: %s' % error)
    rot = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1.0]])
    placement = {'o': [5, 6, 7], 'x': list(rot[:, 0]), 'y': list(rot[:, 1]),
                 'z': list(rot[:, 2])}
    cases = [
        ('box', {'size': [4, 6, 8]}),
        ('prism', {'profile': [[0, 0], [10, 0], [10, 4], [0, 4]],
                   'height': 3}),
        ('cylinder', {'radius': 5, 'height': 9}),
        ('hull', {'vertices': [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
                  'faces': [[0, 2, 1], [0, 1, 3], [1, 2, 3], [0, 3, 2]]}),
    ]
    for kind, params in cases:
        proxy = _proxy(kind, params)
        proxy['placement'] = placement
        ours = r.proxy_points(proxy)
        theirs = np.asarray(proxy_mesh(proxy).vertices)
        assert np.allclose(ours.min(axis=0), theirs.min(axis=0), atol=0.5), kind
        assert np.allclose(ours.max(axis=0), theirs.max(axis=0), atol=0.5), kind
    assert len(r.proxy_points({'primitive': 'sphere'})) == 0


def test_passport_points_prefer_the_preview_over_proxies():
    mesh = {'vertices': [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            'faces': [[0, 1, 2]]}
    box = _proxy('box', {'size': [2, 2, 2]})
    assert len(r.passport_points({'geometry': {'meshes': [mesh],
                                               'proxies': [box]}})) == 3
    assert len(r.passport_points({'geometry': {
        'point_clouds': [{'points': [[0, 0, 0]] * 5}]}})) == 5
    assert len(r.passport_points({'geometry': {'proxies': [box]}})) == 8
    assert len(r.passport_points({})) == 0


# FILTERS ---------------------------------------------------------------------
def test_the_fetch_filter_params_are_the_servers():
    params = r.fetch_filter_params(
        original_function=' IfcBeam ', material='concrete', dataset='ds',
        complexity=2, fragment=True, reserved=1, shape_class='linear',
        material_class='17 01 01', circulation='all',
        bbx={'min_x': 100, 'max_x': 0, 'min_z': None, 'max_y': 50.5})
    assert params == {
        'original_function': 'IfcBeam', 'material': 'concrete',
        'dataset': 'ds', 'shape_class': 'linear',
        'material_class': '17 01 01', 'circulation': 'all', 'complexity': 2,
        'fragment': 'true', 'reserved': 'true', 'bbx_min_x': 100,
        'bbx_max_y': 50.5}
    assert r.fetch_filter_params() == {}
    assert r.fetch_filter_params(reserved=-1, fragment=False,
                                 original_function='') == {
        'fragment': 'false'}
    # every key is a query parameter of GET /identities
    sys.path.insert(0, str(BACKEND))
    try:
        from apps.catalog.api.identity_filters import catalog_filters
    except Exception as error:
        return
    import inspect
    accepted = set(inspect.signature(catalog_filters).parameters)
    assert set(params) <= accepted


def test_passes_filters():
    passport = _passport()
    assert r.passes_filters(passport)
    assert r.passes_filters(passport, original_function='ifcbeam',
                            material='Concrete', dataset='DS',
                            complexity=1, fragment=False,
                            shape_class='linear', material_class='17 01 01')
    for bad in (dict(original_function='IfcColumn'), dict(material='steel'),
                dict(dataset='x'), dict(complexity=2), dict(fragment=True),
                dict(shape_class='planar'),
                dict(material_class='17 02 01')):
        assert not r.passes_filters(passport, **bad), bad
    assert r.passes_filters(passport, bbx={'min_x': 300, 'max_x': 500})
    assert not r.passes_filters(passport, bbx={'min_x': 500})
    assert not r.passes_filters(passport, bbx={'max_z': 40})
    assert r.passes_filters(passport, bbx={'min_x': 0, 'max_x': 0})
    # a piece whose complexity the runner has not derived yet does not match
    pending = _passport(complexity=None)
    assert not r.passes_filters(pending, complexity=1)
    assert r.passes_filters(pending)
    assert not r.passes_filters('nope')
