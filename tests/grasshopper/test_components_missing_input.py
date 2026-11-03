"""Missing input is a warning, no result is an empty tree (issues #32, #33,
#40; decisions 8.180, 8.186, 8.187).

The convention of the CSC components: an input that carries nothing is a
warning (the component waits for data), a real failure (a bad value, a bad
count, a server error) stays an error; an output without a result is an empty
Grasshopper tree, never ``''`` or ``None``. An item-access component runs once
per item: with no data at all on its input it gives empty trees, and one
missing, empty or failed item of a list gives a null in its slot, so the
outputs stay one to one with the input list.
"""

from __future__ import annotations

import json
import sys
import types

import pytest

import compstub
from csc_gh import build as b
from test_components import UUID_A, UUID_B
from test_components_layout import (Core, Curve, _layout_component,
                                    _run_layout, load)
from test_upload import FakeCore, Response


def _components():
    return [p.stem[len('DDU_CSC_'):] for p in compstub.headers.component_files()]


def _has_empty_outputs(name):
    text = (compstub.SRC / ('DDU_CSC_%s.py' % name)).read_text(encoding='utf-8')
    return 'def empty_outputs' in text


WITH_EMPTY = [n for n in _components() if _has_empty_outputs(n)]


def _seen(obj):
    return compstub.messages(obj)


@pytest.fixture(autouse=True)
def _stub_what_rhino_and_d2p_provide(monkeypatch):
    """Components that import the D2P libraries or ``System.Drawing`` load
    outside Rhino against stubs (they only pass objects around)."""
    for name in ('System.Drawing', 'd2p_core', 'd2p_core.utility',
                 'd2p_core.utility.instantiation', 'D2P', 'D2P.Core',
                 'D2P.Core.Components', 'D2P.Core.Components.Primitives',
                 'D2P.Core.Interfaces'):
        if name not in sys.modules:
            monkeypatch.setitem(sys.modules, name, compstub.Stub(name))


# THE LIBRARY ------------------------------------------------------------------
def test_a_missing_input_is_a_build_error_of_its_own_kind():
    assert issubclass(b.MissingInput, b.BuildError)
    error = b.missing_input('Geometry')
    assert isinstance(error, b.MissingInput)
    assert str(error) == 'Input Geometry failed to collect data'


@pytest.mark.parametrize('call', [
    lambda: b.actor('user'),
    lambda: b.actor(),
    lambda: b.origin(None),
    lambda: b.identity_body(None, None, '{}', {}),
    lambda: b.identity_body(None, 'ds', None, {}),
    lambda: b.identity_body(None, 'ds', '', {}),
    lambda: b.snapshot_envelope(None, {}),
    lambda: b.snapshot_envelope('  ', {}),
    lambda: b.reinforcement_layout_record(None, [{'diameter_mm': 8, 'points': [
        [0, 0, 0], [1, 0, 0]]}], 'drawing'),
    lambda: b.reinforcement_layout_record(UUID_A, [{'diameter_mm': 8, 'points': [
        [0, 0, 0], [1, 0, 0]]}], None),
    lambda: b.evidence_bulk_body([], [UUID_A]),
    lambda: b.evidence_bulk_body(['{"a": 1}'], []),
])
def test_the_builders_name_an_input_that_is_missing(call):
    with pytest.raises(b.MissingInput):
        call()


@pytest.mark.parametrize('call', [
    lambda: b.actor('person', name='Ada', role='nobody'),
    lambda: b.origin('nonsense'),
    lambda: b.identity_body('not-a-uuid', 'ds', '{}', {}),
    lambda: b.snapshot_envelope('not-a-uuid', {}),
    lambda: b.identity_body(None, 'ds', '{}', {}),
    lambda: b.identity_body(None, 'ds', '{"material": "concrete"}', {}),
    lambda: b.reinforcement_layout_record('not-a-uuid', [], 'drawing'),
    lambda: b.evidence_bulk_body(['{"a": 1}'], ['nope']),
])
def test_the_builders_keep_a_real_failure_an_error(call):
    with pytest.raises(b.BuildError) as raised:
        call()
    assert not isinstance(raised.value, b.MissingInput)


