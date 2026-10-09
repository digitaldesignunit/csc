"""The shared package ``csc_gh`` outside Rhino (decisions 8.111, 8.112, 8.113):
its version, the reload switch, the declared outputs of a script component
(against fakes of the Grasshopper objects), the runtime message helpers and
the way a component behaves without the library."""

from __future__ import annotations

import ast
import sys
import types

import pytest

import csc_gh
from csc_gh import messages, ports

import compstub


# VERSION ----------------------------------------------------------------------
def test_versions_compare_like_the_updater_does():
    key = csc_gh.version_key
    assert key('261005') < key('261005a') < key('261006')
    assert key('261004a') > key('261004')
    assert key('999999') > key('261005z')
    with pytest.raises(ValueError):
        key('0.6.0.0')
    with pytest.raises(ValueError):
        key('')


def test_require_raises_an_import_error_when_too_old():
    csc_gh.require(csc_gh.__version__)
    csc_gh.require('100000')
    with pytest.raises(ImportError) as info:
        csc_gh.require('999999')
    assert isinstance(info.value, csc_gh.LibraryTooOld)
    assert '261005' in csc_gh.problem_text('261005')
    assert 'CSC_Update' in csc_gh.problem_text('261005')
    assert 'restart Rhino' in csc_gh.problem_text('261005')


def test_importing_the_package_imports_no_module_of_it():
    code = ("import sys, csc_gh; "
            "print([m for m in sys.modules if m.startswith('csc_gh.')])")
    import subprocess
    out = subprocess.run(
        [sys.executable, '-c', code], capture_output=True, text=True,
        env={**__import__('os').environ,
             'PYTHONPATH': str(compstub.headers.LIB_DIR)}).stdout.strip()
    assert out == '[]'


def test_every_module_of_the_package_is_listed_for_the_reload():
    names = {p.stem for p in (compstub.headers.LIB_DIR / 'csc_gh').glob('*.py')}
    assert names - {'__init__'} == set(csc_gh.MODULES)


# RELOAD (development) ------------------------------------------------------------
# A reload re-runs the modules in place, which would leave the names other
# tests hold pointing at old objects (an exception class, say): the reload is
# tried in a process of its own.
def _run(code, **env):
    import os
    import subprocess
    result = subprocess.run(
        [sys.executable, '-c', code], capture_output=True, text=True,
        env={**os.environ, 'PYTHONPATH': str(compstub.headers.LIB_DIR), **env})
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_reload_rebinds_the_names_a_component_took():
    code = """
import sys
import csc_gh
from csc_gh import build
namespace = {'identity_body': build.identity_body,
             'BuildError': build.BuildError, 'own': 1}
before = build.identity_body
reloaded = csc_gh.reload_modules(namespace)
assert 'build' in reloaded
assert build.identity_body is not before
assert namespace['identity_body'] is sys.modules['csc_gh.build'].identity_body
assert namespace['BuildError'] is sys.modules['csc_gh.build'].BuildError
assert namespace['own'] == 1
print('ok')
"""
    assert _run(code) == 'ok'


def test_the_reload_runs_only_when_asked():
    code = """
import csc_gh
from csc_gh import build
print(csc_gh.dev_reload({}))
"""
    assert _run(code) == '[]'
    assert _run(code, CSC_DEV_RELOAD='0') == '[]'
    assert _run(code, CSC_DEV_RELOAD='1') == "['build']"


# DECLARED OUTPUTS ----------------------------------------------------------------
class Param:
    def __init__(self, name, nick=None, desc=''):
        self.Name = name
        self.NickName = nick or name
        self.Description = desc


class FakeParams:
    def __init__(self, names):
        self.Output = [Param(n) for n in names]
        self.registered = []
        self.unregistered = []

    def RegisterOutputParam(self, param, index):
        self.Output.insert(index, param)
        self.registered.append(index)

    def UnregisterOutputParameter(self, param):
        self.Output.remove(param)
        self.unregistered.append(param.Name)

    def OnParametersChanged(self):
        self.changed = True


class FakeDocument:
    def __init__(self):
        self.scheduled = []

    def ScheduleSolution(self, milliseconds, callback):
        self.scheduled.append(callback)

    def run(self):
        """The scheduled solution: the callbacks that are queued now (a
        callback may queue another one for the next solution)."""
        queued, self.scheduled = self.scheduled, []
        for callback in queued:
            callback(self)


class FakeComponent:
    """The parts of a script component the helper touches."""

    def __init__(self, names=('out', 'a'), document=None):
        self.Params = FakeParams(names)
        self.document = document
        self.created = []
        self.expired = 0
        self.maintenance = 0
        self.InstanceGuid = 'guid-%d' % id(self)

    def OnPingDocument(self):
        return self.document

    def CreateParameter(self, side, index):
        param = Param('new%d' % index)
        self.created.append((side, index))
        return param

    def VariableParameterMaintenance(self):
        self.maintenance += 1

    def ExpireSolution(self, recompute):
        self.expired += 1


