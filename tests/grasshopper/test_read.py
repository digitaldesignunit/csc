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


# DIMENSION AND NEAR SEARCH (8.169, 8.170) ------------------------------------
class _Xyz:
    """What a Rhino Point3d / Vector3d is to the helpers: X, Y, Z."""

    def __init__(self, x, y, z=0.0):
        self.X, self.Y, self.Z = x, y, z


class _Xy:
    def __init__(self, x, y):
        self.X, self.Y = x, y


def test_the_fit_size_takes_three_numbers_in_any_form():
    want = '1200,600,200'
    assert r.fit_size_of([1200, 600, 200]) == want
    assert r.fit_size_of((1200.0, 600.0, 200.0)) == want
    assert r.fit_size_of(_Xyz(1200, 600, 200)) == want            # Point3d / Vector3d
    assert r.fit_size_of('1200, 600, 200') == want
    assert r.fit_size_of('1200;600;200') == want
    assert r.fit_size_of(' 1200 600 200 ') == want
    assert r.fit_size_of([1200.5, 600, 200]) == '1200.5,600,200'
    for bad in ([1200, 600], [1, 2, 3, 4], 'a,b,c', '1200,600', [0, 1, 2], [-5, 10, 10],
                [1e9, 1, 1], None, '', [True, 1, 1], [float('nan'), 1, 1], 5):
        with pytest.raises(ValueError):
            r.fit_size_of(bad)


def test_the_fit_tolerance_is_a_percent_or_millimetres_as_the_server_reads_it():
    assert r.fit_tolerance_of('10%') == '10%'
    assert r.fit_tolerance_of(' 7.5 % ') == '7.5%'
    assert r.fit_tolerance_of('50mm') == '50mm'
    assert r.fit_tolerance_of('50 MM') == '50mm'
    assert r.fit_tolerance_of(10) == '10%'                        # a bare number is per cent
    assert r.fit_tolerance_of('12,5') == '12.5%'
    assert r.fit_tolerance_of(None) is None and r.fit_tolerance_of(' ') is None
    for bad in ('ten', '10 m', '101%', '1e9mm', -5, '%', True):
        with pytest.raises(ValueError):
            r.fit_tolerance_of(bad)


def test_the_fit_params_follow_the_mode():
    assert r.fit_params(None, None, None) == {}
    assert r.fit_params('about', [1200, 600, 200], None) == {
        'fit_mode': 'about', 'fit_size': '1200,600,200', 'fit_tol': '10%'}
    assert r.fit_params('About', [1200, 600, 200], '50mm')['fit_tol'] == '50mm'
    # can hold takes no tolerance: it is left out, not sent (the server answers 422)
    assert r.fit_params('Can hold', [1200, 600, 200], '5%') == {
        'fit_mode': 'can_hold', 'fit_size': '1200,600,200'}
    assert r.fit_params('can-hold', [1, 2, 3], None)['fit_mode'] == 'can_hold'
    for args in (('hold', [1, 2, 3], None), (None, [1, 2, 3], None), ('about', [1, 2], None),
                 ('about', [0, 600, 200], None), ('about', [-5, 600, 200], None),
                 ('about', [1e9, 1, 1], None), ('about', [0, 0, 5], None), ('about', [1, 2], '10%')):
        with pytest.raises(ValueError):
            r.fit_params(*args)


def test_the_near_point_is_latitude_then_longitude_as_in_origin():
    assert r.near_point_of(_Xyz(49.8728, 8.6512)) == (49.8728, 8.6512)   # X = lat, Y = lon
    assert r.near_point_of(_Xy(49.8728, 8.6512)) == (49.8728, 8.6512)
    assert r.near_point_of([49.8728, 8.6512]) == (49.8728, 8.6512)
    assert r.near_point_of('49.8728, 8.6512') == (49.8728, 8.6512)
    assert r.near_point_of('52.5 13.4') == (52.5, 13.4)
    for bad in ('49.87', [1, 2, 3], '91, 0', [0, 181], 'a, b', 7, [None, 1]):
        with pytest.raises(ValueError):
            r.near_point_of(bad)


def test_the_near_params_name_the_layer_and_the_radius():
    assert r.near_params(None, None, None) == {}
    assert r.near_params('', '', '') == {}
    assert r.near_params(_Xyz(49.8728, 8.6512), None, None) == {
        'near_lat': '49.8728', 'near_lon': '8.6512'}
    assert r.near_params([49.8728, 8.6512], 'Origin', 25) == {
        'near_lat': '49.8728', 'near_lon': '8.6512', 'near_layer': 'origin',
        'radius_km': '25'}
    assert 'radius_km' not in r.near_params([1, 2], 'current', 0)       # empty or 0 = nearest
    assert r.near_params([1, 2], None, 2.5)['radius_km'] == '2.5'
    for args in (([1, 2], 'garden', None), ([1, 2], None, -1), ([1, 2], None, 'far'),
                 (None, 'origin', None), (None, None, 30), ([200, 2], None, None)):
        with pytest.raises(ValueError):
            r.near_params(*args)