# EVERY COMPONENT: THE EARLY STOP -----------------------------------------------
def _argument_count(module, name):
    code = getattr(module, 'CSC_' + name).RunScript.__code__
    return code.co_argcount - 1


@pytest.mark.parametrize('name', WITH_EMPTY)
def test_empty_outputs_is_an_empty_tree_per_output(name):
    module = compstub.load_component(name)
    result = module.empty_outputs()
    count = len(module.OUTPUTS)
    if count == 0:
        assert result is None
        return
    assert compstub.no_data(result)
    if count == 1:
        assert isinstance(result, compstub.FakeDataTree)
    else:
        assert isinstance(result, tuple) and len(result) == count
        assert len({id(tree) for tree in result}) == count


@pytest.mark.parametrize('name', WITH_EMPTY)
def test_the_early_stop_returns_empty_trees(name):
    """The library is missing or too old: RunScript stops at once and the
    outputs carry no data (not ``null``)."""
    module = compstub.load_component(name)
    obj = compstub.instance(module, name)
    module.ns['LIBRARY_PROBLEM'] = 'CSC library too old or missing'
    obj._outputs_ready = False
    result = obj.RunScript(*([None] * _argument_count(module, name)))
    if not module.OUTPUTS:
        assert result is None
    else:
        assert compstub.no_data(result)


# THE COMPONENTS: A MISSING INPUT WAITS, A FAILED ITEM KEEPS ITS SLOT -------------
# 8.180: a missing input is a warning, no result is an empty tree.
# 8.186: Grasshopper runs an item-access component once per item. An input
# with no data at all gives empty trees; one missing, empty or failed item in
# a list gives a null in its slot, so the outputs stay one to one.
def _run(name, *args, no_data=()):
    """Run one iteration of a component; ``no_data`` names the inputs that
    carry no data at all (nothing connected)."""
    module = compstub.load_component(name)
    obj = compstub.instance(module, name)
    compstub.no_data_on(obj, *no_data)
    return obj.RunScript(*args), obj


def _waits(result, obj, words):
    """A warning, no error, empty trees: the component waits for data."""
    seen = _seen(obj)
    assert compstub.no_data(result), result
    assert seen['error'] == [], seen
    assert any(words in m for m in seen['warning']), seen


def _skips(result, obj, words):
    """A warning, no error, a null in the slot of the item."""
    seen = _seen(obj)
    assert compstub.nulls(result), result
    assert seen['error'] == [], seen
    assert any(words in m for m in seen['warning']), seen


def _fails(result, obj, words=''):
    """An error and a null in the slot of the item."""
    seen = _seen(obj)
    assert compstub.nulls(result), result
    assert seen['warning'] == [], seen
    assert any(words in m for m in seen['error']), seen


def test_actor_without_a_user_id_or_a_name():
    args = ('user', None, None, None, None, None, None, None, False)
    result, obj = _run('Actor', *args, no_data=('UserID',))
    _waits(result, obj, 'UserID')
    result, obj = _run('Actor', *args)                   # the item is empty
    _skips(result, obj, 'UserID')
    args = (None,) * 8 + (False,)
    result, obj = _run('Actor', *args, no_data=('Name', 'Organization'))
    _waits(result, obj, 'name or an organization')
    result, obj = _run('Actor', *args)
    _skips(result, obj, 'name or an organization')


def test_actor_with_a_bad_role_is_still_an_error():
    result, obj = _run('Actor', None, None, 'Ada', None, None, None, None,
                       'nobody', False)
    _fails(result, obj, 'Role')


def test_origin_without_a_kind_waits_and_with_a_bad_kind_fails():
    args = (None,) * 14 + (False,)
    result, obj = _run('Origin', *args, no_data=('Kind',))
    _waits(result, obj, 'Kind')
    result, obj = _run('Origin', *args)
    _skips(result, obj, 'Kind')
    result, obj = _run('Origin', 'nonsense', *([None] * 13), False)
    _fails(result, obj, 'Kind')