@pytest.fixture
def grasshopper(monkeypatch):
    """A Grasshopper whose scheduled solutions run when the test says."""
    kernel = types.ModuleType('Grasshopper.Kernel')
    kernel.GH_ParameterSide = types.SimpleNamespace(Output='output-side')
    kernel.GH_Document = types.SimpleNamespace(
        GH_ScheduleDelegate=lambda function: function)
    module = types.ModuleType('Grasshopper')
    module.Kernel = kernel
    monkeypatch.setitem(sys.modules, 'Grasshopper', module)
    monkeypatch.setitem(sys.modules, 'Grasshopper.Kernel', kernel)
    ports._TRIES.clear()
    ports._PROBLEMS.clear()
    return module


OUTS = [('IdentityID', 'IdentityID', 'the id'),
        ('Name', 'Name', 'the name'),
        ('Geometry', 'Geometry', 'the geometry')]


def names(component):
    return [p.Name for p in component.Params.Output]


def test_matching_outputs_only_get_their_descriptions(grasshopper):
    doc = FakeDocument()
    comp = FakeComponent(('out', 'IdentityID', 'Name', 'Geometry'), doc)
    status = ports.ensure_outputs(comp, OUTS)
    assert status.ready and status.remark is None
    assert doc.scheduled == [] and comp.created == []
    assert [p.Description for p in comp.Params.Output] == [
        '', 'the id', 'the name', 'the geometry']
    assert ports.ensure_outputs(comp, OUTS).ready      # idempotent


def test_outputs_are_changed_between_solutions_not_inside_one(grasshopper):
    doc = FakeDocument()
    comp = FakeComponent(('out', 'a'), doc)
    status = ports.ensure_outputs(comp, OUTS)
    assert not status.ready and status.remark == ports.UPDATED
    assert names(comp) == ['out', 'a']          # nothing changed yet
    assert len(doc.scheduled) == 1
    doc.run()
    assert names(comp) == ['out', 'IdentityID', 'Name', 'Geometry']
    assert comp.created == [('output-side', 2), ('output-side', 3)]
    assert comp.maintenance == 1 and comp.Params.changed
    assert comp.expired == 1
    assert ports.ensure_outputs(comp, OUTS).ready


def test_a_component_that_solved_again_is_not_expired_a_second_time(
        grasshopper):
    doc = FakeDocument()
    comp = FakeComponent(('out', 'a'), doc)
    ports.ensure_outputs(comp, OUTS)
    doc.run()                                   # healed, expired once
    assert comp.expired == 1
    assert ports.ensure_outputs(comp, OUTS).ready      # it ran again
    doc.run()                                   # the second pass
    assert comp.expired == 1 and not ports._PENDING


def test_a_component_that_did_not_solve_again_is_expired_once_more(
        grasshopper):
    doc = FakeDocument()
    comp = FakeComponent(('out', 'a'), doc)
    ports.ensure_outputs(comp, OUTS)
    doc.run()                                   # healed, expired once
    doc.run()                                   # nothing ran it: expire again
    assert comp.expired == 2
    doc.run()                                   # and not a third time
    assert comp.expired == 2


def test_a_rename_keeps_the_parameter_object(grasshopper):
    doc = FakeDocument()
    comp = FakeComponent(('out', 'Proxies', 'Name', 'Geometry'), doc)
    keep = comp.Params.Output[1]
    ports.ensure_outputs(comp, OUTS)
    doc.run()
    assert comp.Params.Output[1] is keep and keep.Name == 'IdentityID'
    assert comp.created == []                    # renamed, not created


def test_too_many_outputs_are_removed_and_out_is_left_alone(grasshopper):
    doc = FakeDocument()
    comp = FakeComponent(('out', 'a', 'b', 'c', 'd'), doc)
    ports.ensure_outputs(comp, OUTS[:2])
    doc.run()
    assert names(comp) == ['out', 'IdentityID', 'Name']
    assert comp.Params.unregistered == ['d', 'c']


def test_without_the_own_out_output_the_indices_start_at_zero(grasshopper):
    doc = FakeDocument()
    comp = FakeComponent(('a', 'b'), doc)
    ports.ensure_outputs(comp, OUTS)
    doc.run()
    assert names(comp) == ['IdentityID', 'Name', 'Geometry']


def test_without_a_document_the_change_is_made_at_once(grasshopper):
    comp = FakeComponent(('out', 'a'), None)
    status = ports.ensure_outputs(comp, OUTS)
    assert not status.ready
    assert names(comp) == ['out', 'IdentityID', 'Name', 'Geometry']


