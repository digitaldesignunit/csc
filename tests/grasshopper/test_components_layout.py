"""The components of phase C outside Grasshopper (compstub): the Me input of
Actor, the passport and link inputs of ReinforcementLayout, and
FetchReinforcementLayout over a fake Session core."""

from __future__ import annotations

import json
import types

import numpy as np
import pytest

import compstub
from csc_gh import build as b
from csc_gh import layout as lay
from test_upload import FakeCore, Response

UUID_A = '11111111-1111-4111-8111-111111111111'      # a snapshot
UUID_B = '22222222-2222-4222-8222-222222222222'      # an identity
UUID_C = '33333333-3333-4333-9333-333333333333'      # another snapshot
UUID_U = '44444444-4444-4444-8444-444444444444'      # an account

PLANE = {'o': [100.0, 200.0, 300.0], 'x': [0.0, 1.0, 0.0],
         'y': [-1.0, 0.0, 0.0], 'z': [0.0, 0.0, 1.0]}
PROFILE = {'_id': UUID_U, 'username': 'ada', 'full_name': 'Ada Lovelace',
           'organization': 'Lab GmbH',
           'organization_ror': 'https://ror.org/02mhbdp94',
           'orcid': '0000-0002-1825-0097', 'default_role': 'laboratory',
           'role': 'user', 'memberships': [], 'moderated_datasets': []}


class Core(FakeCore):
    """A Session core that can sign in, say who it is and read a profile."""

    base_url = 'https://api.example.org'

    def __init__(self, answers=None, valid=True):
        super().__init__(answers)
        self.valid = valid

    def is_valid(self):
        return self.valid

    def get_username(self):
        return 'ada'

    @staticmethod
    def validate_uuid(value):
        return b.is_uuid(value)


def load(name, core=None, sticky=None):
    sticky = dict(sticky or {})
    if core is not None:
        sticky['CSC_AuthCore'] = core
    module = compstub.load_component(name, sticky=sticky)
    return module, compstub.instance(module, name)


# ACTOR: ME --------------------------------------------------------------------
def _run_actor(obj, me, **typed):
    names = ('Kind', 'UserID', 'Name', 'Organization', 'OrganizationROR',
             'ORCID', 'Email', 'Role')
    return obj.RunScript(*[typed.get(n) for n in names], me)


def test_me_is_the_signed_in_account():
    core = Core({('GET', '/users/me'): Response(200, PROFILE)})
    _, obj = load('Actor', core)
    result = json.loads(_run_actor(obj, True))
    assert result == {
        'kind': 'user', 'user_id': UUID_U, 'name': 'Ada Lovelace',
        'organization': 'Lab GmbH',
        'organization_ror': 'https://ror.org/02mhbdp94',
        'orcid': '0000-0002-1825-0097', 'role': 'laboratory'}
    assert compstub.messages(obj)['error'] == []
    assert compstub.messages(obj)['warning'] == []
    assert core.calls == [('GET', '/users/me', None)]
    # a typed input overrides the profile value
    typed = json.loads(_run_actor(obj, True, Name='A. L.', Role='witness',
                                  Organization='Other'))
    assert typed['name'] == 'A. L.' and typed['role'] == 'witness'
    assert typed['organization'] == 'Other'
    assert typed['orcid'] == '0000-0002-1825-0097'


def test_me_with_another_user_id_warns():
    core = Core({('GET', '/users/me'): Response(200, PROFILE)})
    _, obj = load('Actor', core)
    result = json.loads(_run_actor(obj, True, UserID=UUID_B))
    assert result['user_id'] == UUID_B                 # the typed id wins
    assert result['name'] == 'Ada Lovelace'
    assert 'differs from the signed-in account' in \
        compstub.messages(obj)['warning'][0]
    # the account's own id typed in is no reason to warn
    _, obj = load('Actor', core)
    _run_actor(obj, True, UserID=UUID_U)
    assert compstub.messages(obj)['warning'] == []


def test_me_reads_the_profile_once_a_minute():
    core = Core({('GET', '/users/me'): Response(200, PROFILE)})
    _, obj = load('Actor', core)
    for _ in range(3):
        _run_actor(obj, True)
    assert len(core.calls) == 1