def test_the_filter_params_carry_the_fit_and_the_near_search():
    params = r.fetch_filter_params(
        material='concrete', fit_mode='about', fit_size=_Xyz(1200, 600, 200),
        fit_tolerance='5%', near_point=_Xyz(49.8728, 8.6512), near_layer='origin',
        radius_km=30)
    assert params == {
        'material': 'concrete', 'fit_mode': 'about', 'fit_size': '1200,600,200',
        'fit_tol': '5%', 'near_lat': '49.8728', 'near_lon': '8.6512',
        'near_layer': 'origin', 'radius_km': '30'}
    with pytest.raises(ValueError):
        r.fetch_filter_params(fit_size=[1, 2, 3])
    # the keys are query parameters of the server, and the server reads the values
    sys.path.insert(0, str(BACKEND))
    try:
        from apps.catalog.api.identity_filters import catalog_filters, _parse_fit
        from apps.catalog.api.near_search import parse_near
    except Exception:
        return
    import inspect
    assert set(params) <= set(inspect.signature(catalog_filters).parameters)
    for mode, tolerance in (('about', '5%'), ('about', '50mm'), ('can_hold', None)):
        got = r.fit_params(mode, [1200, 600, 200.5], tolerance)
        fit = _parse_fit(got['fit_mode'], got['fit_size'], got.get('fit_tol'))
        assert fit['fit_mode'] == mode and sorted(fit['fit_sides']) == [200.5, 600.0, 1200.0]
    near = r.near_params(_Xyz(49.8728, 8.6512), 'origin', 30)
    assert parse_near(float(near['near_lat']), float(near['near_lon']), near['near_layer'],
                      float(near['radius_km']))


def test_a_row_gives_its_fit_in_percent_and_its_distance_in_km():
    assert r.fit_percent({'fit': {'mode': 'about', 'deviation': 0.08}}) == pytest.approx(8.0)
    assert r.fit_percent({'fit': {'mode': 'can_hold', 'waste_mm3': 5e7, 'waste_percent': 41.5}}) == 41.5
    assert r.fit_percent({}) is None and r.fit_percent({'fit': None}) is None
    assert r.fit_percent({'fit': {'mode': 'about'}}) is None
    assert r.distance_km({'distance_m': 12500.0}) == 12.5
    assert r.distance_km({}) is None and r.distance_km(None) is None


# SIMILAR SEARCH (8.174) ------------------------------------------------------
def test_the_similar_basis_and_count():
    assert r.similar_basis(None) == 'radial_signature' and r.similar_basis(' ') == 'radial_signature'
    assert r.similar_basis('Scalars') == 'scalars' and r.similar_basis('hks') == 'hks'
    with pytest.raises(ValueError):
        r.similar_basis('tsne')
    assert r.similar_count(None) == (10, None)
    assert r.similar_count(6) == (6, None) and r.similar_count('25') == (25, None)
    assert r.similar_count(0) == (10, None) and r.similar_count(0.0) == (10, None)
    assert r.similar_count(-3) == (1, 'Count raised to 1')
    assert r.similar_count(500) == (50, 'Count lowered to the most the server gives, 50')
    with pytest.raises(ValueError):
        r.similar_count('many')


def test_the_similar_params_are_the_filters_plus_basis_and_count():
    filters = r.fetch_filter_params(material='concrete', reserved=1, fit_mode='can_hold',
                                    fit_size=[1200, 600, 200])
    params, note = r.similar_params(filters, 'scalars', 5)
    assert params == {'material': 'concrete', 'fit_mode': 'can_hold', 'fit_size': '1200,600,200',
                      'basis': 'scalars', 'count': 5} and note is None   # reserved is not a similar filter
    assert r.similar_params({}, None, None)[0] == {'basis': 'radial_signature', 'count': 10}
    assert r.similar_params(None, None, 99)[1]
    sys.path.insert(0, str(BACKEND))
    try:
        import inspect
        from apps.catalog.api.identity_filters import catalog_filters
        from apps.catalog.api import catalog_list
    except Exception:
        return
    route = inspect.signature(catalog_list.get_similar_identities).parameters
    assert {'basis', 'count'} <= set(route)
    assert set(params) - {'basis', 'count'} <= set(inspect.signature(catalog_filters).parameters)


def test_the_similar_results_keep_the_order_and_the_extra_numbers():
    body = {'query_id': 'q', 'results': [
        {'distance': 0.5, 'piece': {'_id': 'a', 'fit': {'mode': 'about', 'deviation': 0.1},
                                    'distance_m': 2000}},
        {'distance': 1.25, 'piece': {'_id': 'b'}},
        {'distance': 2.0, 'piece': {}},
    ]}
    assert r.similar_results(body) == [
        {'id': 'a', 'distance': 0.5, 'fit': pytest.approx(10.0), 'distance_km': 2.0},
        {'id': 'b', 'distance': 1.25, 'fit': None, 'distance_km': None}]
    assert r.similar_results({}) == [] and r.similar_results(None) == []


