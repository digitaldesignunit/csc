"""The client library in one namespace: the names of the modules of the
``csc_gh`` package merged in dependency order (what the tests of the pure
modules, and the headless Rhino tests, index by name). ``fresh=True`` reloads
the modules first, so a test that changes an environment variable (e.g.
``CSC_MESH_BUILD_MODE``) gets a library that reads it afresh; the default
leaves them alone, so exception classes stay the same objects across tests."""

from __future__ import annotations

import importlib

# the names the tests use for the modules (the library had these file names
# before it became a package, decision 8.111)
SHORT = {'csc_ply': 'ply', 'csc_build': 'build', 'csc_read': 'read',
         'csc_convention': 'convention', 'csc_frame': 'frame',
         'csc_rhino': 'rhino', 'csc_doc': 'doc', 'csc_upload': 'upload'}
ORDER = ('csc_ply', 'csc_build', 'csc_read', 'csc_convention', 'csc_frame',
         'csc_rhino', 'csc_doc')


def namespace(names=ORDER, fresh=False):
    scope = {'__name__': 'embedded'}
    for name in names:
        module = importlib.import_module('csc_gh.' + SHORT[name])
        if fresh:
            module = importlib.reload(module)
        scope.update({key: value for key, value in vars(module).items()
                      if not key.startswith('__')})
    return scope
