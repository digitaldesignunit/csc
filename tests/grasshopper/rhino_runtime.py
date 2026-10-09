"""Start Rhino 8 inside the test process the way Rhino 8 runs its own
CPython 3.9 scripts: on .NET 7 (CoreCLR), which is also what the D2P wrapper
needs (its bundled D2P.Core.dll). ``CSC_TEST_RHINO_SYSTEM`` names the Rhino
System folder when Rhino is not in its default place."""

from __future__ import annotations

import os

DEFAULT_SYSTEM = r'C:\Program Files\Rhino 8\System'


def load():
    import rhinoinside
    system = os.environ.get('CSC_TEST_RHINO_SYSTEM', DEFAULT_SYSTEM)
    if os.path.isdir(system):
        rhinoinside.load(system, 'net7.0')
    else:
        rhinoinside.load()