def test_without_me_the_actor_is_built_as_before():
    core = Core()
    _, obj = load('Actor', core)
    for me in (False, None):
        result = json.loads(_run_actor(obj, me, Name='Ada',
                                       Organization='Lab GmbH',
                                       Role='operator'))
        assert result == b.actor(name='Ada', organization='Lab GmbH',
                                 role='operator')
    assert core.calls == []
    # and an actor of kind user without an id is still refused
    bad = _run_actor(obj, False, Kind='user')
    assert bad == '' and 'UserID' in compstub.messages(obj)['error'][0]


@pytest.mark.parametrize('core', [None, Core(valid=False)])
def test_me_without_a_session_says_to_sign_in(core):
    _, obj = load('Actor', core)
    assert _run_actor(obj, True) == ''
    error = compstub.messages(obj)['error'][0]
    assert 'sign in with the Session component first' in error


def test_me_with_an_expired_token_or_a_refusal_says_so():
    core = Core({('GET', '/users/me'): Response(401, {'detail': 'x'})})
    _, obj = load('Actor', core)
    assert _run_actor(obj, True) == ''
    assert 'sign in with the Session' in compstub.messages(obj)['error'][0]
    core = Core({('GET', '/users/me'): Response(500, {'detail': 'down'})})
    _, obj = load('Actor', core)
    assert _run_actor(obj, True) == ''
    assert compstub.messages(obj)['error']
    # a different kind with Me is refused, not guessed
    core = Core({('GET', '/users/me'): Response(200, PROFILE)})
    _, obj = load('Actor', core)
    assert _run_actor(obj, True, Kind='person') == ''
    assert 'kind user' in compstub.messages(obj)['error'][0]


# REINFORCEMENT LAYOUT: PASSPORT, UNIT, LINK -------------------------------------
class Curve:
    def __init__(self, *points):
        self.points = list(points)


def _layout_component(scale=1.0, unit='Millimeters'):
    module = compstub.load_component('ReinforcementLayout')
    compstub.patch_library(module, 'curve_points', lambda c: c.points)
    compstub.patch_library(module, 'mm_per_document_unit',
                           lambda: (scale, unit))
    return module, compstub.instance(module, 'ReinforcementLayout')


def _run_layout(obj, curves, snapshot_id=None, passport=None, **extra):
    args = {'Spec': ['BSt III'], 'Diameter': [8.0], 'Basis': 'drawing'}
    args.update(extra)
    return obj.RunScript(
        curves, args['Spec'], args['Diameter'], snapshot_id,
        args['Basis'], args.get('ObservedAt'), args.get('DocumentTitle'),
        args.get('DocumentDate'), args.get('DocumentReference'), None, None,
        None, None, args.get('DocumentUrl'), args.get('DocumentRetrievedAt'),
        passport)


def _passport(placement=None, snapshot_id=UUID_A):
    snapshot = {'_id': snapshot_id}
    if placement is not None:
        snapshot['csc_placement'] = placement
    return json.dumps({'identity': {'_id': UUID_B}, 'snapshots': [snapshot]})


def test_curves_on_a_placed_piece_are_stored_back_with_the_passport():
    stored = [(0.0, 0.0, 0.0), (500.0, 0.0, 0.0), (500.0, 80.0, 40.0)]
    placed = lay.points_to_document(stored, PLANE)
    _, obj = _layout_component()
    record = json.loads(_run_layout(obj, [Curve(*placed)],
                                    passport=_passport(PLANE)))
    assert compstub.messages(obj)['error'] == []
    got = record['payload']['bars'][0]['points']
    assert np.allclose(got, stored, atol=1e-6)
    assert record['position']['snapshot_id'] == UUID_A
    assert record['position']['kind'] == 'none'
    assert any('inverse placement' in m
               for m in compstub.messages(obj)['remark'])