def test_compute_frame_without_geometry_waits():
    for geometry in ([], None):
        result, obj = _run('ComputeFrame', geometry, None)
        _waits(result, obj, 'Geometry')
        assert isinstance(result, tuple) and len(result) == 5


@pytest.mark.parametrize('name,args', [
    ('CreateComponentIdentity', (False, None, 'ds', None, None, None, None,
                                 None, False)),
    ('CreateComponentIdentity', (False, None, 'ds', None, None, None, [],
                                 None, False)),
    ('CreateComponentSnapshot', (False, UUID_B, None, None, None, None,
                                 False)),
    ('CreateComponentSnapshot', (False, UUID_B, None, None, [], None, False)),
])
def test_the_create_components_without_geometry_wait(name, args):
    # Geometry has list access: nothing there is no data at all
    result, obj = _run(name, *args)
    _waits(result, obj, 'Geometry')


def test_a_new_component_without_identity_metadata_waits_but_a_cut_does_not():
    with pytest.raises(b.MissingInput) as raised:
        b.identity_body(None, 'ds', None, {})
    assert 'Identity' in str(raised.value) and raised.value.ports == (
        'Identity',)
    # a cut (parents) may omit the metadata
    body = b.identity_body(None, 'ds', None, {}, [UUID_A])
    assert body['parent_identities'] == [UUID_A]


def _create_identity_module(tmp_path):
    mesh = b.inline_mesh([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]])
    module = compstub.load_component('CreateComponentIdentity')
    compstub.patch_library(module, 'staging_root', lambda: str(tmp_path))
    compstub.patch_library(module, 'stage_geometry', lambda *a, **k: (
        b.geometry_body([mesh]), {}, (0, 0, 0)))
    compstub.patch_library(module, 'input_references', lambda *a: None)
    return compstub.instance(module, 'CreateComponentIdentity')


def test_create_identity_without_identity_metadata(tmp_path):
    args = (False, None, 'ds', None, None, None, [object()], None, False)
    obj = _create_identity_module(tmp_path)
    compstub.no_data_on(obj, 'Identity')
    _waits(obj.RunScript(*args), obj, 'Identity')
    obj = _create_identity_module(tmp_path)               # an empty item
    _skips(obj.RunScript(*args), obj, 'Identity')
    # a missing Dataset the same way
    args = (False, None, None, '{}', None, None, [object()], None, False)
    obj = _create_identity_module(tmp_path)
    compstub.no_data_on(obj, 'Dataset')
    _waits(obj.RunScript(*args), obj, 'Dataset')
    obj = _create_identity_module(tmp_path)
    _skips(obj.RunScript(*args), obj, 'Dataset')


def test_the_create_components_clear_the_staging_folder_with_no_result(
        tmp_path):
    for name, args in (('CreateComponentIdentity',
                        (True, None, None, None, None, None, None, None,
                         False)),
                       ('CreateComponentSnapshot',
                        (True, None, None, None, None, None, False))):
        module = compstub.load_component(name)
        compstub.patch_library(module, 'staging_root', lambda: str(tmp_path))
        obj = compstub.instance(module, name)
        assert compstub.no_data(obj.RunScript(*args))
        assert _seen(obj)['error'] == []


def test_apply_frame_without_input():
    for missing in (None, '', '   '):
        result, obj = _run('ApplyFrame', missing, None, no_data=('Input',))
        _waits(result, obj, 'Input')
        assert len(result) == 2
        result, obj = _run('ApplyFrame', missing, None)    # an item of a list
        _skips(result, obj, 'Input')
        assert len(result) == 2


def test_apply_frame_with_text_that_is_no_passport_is_an_error():
    result, obj = _run('ApplyFrame', 'hello', None)
    _fails(result, obj, 'passport')
    assert len(result) == 2


