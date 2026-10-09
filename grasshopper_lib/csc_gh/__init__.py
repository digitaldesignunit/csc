"""The shared Grasshopper client library of CSC (decision 8.111).

One package, installed to ``%APPDATA%\\McNeel\\Rhinoceros\\8.0\\scripts\\csc_gh``
(Rhino 8 puts that folder on ``sys.path`` of every Python 3 script, both
``# venv:`` environments run in one interpreter). The script components
``import csc_gh`` and take what they need from its modules; they carry no copy
of it. ``CSC_Update`` installs the package together with the UserObjects.

Modules (importing the package imports none of them, so a component without
Rhino, or without numpy, can still check the version):

* ``ply``, ``build``, ``read``, ``convention``, ``frame``, ``upload`` --- pure
  Python (numpy for arrays), no Rhino;
* ``rhino``, ``doc`` --- RhinoCommon: geometry, the document convention;
* ``ports`` --- the declared outputs of a script component (8.112);
* ``messages`` --- the runtime message levels and the state text (8.113).

The version has the shape of a component's ``Version:`` line (six digits and
an optional letter: ``261005``, ``261005a``), so the updater compares both the
same way. Python 3.9 compatible (Rhino 8).
"""

import importlib
import os
import re
import sys

__version__ = '261008'

# in dependency order: a module is reloaded after the ones it imports from
MODULES = ('ply', 'build', 'read', 'convention', 'frame', 'upload', 'rhino',
           'doc', 'messages', 'ports')

_VERSION = re.compile(r'^(\d+)([a-zA-Z]?)$')


class LibraryTooOld(ImportError):
    """The installed ``csc_gh`` is older than a component needs."""


def version_key(version):
    """Sort key of a version text (``'261005a'`` after ``'261005'``)."""
    match = _VERSION.match(str(version).strip())
    if match is None:
        raise ValueError('not a csc_gh version: %r' % (version,))
    return (int(match.group(1)), match.group(2).lower())


def is_at_least(minimum):
    return version_key(__version__) >= version_key(minimum)


def require(minimum):
    """Raise ``LibraryTooOld`` (an ``ImportError``) when the installed
    library is older than ``minimum``."""
    if not is_at_least(minimum):
        raise LibraryTooOld('csc_gh %s is installed, %s is needed'
                            % (__version__, minimum))


def problem_text(minimum):
    """The one message a component shows when the library is missing or too
    old."""
    return ('CSC library %s too old or missing: run CSC_Update, then restart '
            'Rhino' % minimum)


def dev_reload_wanted():
    return os.environ.get('CSC_DEV_RELOAD', '').strip() not in ('', '0')


def reload_modules(namespace=None):
    """Reload the loaded modules of the package in dependency order
    (``importlib.reload``) and, given ``namespace`` (a component's
    ``globals()``), point the names it took from them (``from csc_gh.build
    import x``) at the new objects. A name is rebound only when it is
    identical to the old object of the same name in a reloaded module.

    Returns the reloaded module names. For development: the junction of the
    scripts folder to the repository (``grasshopper_development/README.md``)
    plus ``CSC_DEV_RELOAD=1``."""
    old = {}
    for name in MODULES:
        module = sys.modules.get('%s.%s' % (__name__, name))
        if module is not None:
            old[name] = dict(vars(module))
    reloaded = []
    for name in MODULES:
        module = sys.modules.get('%s.%s' % (__name__, name))
        if module is not None:
            importlib.reload(module)
            reloaded.append(name)
    if namespace is not None:
        for key, value in list(namespace.items()):
            for name, before in old.items():
                if key in before and before[key] is value:
                    fresh = getattr(sys.modules['%s.%s' % (__name__, name)],
                                    key, value)
                    namespace[key] = fresh
                    break
    return reloaded


def dev_reload(namespace=None):
    """``reload_modules`` when ``CSC_DEV_RELOAD`` is set, else nothing; a
    component calls it once per solve with its ``globals()``."""
    if dev_reload_wanted():
        return reload_modules(namespace)
    return []
