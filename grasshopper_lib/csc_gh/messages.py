"""Runtime messages of the script components (decision 8.113).

Four levels, one meaning each:

* ``error`` (red): a real failure --- a server error, invalid data, a failed
  build, an unexpected exception;
* ``warn`` (orange): a missing or empty input (Grasshopper's own convention,
  "Input parameter X failed to collect data": the component returns empty
  outputs and does not raise) and a skipped item, which the text names;
* ``remark`` (grey): a normal hint --- a cache hit, nothing to do, an output
  check that was skipped;
* ``state``: the one short text under the component (``Component.Message``):
  "Logged in", "12 fetched", "Run is False". Most components leave it empty.
  This module is the only place that assigns it.

The functions take the script instance of the component (``self`` in
``RunScript``). Components keep small local methods that do the same
(``_addWarning`` ...) and call these when the library is installed, so a
missing library never blocks a component. Pure Python; no Grasshopper import
(the levels come from the component).
"""


def _add(instance, level_name, text):
    levels = instance.Component.RuntimeMessageLevel
    instance.AddRuntimeMessage(getattr(levels, level_name), str(text))


def error(instance, text):
    _add(instance, 'Error', text)


def warn(instance, text):
    _add(instance, 'Warning', text)


def remark(instance, text):
    _add(instance, 'Remark', text)


def set_state(component, text=''):
    """The short state under the component; an empty text clears it."""
    component.Message = str(text or '')


def is_empty(value):
    """An input that carries nothing: None, '', or an empty list / tree."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ''
    count = getattr(value, 'DataCount', None)         # a DataTree
    if count is not None:
        return count == 0
    try:
        return len(value) == 0
    except TypeError:
        return False


def missing_inputs(**inputs):
    """The names of the inputs (given as ``Name=value``) that carry nothing,
    in the order given."""
    return [name for name, value in inputs.items() if is_empty(value)]


def missing_text(name):
    return 'Input parameter %s failed to collect data' % name


def check_inputs(instance, **inputs):
    """Warn (never error) for every required input that carries nothing;
    returns True when all are there. The component then returns empty
    outputs and does not raise."""
    names = missing_inputs(**inputs)
    for name in names:
        warn(instance, missing_text(name))
    return not names