def test_the_helper_gives_up_after_two_tries(grasshopper):
    doc = FakeDocument()
    comp = FakeComponent(('out', 'a'), doc)

    def broken(side, index):
        raise RuntimeError('no parameter')
    comp.CreateParameter = broken
    for _ in range(ports.MAX_TRIES):
        assert not ports.ensure_outputs(comp, OUTS).ready
        doc.run()
    status = ports.ensure_outputs(comp, OUTS)
    assert status.ready and 'could not be updated' in status.remark
    assert 'no parameter' in status.remark


def test_the_helper_never_raises(grasshopper):
    status = ports.ensure_outputs(object(), OUTS)     # not a component
    assert status.ready and 'output check skipped' in status.remark


def test_empty_outputs_of_one_and_of_many():
    assert ports.empty(OUTS[:1]) is None
    assert ports.empty(OUTS) == (None, None, None)


# MESSAGES (8.113) ---------------------------------------------------------------
class FakeInstance:
    def __init__(self):
        self.Component = types.SimpleNamespace(
            RuntimeMessageLevel=types.SimpleNamespace(
                Remark='remark', Warning='warning', Error='error'),
            Message='')
        self.got = []

    def AddRuntimeMessage(self, level, text):
        self.got.append((level, text))


def test_the_four_levels():
    inst = FakeInstance()
    messages.error(inst, 'server said no')
    messages.warn(inst, 'skipped mesh 2')
    messages.remark(inst, 'cache hit')
    messages.set_state(inst.Component, 'Logged in')
    assert inst.got == [('error', 'server said no'),
                        ('warning', 'skipped mesh 2'),
                        ('remark', 'cache hit')]
    assert inst.Component.Message == 'Logged in'
    messages.set_state(inst.Component, '')
    assert inst.Component.Message == ''


def test_a_missing_required_input_is_a_warning_not_an_error():
    inst = FakeInstance()
    assert not messages.check_inputs(inst, Passport=None, Items=[], Name=' ',
                                     Ok='x', Count=0)
    assert inst.got == [
        ('warning', 'Input parameter Passport failed to collect data'),
        ('warning', 'Input parameter Items failed to collect data'),
        ('warning', 'Input parameter Name failed to collect data')]
    assert all(level != 'error' for level, _ in inst.got)
    inst = FakeInstance()
    assert messages.check_inputs(inst, Passport='{}', Items=[1])
    assert inst.got == []


def test_a_data_tree_without_data_is_empty():
    tree = types.SimpleNamespace(DataCount=0)
    assert messages.is_empty(tree)
    assert not messages.is_empty(types.SimpleNamespace(DataCount=3))


# A COMPONENT WITHOUT THE LIBRARY ---------------------------------------------------
def _without_library(monkeypatch):
    for name in [m for m in sys.modules if m == 'csc_gh'
                 or m.startswith('csc_gh.')]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, 'csc_gh', None)    # import fails


def test_a_component_without_the_library_says_so_and_does_not_raise(
        monkeypatch):
    _without_library(monkeypatch)
    module = compstub.load_component('Origin', inputs=15, outputs=2)
    assert module.LIBRARY_PROBLEM and 'CSC_Update' in module.LIBRARY_PROBLEM
    assert module.ensure_outputs is None            # the guard path
    obj = compstub.instance(module, 'Origin')
    obj.BeforeRunScript()                           # must not raise
    assert obj._outputs_note == ('output check skipped: CSC library not '
                                 'installed')
    result = obj.RunScript(*([None] * 15))
    assert result is None                           # one output: bare None
    seen = compstub.messages(obj)
    assert seen['error'] == [module.LIBRARY_PROBLEM]


def test_a_helper_only_component_solves_without_the_library(monkeypatch):
    """CreateUUID uses the library for the output check only: without it the
    check is skipped with one remark and the component runs as before."""
    _without_library(monkeypatch)
    module = compstub.load_component('CreateUUID', outputs=2)
    assert module.ensure_outputs is None
    assert not hasattr(module, 'LIBRARY_PROBLEM')
    obj = compstub.instance(module, 'CreateUUID')
    obj.Component.InstanceGuid = 'g-1'
    module.sticky['g-1__CreateUUIDComponent'] = 'the-uuid'
    obj.BeforeRunScript()                           # must not raise
    assert obj._outputs_ready and obj._outputs_note
    assert obj.RunScript(False) == 'the-uuid'
    seen = compstub.messages(obj)
    assert seen['error'] == [] and seen['warning'] == []
    assert seen['remark'] == ['output check skipped: CSC library not '
                              'installed']


def test_with_the_library_the_component_works():
    module = compstub.load_component('Origin', inputs=15, outputs=2)
    assert module.LIBRARY_PROBLEM is None
    obj = compstub.instance(module, 'Origin')
    obj.BeforeRunScript()
    result = obj.RunScript('deinstallation', '2024-05', None, None, None,
                           None, None, None, None, None, None, None, None,
                           None, False)
    assert '"deinstallation"' in result