def test_apply_frame_keeps_the_slot_of_a_blank_item():
    """Grasshopper runs ApplyFrame once per item of [passport, '', passport]:
    three results, the middle one null (the Rhino checklist repeats it)."""
    frame = {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]}
    passport = json.dumps({
        'identity': {'_id': UUID_B},
        'snapshots': [{'_id': UUID_A, 'frame': frame, 'bbx': [4, 2, 1]}]})
    module = compstub.load_component('ApplyFrame')
    obj = compstub.instance(module, 'ApplyFrame')
    slots = [obj.RunScript(item, None) for item in (passport, '', passport)]
    assert [compstub.nulls(s) for s in slots] == [False, True, False]
    assert all(len(s) == 2 for s in slots)
    assert json.loads(slots[0][0])['snapshots'][0]['csc_placement']
    assert [len(_seen(obj)[k]) for k in ('warning', 'error')] == [1, 0]
    # nothing connected at all: empty outputs
    obj = compstub.instance(module, 'ApplyFrame')
    compstub.no_data_on(obj, 'Input')
    assert compstub.no_data(obj.RunScript(None, None))


def test_the_layout_component_waits_for_each_missing_input():
    curve = [Curve((0, 0, 0), (1, 0, 0))]
    # the lists have list access: nothing there is no data at all
    for kwargs, curves, snapshot, words in (
            ({}, [], UUID_A, 'Curves'),
            ({}, [None], UUID_A, 'Curves'),
            ({'Diameter': []}, curve, UUID_A, 'Diameter')):
        _, obj = _layout_component()
        result = _run_layout(obj, curves, snapshot, **kwargs)
        _waits(result, obj, words)
    # the items: no data waits, an empty item keeps its slot
    for kwargs, snapshot, port, words in (
            ({}, None, 'SnapshotID', 'SnapshotID'),
            ({'Basis': None}, UUID_A, 'Basis', 'Basis')):
        _, obj = _layout_component()
        compstub.no_data_on(obj, port, 'ComponentPassport')
        _waits(_run_layout(obj, curve, snapshot, **kwargs), obj, words)
        _, obj = _layout_component()
        _skips(_run_layout(obj, curve, snapshot, **kwargs), obj, words)


def test_the_layout_component_keeps_a_count_mismatch_an_error():
    _, obj = _layout_component()
    curves = [Curve((0, 0, 0), (1, 0, 0)), Curve((0, 1, 0), (1, 1, 0))]
    result = _run_layout(obj, curves, UUID_A, Diameter=[8.0, 10.0, 12.0])
    _fails(result, obj, 'one Diameter for all bars')
    # an empty Diameter list is a missing input, not a count mismatch
    _, obj = _layout_component()
    _waits(_run_layout(obj, curves, UUID_A, Diameter=[]), obj, 'Diameter')


def test_the_steel_grade_of_a_layout_is_optional():
    """8.187: an empty Spec is no warning and the bars carry no grade; a Spec
    that is given follows the count rule."""
    curves = [Curve((0, 0, 0), (1, 0, 0)), Curve((0, 1, 0), (1, 1, 0))]
    for empty in ([], None):
        _, obj = _layout_component()
        record = json.loads(_run_layout(obj, curves, UUID_A, Spec=empty))
        seen = _seen(obj)
        assert seen['warning'] == [] and seen['error'] == [], seen
        bars = record['payload']['bars']
        assert len(bars) == 2 and all('spec' not in bar for bar in bars)
    # one grade for all bars, one per bar
    _, obj = _layout_component()
    one = json.loads(_run_layout(obj, curves, UUID_A, Spec=['BSt III']))
    assert [bar['spec'] for bar in one['payload']['bars']] == ['BSt III'] * 2
    two = json.loads(_run_layout(obj, curves, UUID_A, Spec=['a', 'b']))
    assert [bar['spec'] for bar in two['payload']['bars']] == ['a', 'b']
    # a count that fits neither is still an error, with a null in the slot
    _, obj = _layout_component()
    _fails(_run_layout(obj, curves, UUID_A, Spec=['a', 'b', 'c']), obj,
           'one Spec for all bars')