def test_without_a_placement_the_curves_are_stored_as_they_are():
    points = [(0, 0, 0), (10, 0, 0)]
    _, obj = _layout_component()
    record = json.loads(_run_layout(obj, [Curve(*points)],
                                    passport=_passport()))
    assert record['payload']['bars'][0]['points'] == [[0, 0, 0], [10, 0, 0]]
    assert record['position']['snapshot_id'] == UUID_A
    assert any('conversion: none' in m
               for m in compstub.messages(obj)['remark'])
    # the old way: SnapshotID alone
    record = json.loads(_run_layout(obj, [Curve(*points)], UUID_C))
    assert record['position']['snapshot_id'] == UUID_C


def test_a_snapshot_id_that_disagrees_with_the_passport_is_an_error():
    _, obj = _layout_component()
    out = _run_layout(obj, [Curve((0, 0, 0), (1, 0, 0))], UUID_C,
                      _passport(PLANE))
    assert out == ''
    error = compstub.messages(obj)['error'][0]
    assert UUID_A in error and UUID_C in error
    # nothing to name the snapshot at all
    obj2 = _layout_component()[1]
    assert _run_layout(obj2, [Curve((0, 0, 0), (1, 0, 0))]) == ''
    assert 'SnapshotID' in compstub.messages(obj2)['error'][0]


def test_a_document_in_metres_is_used_1_to_1_with_a_warning():
    _, obj = _layout_component(1000.0, 'Meters')
    record = json.loads(_run_layout(
        obj, [Curve((0, 0, 0), (1.5, 0, 0))], UUID_A, Diameter=[12.0]))
    bar = record['payload']['bars'][0]
    assert bar['points'] == [[0, 0, 0], [1.5, 0, 0]]      # not scaled
    assert bar['diameter_mm'] == 12.0
    warning = ' '.join(compstub.messages(obj)['warning'])
    assert 'Meters' in warning and '1:1' in warning
    assert compstub.messages(obj)['error'] == []
    # a millimetre document says nothing about units
    _, obj = _layout_component()
    _run_layout(obj, [Curve((0, 0, 0), (1.5, 0, 0))], UUID_A)
    assert compstub.messages(obj)['warning'] == []


def test_the_link_and_the_day_it_was_read_go_into_the_document():
    _, obj = _layout_component()
    record = json.loads(_run_layout(
        obj, [Curve((0, 0, 0), (1, 0, 0))], UUID_A,
        DocumentTitle='Plan 7', DocumentUrl='https://archive.example.org/7',
        DocumentRetrievedAt='2026-10-05'))
    assert record['payload']['document'] == {
        'title': 'Plan 7', 'url': 'https://archive.example.org/7',
        'retrieved_at': '2026-10-05'}
    for bad in ({'DocumentUrl': 'javascript:alert(1)'},
                {'DocumentRetrievedAt': 'sometime'}):
        out = _run_layout(obj, [Curve((0, 0, 0), (1, 0, 0))], UUID_A,
                          DocumentTitle='Plan 7', **bad)
        assert out == ''
    assert 'DocumentUrl' in compstub.messages(obj)['error'][-2]


def test_the_layout_component_has_the_new_inputs_last():
    module = compstub.load_component('ReinforcementLayout')
    names = list(module.CSC_ReinforcementLayout.RunScript.__code__
                 .co_varnames[1:17])
    assert names[-3:] == ['DocumentUrl', 'DocumentRetrievedAt',
                          'ComponentPassport']


# FETCH REINFORCEMENT LAYOUT -----------------------------------------------------
class FakeList(list):
    def __class_getitem__(cls, item):
        return cls

    def Add(self, item):
        self.append(item)


FAKE_SYSTEM = types.SimpleNamespace(
    Object=object,
    Collections=types.SimpleNamespace(
        Generic=types.SimpleNamespace(List=FakeList)))


def _row(record_id, observed_at, snapshot_id=UUID_A, status='published',
         basis='drawing', bars=None):
    bars = bars if bars is not None else [
        {'spec': 'BSt III', 'diameter_mm': 8.0,
         'points': [[0, 0, 0], [100, 0, 0], [100, 50, 0]]},
        {'diameter_mm': 12.0, 'cover_mm': 25.0,
         'points': [[0, 10, 0], [100, 10, 0]]}]
    return {'_id': record_id, 'method': 'reinforcement_layout',
            'status': status, 'observed_at': observed_at,
            'position': {'kind': 'none', 'snapshot_id': snapshot_id},
            'payload': {'basis': basis, 'bars': bars}}