# THE STATIC RULES ON THE COMPONENTS -----------------------------------------------
def _source(path):
    return path.read_text(encoding='utf-8')


# development components keep their own messages and outputs (8.112, 8.113),
# unless the user agrees: the updater is in scope for messages only
DEVELOPMENT = {'CreatePublicDevelopmentFile', 'CreateReleaseFiles',
               'ExportScriptsAndSource', 'Update'}


def _migrated():
    """Every CSC component: each declares its outputs (8.112) and follows the
    message levels (8.113)."""
    return [p for p in compstub.headers.component_files()
            if p.stem[len('DDU_CSC_'):] not in DEVELOPMENT]


def _runscript(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'RunScript':
            return node
    return None


def _declared_outputs(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == 'OUTPUTS'
                for t in node.targets):
            return [elt for elt in node.value.elts]
    return None


def _length(node, scope, count):
    """How many values a ``return`` hands back (None: cannot tell)."""
    if isinstance(node, (ast.Tuple, ast.List)):
        return len(node.elts)
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == 'empty_outputs':
            return count
        if isinstance(func, ast.Name) and func.id == 'tuple' and node.args \
                and isinstance(node.args[0], ast.GeneratorExp):
            return _length(node.args[0].generators[0].iter, scope, count)
    if isinstance(node, ast.Name) and node.id in scope:
        return _length(scope[node.id], scope, count)
    single = (ast.Constant, ast.Name, ast.Call, ast.Attribute, ast.Subscript,
              ast.BinOp, ast.IfExp, ast.JoinedStr)
    if count == 1 and isinstance(node, single):
        return 1
    if count == 0 and (node is None or (isinstance(node, ast.Constant)
                                        and node.value is None)):
        return 0
    return None


def _own_returns(func):
    """The ``return`` statements of a function, not those of a function
    defined inside it."""
    found = []

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.Lambda, ast.ClassDef)):
                continue
            if isinstance(child, ast.Return):
                found.append(child)
            visit(child)
    visit(func)
    return found


@pytest.mark.parametrize('path', _migrated(), ids=lambda p: p.stem)
def test_every_return_of_runscript_has_as_many_values_as_outputs(path):
    tree = ast.parse(_source(path))
    outputs = _declared_outputs(tree)
    assert outputs is not None, '%s declares no OUTPUTS' % path.name
    for item in outputs:
        assert isinstance(item, ast.Tuple) and len(item.elts) == 3, \
            '%s: an OUTPUTS entry is (name, nickname, description)' % path.name
    func = _runscript(tree)
    scope = {}
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            scope[node.targets[0].id] = node.value
    for node in _own_returns(func):
        if isinstance(node, ast.Return):
            if node.value is None:
                pytest.fail('%s line %d: a bare return'
                            % (path.name, node.lineno))
            got = _length(node.value, scope, len(outputs))
            assert got == len(outputs), (
                '%s line %d: returns %s values, OUTPUTS has %d'
                % (path.name, node.lineno, got, len(outputs)))


@pytest.mark.parametrize('path', _migrated(), ids=lambda p: p.stem)
def test_a_component_sets_no_message_text_itself(path):
    """``Component.Message`` is set by ``csc_gh.messages.set_state`` only."""
    for node in ast.walk(ast.parse(_source(path))):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for target in targets:
            assert not (isinstance(target, ast.Attribute)
                        and target.attr == 'Message'), (
                '%s line %d assigns .Message' % (path.name, node.lineno))


@pytest.mark.parametrize('path', _migrated(), ids=lambda p: p.stem)
def test_a_component_checks_its_outputs_before_it_runs(path):
    """The class of the component (not a helper class of the file) carries the
    output state, BeforeRunScript checks the outputs, RunScript stops early
    when it has to (8.112)."""
    tree = ast.parse(_source(path))
    cls = [n for n in tree.body if isinstance(n, ast.ClassDef)
           and n.name.startswith('CSC_')][0]
    assigned = {n.targets[0].id for n in cls.body
                if isinstance(n, ast.Assign)
                and isinstance(n.targets[0], ast.Name)}
    assert {'_outputs_ready', '_outputs_note'} <= assigned
    methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
    assert {'_stop', '_check_outputs', '_state', 'BeforeRunScript',
            'RunScript'} <= set(methods)
    calls = [ast.unparse(n.func) for n in ast.walk(methods['BeforeRunScript'])
             if isinstance(n, ast.Call)]
    assert 'self._check_outputs' in calls
    body = [n for n in methods['RunScript'].body
            if not (isinstance(n, ast.Expr)
                    and isinstance(n.value, ast.Constant))]
    first = ast.unparse(body[0])
    assert first.startswith('if self._stop():'), (path.name, first)
