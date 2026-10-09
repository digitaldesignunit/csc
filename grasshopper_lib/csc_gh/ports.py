"""The outputs of a script component, declared in its source (decision 8.112).

A component lists ``OUTPUTS = [(name, nickname, description), ...]`` in the
order ``RunScript`` returns them, and calls ``ensure_outputs`` from
``BeforeRunScript``. The helper makes the outputs of the component match:

* nothing to do (names, nicknames and order match): only the descriptions are
  set, and the run goes on;
* otherwise it renames in place by index (the wires stay), adds what is
  missing with the parameter the Rhino 8 script component creates itself
  (``IGH_VariableParameterComponent.CreateParameter``, not a generic
  parameter: the component maps the returned values to its own variable
  parameters) and removes what is too many. The script component's own
  ``out`` output (first, a text) is left alone; the indices count after it.

That is a structural change, and none is made inside the running solution:
the helper schedules it (``GH_Document.ScheduleSolution``); the callback
changes the parameters, runs ``VariableParameterMaintenance`` and
``Params.OnParametersChanged`` and expires the solution. The current run
returns early (``status.ready`` is False, ``status.remark`` says why).

After the change the component is expired (``ExpireSolution(False)``) in the
callback, so the solution that follows solves it again. A second scheduled
pass makes sure of it: when the component has not run again with the matching
outputs, it is expired once more. If even that does not refresh it, the user
recomputes by hand (the remark says so).

The helper never blocks a component: it never raises, and after two tries that
did not make the outputs match it gives up with a remark and lets the run go
on with the outputs the component has.

Components import it in a guard (``try: from csc_gh.ports import
ensure_outputs`` / ``except ImportError: ensure_outputs = None``): without the
library the check is skipped and the component runs with the outputs it has.
RhinoCommon and Grasshopper are imported inside the functions, so the module
imports anywhere.
"""

OWN_OUTPUT = 'out'          # the script component's own text output
MAX_TRIES = 2               # schedules of one signature before giving up

_TRIES = {}                 # component key -> number of schedules
_PROBLEMS = {}              # component key -> text of the last failure
_PENDING = {}               # healed, not yet solved again: component key -> 1
UPDATED = 'outputs updated - recompute if the result does not refresh'


class PortsStatus(object):
    """What ``ensure_outputs`` found: ``ready`` (the run may go on) and
    ``remark`` (a text for the user, or None)."""

    def __init__(self, ready, remark=None):
        self.ready = ready
        self.remark = remark

    def __repr__(self):
        return 'PortsStatus(ready=%r, remark=%r)' % (self.ready, self.remark)


def empty(outputs):
    """What ``RunScript`` returns when it stops early: None for no or one
    output, a tuple of None for several."""
    if len(outputs) <= 1:
        return None
    return tuple(None for _ in outputs)


def own_offset(params):
    """1 when the first output is the script component's own ``out``."""
    if len(params) and params[0].Name == OWN_OUTPUT:
        return 1
    return 0


def matches(params, outputs):
    """Whether the outputs (after ``out``) have the declared names and
    nicknames, in that order and number."""
    offset = own_offset(params)
    if len(params) - offset != len(outputs):
        return False
    for index, (name, nickname, _) in enumerate(outputs):
        param = params[index + offset]
        if param.Name != name or param.NickName != nickname:
            return False
    return True


def set_descriptions(params, outputs):
    offset = own_offset(params)
    for index, (_, _, description) in enumerate(outputs):
        if index + offset < len(params):
            param = params[index + offset]
            if param.Description != description:
                param.Description = description


def _key(component):
    try:
        return str(component.InstanceGuid)
    except Exception:
        return str(id(component))


def _interfaces(component):
    """``(component, variable-parameter component)``: ``ghenv.Component`` of a
    script component is both (it has ``Params`` and ``CreateParameter``), so
    the object itself serves; no cast is needed."""
    return component, component


def _output_side():
    from Grasshopper.Kernel import GH_ParameterSide
    return GH_ParameterSide.Output


def apply(component, outputs, side=None):
    """Make the outputs match (the structural part; called from the scheduled
    callback, never from a running solution). Returns None."""
    plain, variable = _interfaces(component)
    side = _output_side() if side is None else side
    params = plain.Params.Output
    offset = own_offset(params)
    for index, (name, nickname, description) in enumerate(outputs):
        position = index + offset
        if position < len(params):
            param = params[position]
        else:
            param = variable.CreateParameter(side, position)
            plain.Params.RegisterOutputParam(param, position)
        param.Name = name
        param.NickName = nickname
        param.Description = description
    while len(plain.Params.Output) > len(outputs) + offset:
        plain.Params.UnregisterOutputParameter(plain.Params.Output[
            len(plain.Params.Output) - 1])
    variable.VariableParameterMaintenance()
    plain.Params.OnParametersChanged()
    _PENDING[_key(component)] = 1
    plain.ExpireSolution(False)


def _schedule(component, outputs):
    """Hand ``apply`` to the document to run between solutions; False when
    there is no document (the component is not on a canvas)."""
    plain, _ = _interfaces(component)
    document = plain.OnPingDocument()
    if document is None:
        return False
    key = _key(component)

    from Grasshopper.Kernel import GH_Document

    def make_sure(_document):
        # the component has not run again with the matching outputs: expire
        # it once more (the first expire may have been lost)
        try:
            if _PENDING.pop(key, None):
                plain.ExpireSolution(False)
        except Exception as error:
            _PROBLEMS[key] = str(error)

    def callback(_document):
        try:
            apply(component, outputs)
            document.ScheduleSolution(
                5, GH_Document.GH_ScheduleDelegate(make_sure))
        except Exception as error:      # stays out of the solution
            _PROBLEMS[key] = str(error)

    document.ScheduleSolution(1, GH_Document.GH_ScheduleDelegate(callback))
    return True


def ensure_outputs(component, outputs):
    """Make the outputs of ``component`` match ``outputs`` (a list of
    ``(name, nickname, description)`` in return order). Never raises.
    Returns a ``PortsStatus``."""
    try:
        plain, _ = _interfaces(component)
        params = plain.Params.Output
        key = _key(component)
        if matches(params, outputs):
            set_descriptions(params, outputs)
            _TRIES.pop(key, None)
            _PROBLEMS.pop(key, None)
            _PENDING.pop(key, None)         # solved again: healed
            return PortsStatus(True)
        if _TRIES.get(key, 0) >= MAX_TRIES:
            return PortsStatus(True, 'outputs could not be updated%s: the '
                               'component runs with the outputs it has'
                               % (' (%s)' % _PROBLEMS[key]
                                  if key in _PROBLEMS else ''))
        _TRIES[key] = _TRIES.get(key, 0) + 1
        if _schedule(component, outputs):
            return PortsStatus(False, UPDATED)
        apply(component, outputs)
        return PortsStatus(False, UPDATED)
    except Exception as error:
        return PortsStatus(True, 'output check skipped: %s' % error)
