"""Tests of the Grasshopper client libraries outside Rhino (plan P8).

``grasshopper_lib`` holds the package ``csc_gh`` the script components import; it is
put on the path here. The tests that need RhinoCommon run only in a headless
Rhino (``CSC_TEST_RHINO=1`` with rhinoinside importable, see
``test_rhino_headless.py``).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _path in (_ROOT / 'grasshopper_lib', Path(__file__).resolve().parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _undo_library_patches():
    yield
    import compstub
    compstub.undo_patches()
