"""ReadFromD2P: the ``Component`` output carries the concrete .NET object of
the D2P component (the ``IComponentBase`` that D2P and Grasshopper accept),
whatever shape ``instance_from_object`` hands back (issue #36, 8.185 b).
D2P and the Rhino document are stubbed: the component only passes objects
around.
"""

from __future__ import annotations

import sys
import types

import pytest

import compstub

UUID_I = '11111111-1111-4111-8111-111111111111'
PLANE = object()


class NetObject:
    """A concrete .NET object (a D2P component)."""

    Plane = PLANE

    def GetType(self):
        return types.SimpleNamespace(FullName='D2P.Core.Components.GHComponent')


class Wrapper:
    """A Python wrapper that holds the .NET object in ``NetObj``."""

    def __init__(self, net):
        self.NetObj = net
        self.Plane = PLANE


class InterfaceProxy:
    """What pythonnet 3 may hand over for an interface-typed return."""

    def __init__(self, net):
        self.__implementation__ = net
        self.Plane = PLANE


class RhinoObject:
    def __init__(self, name, object_id):
        self.Id = object_id
        self.Attributes = types.SimpleNamespace(Name=name)


@pytest.fixture
def csc_doc():
    """``csc_gh.doc`` against the Rhino stubs (it imports RhinoCommon)."""
    saved = compstub._install_modules({})
    compstub._purge_library()
    try:
        from csc_gh import doc
        yield doc
    finally:
        compstub._restore(saved)
        compstub._purge_library()


def _entry(name, object_id, identity_id=UUID_I):
    return {'object': RhinoObject(name, object_id), 'plane': PLANE,
            'tags': {'identity_id': identity_id, 'problems': []}}


def _read(monkeypatch, entries, resolve):
    """Run ReadFromD2P over ``entries`` (what ``tagged_objects`` finds);
    ``resolve(rhino_object)`` stands in for ``instance_from_object``."""
    for name in ('d2p_core', 'd2p_core.utility',
                 'd2p_core.utility.instantiation'):
        monkeypatch.setitem(sys.modules, name, compstub.Stub(name))
    module = compstub.load_component('ReadFromD2P', outputs=2)
    obj = compstub.instance(module, 'ReadFromD2P')

    def read_document(doc, fetch=None, plane_of=None):
        pieces = []
        for entry in entries:
            plane = plane_of(entry) if plane_of and entry['plane'] else None
            pieces.append({
                'object': entry['object'], 'identity_id':
                entry['tags']['identity_id'], 'snapshot_id': None,
                'passport': {'identity': {'_id': UUID_I},
                             'plane_known': plane is not None},
                'problems': []})
        return pieces

    compstub.patch_library(module, 'read_document', read_document)
    module.ns['instance_from_object'] = resolve
    return obj.RunScript(True), obj


def _components(result):
    return [item for _, item in result[1].items]


@pytest.mark.parametrize('shape', ['wrapper', 'proxy', 'plain'])
def test_the_component_output_is_the_concrete_net_object(monkeypatch, shape):
    net = NetObject()
    make = {'wrapper': Wrapper, 'proxy': InterfaceProxy,
            'plain': lambda n: n}[shape]
    result, obj = _read(monkeypatch, [_entry('Lintel', 'a')],
                        lambda rhino_object: make(net))
    assert _components(result) == [net]
    assert _components(result)[0] is net
    seen = compstub.messages(obj)
    assert seen['error'] == [] and seen['warning'] == []
    assert any('D2P.Core.Components.GHComponent' in m for m in seen['remark'])


def test_a_wrapped_proxy_is_unwrapped_step_by_step(csc_doc):
    net = NetObject()
    assert csc_doc.net_instance(Wrapper(InterfaceProxy(net))) is net
    assert csc_doc.net_instance(InterfaceProxy(net)) is net
    assert csc_doc.net_instance(Wrapper(net)) is net
    assert csc_doc.net_instance(net) is net
    assert csc_doc.net_instance(None) is None


def test_the_net_type_name_falls_back_to_the_python_type(csc_doc):
    assert csc_doc.net_type_name(NetObject()) == \
        'D2P.Core.Components.GHComponent'
    assert csc_doc.net_type_name(Wrapper(None)) == 'Wrapper'


def test_a_plain_tag_is_null_without_a_warning(monkeypatch):
    called = []
    result, obj = _read(monkeypatch, [_entry('', 'a')],
                        lambda rhino_object: called.append(1))
    assert _components(result) == [None] and called == []
    seen = compstub.messages(obj)
    assert seen['error'] == [] and seen['warning'] == []
    assert not any('D2P component' in m for m in seen['remark'])


def test_a_failed_resolution_is_a_warning_naming_the_element(monkeypatch):
    def resolve(rhino_object):
        raise RuntimeError('no such group')

    result, obj = _read(monkeypatch, [_entry('Lintel', 'a')], resolve)
    assert _components(result) == [None]
    seen = compstub.messages(obj)
    assert seen['error'] == []
    assert len(seen['warning']) == 1
    warning = seen['warning'][0]
    assert UUID_I in warning and 'no such group' in warning


def test_one_failure_does_not_spoil_the_others(monkeypatch):
    net = NetObject()

    def resolve(rhino_object):
        if rhino_object.Id == 'bad':
            raise RuntimeError('boom')
        return Wrapper(net)

    result, obj = _read(monkeypatch, [_entry('A', 'good'), _entry('B', 'bad')],
                        resolve)
    assert _components(result) == [net, None]
    assert len(compstub.messages(obj)['warning']) == 1