def test_the_layout_component_gives_the_record_on_success():
    _, obj = _layout_component()
    result = _run_layout(obj, [Curve((0, 0, 0), (1, 0, 0))], UUID_A)
    assert json.loads(result)['method'] == 'reinforcement_layout'
    assert _seen(obj)['error'] == [] and _seen(obj)['warning'] == []


def test_the_builders_with_no_missing_input_keep_failures_as_errors():
    """IdentityMetadata, SnapshotMetadata and Capture refuse bad values only:
    every input is optional, so nothing is a missing input there. The failed
    item keeps its slot."""
    for name, args in (
            ('IdentityMetadata', ('IfcBeam', None, None, None, '2001', None,
                                  None, None, None, 'soon')),
            ('SnapshotMetadata', ('Lintel', None, None, None, None, None,
                                  '2024-05-03', None, None, 'soon')),
            ('Capture', (None, None, None, None, None, None, None,
                         [types.SimpleNamespace(X=0, Y=0, Z=0)], ['a', 'b'],
                         None, None))):
        result, obj = _run(name, *args)
        _fails(result, obj)


def test_add_evidence_warns_for_a_missing_input_and_fails_on_a_bad_one():
    # (list access: the outputs are empty trees on both)
    core = FakeCore({('POST', '/evidence/bulk'): Response(201, {'records': []})})
    core.is_valid = lambda: True
    module = compstub.load_component('AddEvidence',
                                     sticky={'CSC_AuthCore': core})
    obj = compstub.instance(module, 'AddEvidence')
    record = json.dumps(b.reinforcement_layout_record(
        UUID_A, [{'diameter_mm': 8, 'points': [[0, 0, 0], [1, 0, 0]]}],
        'drawing'))
    assert compstub.no_data(obj.RunScript([UUID_B], [], True))
    assert compstub.no_data(obj.RunScript([], [record], True))
    seen = _seen(obj)
    assert seen['error'] == [] and len(seen['warning']) == 2
    # an id that is no UUID is a real failure
    assert compstub.no_data(obj.RunScript(['nope'], [record], True))
    assert 'not a valid identity UUID' in _seen(obj)['error'][0]
    assert core.calls == []


def test_fetch_snapshot_waits_for_a_snapshot_id():
    core = Core()
    _, obj = load('FetchSnapshot', core)
    compstub.no_data_on(obj, 'SnapshotID')
    assert compstub.no_data(obj.RunScript(UUID_B, None))
    seen = _seen(obj)
    assert seen['error'] == [] and len(seen['warning']) == 1
    # an empty item of a list keeps its slot
    _, obj = load('FetchSnapshot', core)
    for missing in (None, '', '  '):
        assert compstub.nulls(obj.RunScript(UUID_B, missing)), missing
    seen = _seen(obj)
    assert seen['error'] == [] and len(seen['warning']) == 3
    # a text that is no UUID is a real failure
    assert compstub.nulls(obj.RunScript(UUID_B, 'nope'))
    assert 'valid snapshot UUID' in _seen(obj)['error'][0]
    assert core.calls == []


def test_fetch_all_snapshots_without_a_session_or_input():
    _, obj = load('FetchAllSnapshots', None)          # no session at all
    assert compstub.no_data(obj.RunScript(UUID_B))
    core = Core()
    core.resolve_identity_id_from_input = lambda value: None
    _, obj = load('FetchAllSnapshots', core)
    compstub.no_data_on(obj, 'Input')
    assert compstub.no_data(obj.RunScript(None))      # nothing connected
    assert _seen(obj)['error'] == [] and _seen(obj)['warning']
    _, obj = load('FetchAllSnapshots', core)
    assert compstub.nulls(obj.RunScript(None))        # an empty item
    assert _seen(obj)['error'] == []
    assert compstub.nulls(obj.RunScript('not an identity'))
    assert _seen(obj)['error']