def _fetch_component(core, scale=1.0, unit='Millimeters'):
    module, obj = load('FetchReinforcementLayout', core)
    module.ns['System'] = FAKE_SYSTEM
    compstub.patch_library(module, 'polyline_curve',
                           lambda points: ('curve', list(points)))
    compstub.patch_library(module, 'pipe_brep',
                           lambda curve, radius: ('pipe', radius))
    compstub.patch_library(module, 'mm_per_document_unit',
                           lambda: (scale, unit))
    return module, obj


def _branches(tree):
    out = {}
    for path, item in tree.items:
        out.setdefault(path.indices, []).append(item)
    return out


def test_the_layouts_come_back_as_bars_one_branch_per_record():
    rows = [_row('old', '2024-05-03T00:00:00Z', basis='scan'),
            _row('new', '2026-01-01T00:00:00Z')]
    core = Core({('GET', '/identities/'): Response(200, rows)})
    _, obj = _fetch_component(core)
    out = obj.RunScript(_passport(), None, None)
    bars, diameter, spec, cover, ids, basis, snapshots, status, pipes = out
    assert core.calls == [('GET', '/identities/%s/evidence' % UUID_B,
                           {'method': 'reinforcement_layout',
                            'status': 'published'})]
    assert ids == ['new', 'old']                  # newest first
    assert basis == ['drawing', 'scan']
    assert snapshots == [UUID_A, UUID_A] and status == ['published'] * 2
    assert sorted(_branches(bars)) == [(0,), (1,)]
    first = _branches(bars)[(0,)]
    assert len(first) == 2
    assert first[0] == ('curve', [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0),
                                  (100.0, 50.0, 0.0)])
    assert _branches(diameter)[(0,)] == [8.0, 12.0]
    assert _branches(spec)[(0,)] == ['BSt III', None]
    assert _branches(cover)[(0,)] == [None, 25.0]
    assert pipes.items == []                      # Pipes off
    assert compstub.messages(obj)['error'] == []
    assert obj.Component.Message == '2 layouts, 4 bars'


def test_the_placement_of_the_passport_moves_the_layouts_of_its_snapshot():
    rows = [_row('here', '2026-01-01T00:00:00Z'),
            _row('there', '2025-01-01T00:00:00Z', snapshot_id=UUID_C)]
    core = Core({('GET', '/identities/'): Response(200, rows)})
    _, obj = _fetch_component(core)
    out = obj.RunScript(_passport(PLANE), None, None)
    bars, ids = out[0], out[4]
    assert ids == ['here', 'there']
    expect = lay.points_to_document([(0, 0, 0), (100, 0, 0), (100, 50, 0)],
                                    PLANE)
    here = _branches(bars)[(0,)][0][1]
    assert np.allclose(here, expect)
    assert here[0] == pytest.approx((100.0, 200.0, 300.0))   # the origin Q.o
    there = _branches(bars)[(1,)][0][1]
    assert there[0] == (0.0, 0.0, 0.0)                       # stored, as is
    warning = ' '.join(compstub.messages(obj)['warning'])
    assert UUID_C in warning and 'there' in warning
    assert any('moved by the placement' in m
               for m in compstub.messages(obj)['remark'])


def test_a_raw_identity_id_or_a_snapshot_id_is_enough():
    rows = [_row('r', '2026-01-01T00:00:00Z')]
    core = Core({('GET', '/identities/'): Response(200, rows)})
    _, obj = _fetch_component(core)
    out = obj.RunScript(UUID_B, 'ALL', None)
    assert out[4] == ['r']
    assert core.calls[0][2] == {'method': 'reinforcement_layout',
                                'status': 'all'}
    # a snapshot id: not an identity (404), so the snapshot names it
    class SnapCore(Core):
        def authorized_get(self, path, params=None, **kwargs):
            self.calls.append(('GET', path, params))
            if path == '/identities/%s/evidence' % UUID_A:
                return Response(404, {'detail': 'no'})
            if path == '/snapshots/%s' % UUID_A:
                return Response(200, {'_id': UUID_A, 'identity_id': UUID_B})
            return Response(200, rows)
    core = SnapCore()
    _, obj = _fetch_component(core)
    out = obj.RunScript(UUID_A, None, None)
    assert out[4] == ['r']
    assert [c[1] for c in core.calls] == [
        '/identities/%s/evidence' % UUID_A, '/snapshots/%s' % UUID_A,
        '/identities/%s/evidence' % UUID_B]
    # neither: an error
    class Nothing(Core):
        def authorized_get(self, path, params=None, **kwargs):
            return Response(404, {'detail': 'no'})
    _, obj = _fetch_component(Nothing())
    obj.RunScript(UUID_A, None, None)
    assert 'not found' in compstub.messages(obj)['error'][0]