def test_the_similar_errors_are_said_in_words():
    assert 'not visible' in r.similar_error_text(404)
    assert 'not built' in r.similar_error_text(409)
    assert 'no descriptor' in r.similar_error_text(422)
    assert 'size' in r.similar_error_text(422, 'fit_mode needs size')
    assert r.similar_error_text(500) == ''


# AN EMPTY OR ZERO SIZE AND POINT ARE "NOT SET" ---------------------------------
ZERO_SIZES = ['0,0,0', '0, 0, 0', '0 0 0', [0, 0, 0], (0.0, 0.0, 0.0), [0, 0], [0], [0, 0, 0, 0],
              _Xyz(0, 0, 0), [_Xyz(0, 0, 0)], ' 0,0,0 ', [], '', None]
ZERO_POINTS = ['0,0', '0, 0', '0 0', [0, 0], (0.0, 0.0), [0, 0, 0], _Xyz(0, 0, 0), _Xy(0, 0),
               [_Xyz(0, 0, 0)], [], '', None]


@pytest.mark.parametrize('size', ZERO_SIZES)
def test_a_zero_or_empty_size_is_no_fit_search(size):
    # without a mode: silent
    notes = []
    assert r.fit_params(None, size, None, notes) == {} and notes == []
    assert r.fit_params('', size, '10%', notes) == {} and notes == []
    # with a mode: no search, no error, and a remark for the component
    for mode in ('about', 'can_hold', 'Can hold'):
        notes = []
        assert r.fit_params(mode, size, '10%', notes) == {}
        assert notes == ['FitMode is set but FitSize is empty or zero: no dimension search']
    # no notes list given: the same, without the remark
    assert r.fit_params('about', size, None) == {}


def test_a_size_that_is_set_but_wrong_is_still_an_error():
    for bad in ([1200, 600], [1200], [0, 600, 200], [1200, 0, 200], [-1200, 600, 200], [1e9, 600, 200],
                [0, 0, 200], 'a,b,c', '1200,600', _Xyz(1200, 600, 0), _Xyz(0, 600, 200)):
        for mode in ('about', 'can_hold'):
            with pytest.raises(ValueError):
                r.fit_params(mode, bad, None)
        with pytest.raises(ValueError):
            r.fit_params(None, bad, None)                      # and a size without a mode


@pytest.mark.parametrize('point', ZERO_POINTS)
def test_a_zero_or_empty_point_is_no_near_search(point):
    assert r.near_params(point, None, None) == {}
    assert r.near_params(point, '', '') == {}
    assert r.near_params(point, None, 0) == {}                  # radius 0 is empty too
    # a layer or a radius alone still follows the existing rule: an error
    for layer, radius in (('origin', None), ('current', None), (None, 30), ('origin', 30)):
        with pytest.raises(ValueError):
            r.near_params(point, layer, radius)


def test_a_point_with_one_zero_coordinate_is_a_real_point():
    assert r.near_params(_Xyz(0, 8.65), None, None) == {'near_lat': '0', 'near_lon': '8.65'}
    assert r.near_params([49.87, 0], 'origin', None) == {
        'near_lat': '49.87', 'near_lon': '0', 'near_layer': 'origin'}


def test_the_filter_params_carry_the_remarks_of_the_inputs_left_out():
    params = r.fetch_filter_params(material='concrete', fit_mode='about', fit_size=_Xyz(0, 0, 0),
                                   near_point=_Xyz(0, 0, 0))
    assert params == {'material': 'concrete'}                    # still a plain dict for the query
    assert isinstance(params, dict) and params.notes == [r.FIT_SIZE_EMPTY]
    assert r.fetch_filter_params(fit_size=[0, 0, 0], near_point=[0, 0]).notes == []
    assert r.fetch_filter_params().notes == []
    ok = r.fetch_filter_params(fit_mode='about', fit_size=[1200, 600, 200])
    assert ok.notes == [] and ok['fit_mode'] == 'about'


def test_the_similar_params_hand_the_remarks_on_in_the_note():
    filters = r.fetch_filter_params(fit_mode='can_hold', fit_size=_Xyz(0, 0, 0))
    params, note = r.similar_params(filters, None, None)
    assert params == {'basis': 'radial_signature', 'count': 10}
    assert note == r.FIT_SIZE_EMPTY
    params, note = r.similar_params(filters, None, 500)
    assert note == 'Count lowered to the most the server gives, 50; ' + r.FIT_SIZE_EMPTY
    assert r.similar_params(r.fetch_filter_params(), None, None)[1] is None
    assert r.similar_params({}, None, None)[1] is None