def test_the_fetch_layout_component_without_input():
    _, obj = load('FetchReinforcementLayout', Core())
    compstub.no_data_on(obj, 'ComponentPassport')
    result = obj.RunScript(None, None, None)
    assert _seen(obj)['error'] == [] and _seen(obj)['warning']
    assert isinstance(result, tuple) and compstub.no_data(result)
    _, obj = load('FetchReinforcementLayout', Core())
    result = obj.RunScript(None, None, None)           # an empty item
    assert _seen(obj)['error'] == [] and compstub.nulls(result)
    assert len(result) == 9
    # no session: the component cannot run at all, empty trees
    _, obj = load('FetchReinforcementLayout', None)
    assert compstub.no_data(obj.RunScript(UUID_B, None, None))


# THE LIBRARY: NO DATA AT ALL, AND THE SLOT OF AN ITEM -----------------------------
class _Param:
    def __init__(self, name, count):
        self.Name, self.VolatileDataCount = name, count


def _instance_with(**counts):
    return types.SimpleNamespace(Component=types.SimpleNamespace(
        Params=types.SimpleNamespace(
            Input=[_Param(n, c) for n, c in counts.items()])))


def test_an_input_has_no_data_when_nothing_is_connected_or_the_list_is_empty():
    from csc_gh import messages
    inst = _instance_with(Input=0, Other=1, Items=3)
    assert messages.has_no_data(inst, 'Input')
    assert not messages.has_no_data(inst, 'Other')       # one item, may be null
    assert not messages.has_no_data(inst, 'Items')
    assert not messages.has_no_data(inst, 'Unknown')     # not found: data
    assert messages.waits_for_data(inst, ('Input',))
    assert not messages.waits_for_data(inst, ('Input', 'Other'))
    assert not messages.waits_for_data(inst, ())
    assert messages.waits_for_data(_instance_with(A=0, B=0), ('A', 'B'))


def test_a_missing_input_names_its_ports():
    assert b.missing_input('Geometry').ports == ('Geometry',)
    assert b.MissingInput('x').ports == ()
    with pytest.raises(b.MissingInput) as raised:
        b.actor('user')
    assert raised.value.ports == ('UserID',)
    with pytest.raises(b.MissingInput) as raised:
        b.actor()
    assert raised.value.ports == ('Name', 'Organization')
    with pytest.raises(b.MissingInput) as raised:
        b.origin(None)
    assert raised.value.ports == ('Kind',)


def test_nulls_are_one_per_output():
    from csc_gh import ports
    outs = [('A', 'A', 'a'), ('B', 'B', 'b'), ('C', 'C', 'c')]
    assert ports.nulls(outs[:1]) is None
    assert ports.nulls(outs) == (None, None, None)


def _item_access():
    return [n for n in _components() if 'def _no_result' in (
        compstub.SRC / ('DDU_CSC_%s.py' % n)).read_text(encoding='utf-8')]


@pytest.mark.parametrize('name', _item_access())
def test_an_item_access_component_gives_empty_trees_or_nulls(name):
    """``_no_result`` with no ports (a list or tree input is empty) gives
    empty trees; with ports it gives empty trees for no data at all and a
    null per output for an item."""
    module = compstub.load_component(name)
    obj = compstub.instance(module, name)
    count = len(module.OUTPUTS)
    assert compstub.no_data(obj._no_result())
    first = obj.InputParams[0].Name
    assert compstub.nulls(obj._no_result(first))
    compstub.no_data_on(obj, first)
    assert compstub.no_data(obj._no_result(first))
    assert count >= 1


@pytest.mark.parametrize('name,args,words', [
    ('CreatePublicDevelopmentFile', (True, [], '  ', 'name'),
     'Save path cannot be empty'),
    ('CreateReleaseFiles', (True, False, '  ', [], 'path', 'name', [], []),
     'Group name cannot be empty'),
])
def test_the_development_tools_warn_for_an_empty_input(name, args, words):
    module = compstub.load_component(name)
    obj = compstub.instance(module, name)
    obj.RunScript(*args[:_argument_count(module, name)])
    assert words in _seen(obj)['warning']
    assert _seen(obj)['error'] == []