def test_pipes_make_solid_bars_with_the_diameter_in_millimetres():
    rows = [_row('r', '2026-01-01T00:00:00Z')]
    core = Core({('GET', '/identities/'): Response(200, rows)})
    _, obj = _fetch_component(core)
    out = obj.RunScript(_passport(), None, True)
    assert _branches(out[8])[(0,)] == [('pipe', 4.0), ('pipe', 6.0)]
    assert compstub.messages(obj)['warning'] == []
    # a metre document: nothing is scaled, the warning says so
    _, obj = _fetch_component(core, 1000.0, 'Meters')
    out = obj.RunScript(_passport(), None, True)
    bars, diameter, pipes = out[0], out[1], out[8]
    assert _branches(pipes)[(0,)] == [('pipe', 4.0), ('pipe', 6.0)]
    assert _branches(bars)[(0,)][0][1][1] == (100.0, 0.0, 0.0)
    assert _branches(diameter)[(0,)] == [8.0, 12.0]
    warning = ' '.join(compstub.messages(obj)['warning'])
    assert 'Meters' in warning and '1:1' in warning


def test_a_record_without_content_is_left_out_with_a_warning():
    rows = [_row('r', '2026-01-01T00:00:00Z'),
            {'_id': 'gone', 'kind': 'evidence', 'status': 'withdrawn'}]
    core = Core({('GET', '/identities/'): Response(200, rows)})
    _, obj = _fetch_component(core)
    out = obj.RunScript(_passport(), None, None)
    assert out[4] == ['r']
    assert 'gone' in ' '.join(compstub.messages(obj)['warning'])


def test_no_layout_and_the_refusals_are_told():
    core = Core({('GET', '/identities/'): Response(200, [])})
    _, obj = _fetch_component(core)
    out = obj.RunScript(_passport(), None, None)
    assert out[0].items == [] and out[4] == []
    assert 'No reinforcement layout' in compstub.messages(obj)['warning'][0]
    # a status the server does not know is refused before the request
    core.calls.clear()
    obj.RunScript(_passport(), 'maybe', None)
    assert core.calls == [] and 'Status' in compstub.messages(obj)['error'][0]
    # a refusal of the server is reported
    core = Core({('GET', '/identities/'): Response(403, {'detail': 'no'})})
    _, obj = _fetch_component(core)
    obj.RunScript(_passport(), None, None)
    assert 'Access denied' in compstub.messages(obj)['error'][0]
    # input that is none of the accepted forms
    _, obj = _fetch_component(Core())
    obj.RunScript('hello', None, None)
    assert compstub.messages(obj)['error']
    # no session, no input
    _, obj = _fetch_component(None)
    assert obj.RunScript(_passport(), None, None) == (None,) * 9
    assert 'CSC_Session' in compstub.messages(obj)['warning'][0]
    _, obj = _fetch_component(Core())
    obj.RunScript(None, None, None)
    assert compstub.messages(obj)['warning']


def test_the_fetch_component_names_its_inputs_and_outputs():
    module = compstub.load_component('FetchReinforcementLayout')
    names = module.CSC_FetchReinforcementLayout.RunScript.__code__ \
        .co_varnames[1:4]
    assert list(names) == ['ComponentPassport', 'Status', 'Pipes']
    assert [o[0] for o in module.OUTPUTS] == [
        'Bars', 'Diameter', 'Spec', 'Cover', 'RecordID', 'Basis',
        'SnapshotID', 'Status', 'Pipes']
    assert module.ns['ghenv'].Component.SubCategory == '2 Catalog Interface'
