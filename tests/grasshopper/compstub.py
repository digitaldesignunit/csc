"""Load a Grasshopper script component outside Grasshopper.

``load_component('Session')`` compiles ``grasshopper_userobjects_src/
DDU_CSC_Session.py`` into a module whose ``ghenv``, ``Grasshopper`` and
``scriptcontext`` are small fakes, so the component class can be built and its
``RunScript`` called with plain Python values. ``Rhino`` and ``System`` are
the real ones when a headless Rhino is loaded (``CSC_TEST_RHINO=1``), else a
stub that accepts any attribute (enough for annotations and for components
that only pass geometry around).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import headers

SRC = headers.SRC_DIR


class Stub:
    """An object that is any attribute, any call and any subscript."""

    def __init__(self, name='stub'):
        self._name = name

    def __getattr__(self, item):
        if item.startswith('__'):
            raise AttributeError(item)
        return Stub('%s.%s' % (self._name, item))

    def __call__(self, *args, **kwargs):
        return Stub('%s()' % self._name)

    def __getitem__(self, item):
        return Stub('%s[]' % self._name)

    def __repr__(self):
        return '<Stub %s>' % self._name


class _Messages:
    """What a component told the user."""

    def __init__(self):
        self.remarks, self.warnings, self.errors = [], [], []


class FakeScriptInstance:
    """``Grasshopper.Kernel.GH_ScriptInstance``: collects runtime messages."""

    def AddRuntimeMessage(self, level, message):
        self.__class__.messages_of(self)[level].append(message)

    @staticmethod
    def messages_of(instance):
        store = instance.__dict__.setdefault(
            '_messages', {'remark': [], 'warning': [], 'error': []})
        return store


class FakeLevels:
    Remark, Warning, Error = 'remark', 'warning', 'error'


class FakeParam:
    def __init__(self, name='out'):
        self.Name = name
        self.Description = ''


class FakeComponentObject:
    """``ghenv.Component``: a bag with the attributes components set."""

    def __init__(self, inputs=12, outputs=18):
        self.Params = types.SimpleNamespace(
            Input=[FakeParam('in%d' % i) for i in range(inputs)],
            Output=[FakeParam('o%d' % i) for i in range(outputs)])
        self.RuntimeMessageLevel = FakeLevels
        self.Message = ''
        self.Name = self.NickName = self.Category = self.SubCategory = ''
        self.Description = ''

    def OnPingDocument(self):
        return None


class FakeDataTree:
    """``Grasshopper.DataTree[T]``: items per path."""

    def __class_getitem__(cls, item):
        return cls

    def __init__(self):
        self.items = []

    def Add(self, item, path=None):
        self.items.append((path, item))

    def AddRange(self, items, path=None):
        for item in items:
            self.Add(item, path)

    @property
    def DataCount(self):
        return len(self.items)

    @property
    def values(self):
        return [item for _, item in self.items]


class FakeInputTree:
    """An input ``DataTree``: ``{branch index: [items]}``."""

    def __init__(self, branches):
        self.branches = [list(items) for items in branches]

    @property
    def DataCount(self):
        return sum(len(b) for b in self.branches)

    @property
    def BranchCount(self):
        return len(self.branches)

    @property
    def Paths(self):
        return [FakePath(i) for i in range(len(self.branches))]

    @property
    def Branches(self):
        return self.branches

    def __bool__(self):
        return True


class FakePath:
    def __init__(self, *indices):
        self.indices = indices


def fake_grasshopper():
    module = types.ModuleType('Grasshopper')
    kernel = types.SimpleNamespace(
        GH_ScriptInstance=FakeScriptInstance,
        GH_Document=types.SimpleNamespace(
            GH_ScheduleDelegate=lambda function: function),
        Data=types.SimpleNamespace(GH_Path=FakePath))
    module.Kernel = kernel
    module.DataTree = FakeDataTree
    module.Folders = Stub('Folders')
    return module


def fake_scriptcontext(sticky=None):
    module = types.ModuleType('scriptcontext')
    module.sticky = {} if sticky is None else sticky
    module.doc = None
    return module


def _install_modules(sticky):
    """Put the fakes into ``sys.modules``; returns what to restore."""
    saved = {}
    fakes = {'Grasshopper': fake_grasshopper(),
             'scriptcontext': fake_scriptcontext(sticky),
             # the updater imports the Rhino script component libraries
             'GhPython': Stub('GhPython'),
             'ScriptComponents': Stub('ScriptComponents'),
             'RhinoCodePluginGH': Stub('RhinoCodePluginGH')}
    if 'Rhino' not in sys.modules or isinstance(sys.modules['Rhino'], Stub):
        rhino = Stub('Rhino')
        fakes.update({'Rhino': rhino, 'System': Stub('System'),
                      'Rhino.Geometry': rhino.Geometry,
                      'rhinoscriptsyntax': Stub('rs')})
    for name, module in fakes.items():
        saved[name] = sys.modules.get(name)
        sys.modules[name] = module
    return saved


def _restore(saved):
    for name, module in saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


_PATCHES = []


def patch_library(module, name, value):
    """Replace ``name`` where a component and the library see it: in the
    ``csc_gh`` module that defines it (the library calls it itself) and in
    the namespace of the loaded component (which took the name with ``from
    csc_gh.x import name``). Undone after each test (``conftest.py``)."""
    import importlib
    import csc_gh
    for short in csc_gh.MODULES:
        try:
            owner = importlib.import_module('csc_gh.' + short)
        except ImportError:
            continue
        if name in vars(owner):
            _PATCHES.append((owner.__dict__, name, owner.__dict__[name]))
            owner.__dict__[name] = value
    if name in module.ns:
        _PATCHES.append((module.ns, name, module.ns[name]))
        module.ns[name] = value


def undo_patches():
    while _PATCHES:
        scope, name, old = _PATCHES.pop()
        scope[name] = old


def _purge_library():
    """Forget the modules of ``csc_gh`` that bind ``Rhino`` and ``System``
    when they are imported, so each component load gets the stubs (or the real
    Rhino) of its own test, not those of an earlier one."""
    for module in ('csc_gh.rhino', 'csc_gh.doc'):
        sys.modules.pop(module, None)


def load_component(name, sticky=None, inputs=12, outputs=18,
                   real_rhino=False):
    """The compiled module of component ``name``: its class is
    ``module.CSC_<name>`` (the module's ``ns`` is the globals dict)."""
    path = SRC / ('DDU_CSC_%s.py' % name)
    source = path.read_text(encoding='utf-8')
    sticky = {} if sticky is None else sticky
    _purge_library()
    saved = _install_modules(sticky)
    try:
        scope = {
            '__name__': 'component_' + name,
            'ghenv': types.SimpleNamespace(
                Component=FakeComponentObject(inputs, outputs)),
        }
        exec(compile(source, str(path), 'exec'), scope)
    finally:
        _restore(saved)
        _purge_library()
    module = types.SimpleNamespace(**{k: v for k, v in scope.items()
                                      if not k.startswith('__')})
    module.ns = scope
    module.sticky = sticky
    return module


def instance(module, name):
    """A fresh component object of a loaded module (``CSC_<name>``)."""
    cls = getattr(module, 'CSC_' + name)
    obj = cls.__new__(cls)
    obj.Component = module.ns['ghenv'].Component
    obj.InputParams = obj.Component.Params.Input
    obj.OutputParams = obj.Component.Params.Output
    # ``scriptcontext.sticky`` as the component's own ``sc``
    return obj


def messages(obj):
    return FakeScriptInstance.messages_of(obj)
