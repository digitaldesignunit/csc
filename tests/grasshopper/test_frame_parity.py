"""The client's frame (csc_frame) equals the server's (apps/catalog/frame.py).

Shared fixtures in tests/fixtures/frame_parity are written by the server's
``compute_frame`` (``python tests/grasshopper/frame_cases.py --write``).
* ``test_fixtures_are_current`` (needs the backend stack) fails when a fixture
  no longer matches the server -- also when FRAME_VERSION moved;
* ``test_client_reproduces_the_server`` runs anywhere the client libraries
  import (the Rhino 8 pins numpy 2.0.2 / scipy 1.13.1 / trimesh 4.12.2 as well
  as the server's stack): axes, signs, extents and origin must agree.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

import frame_cases
from csc_gh import frame as csc_frame

FIXTURES = sorted(frame_cases.FIXTURE_DIR.glob('*.json'))
AXES_ATOL = 1e-4
LENGTH_RTOL = 1e-4
LENGTH_ATOL = 1e-3


def _load(path):
    return json.loads(path.read_text(encoding='ascii'))


def _axes(frame):
    return np.array([frame['x'], frame['y'], frame['z']])


def test_every_case_has_a_fixture():
    names = {case[0] for case in frame_cases.build_cases()}
    assert names == {p.stem for p in FIXTURES}, (
        'run: python tests/grasshopper/frame_cases.py --write')


@pytest.mark.parametrize('path', FIXTURES, ids=lambda p: p.stem)
def test_client_reproduces_the_server(path):
    doc = _load(path)
    expected = doc['expected']
    result = csc_frame.compute_frame(
        np.array(doc['points']), original_function=doc['original_function'])
    assert csc_frame.FRAME_VERSION == expected['frame_version']
    assert np.allclose(result['bbx'], expected['bbx'],
                       rtol=LENGTH_RTOL, atol=LENGTH_ATOL)
    assert np.allclose(result['frame']['o'], expected['frame']['o'],
                       rtol=LENGTH_RTOL, atol=LENGTH_ATOL)
    got, want = _axes(result['frame']), _axes(expected['frame'])
    if doc['round_section']:
        # the angle about the long axis of a round section is arbitrary:
        # the long axis (x) with its sign and the extents must agree
        assert np.allclose(got[0], want[0], atol=AXES_ATOL)
    else:
        assert np.allclose(got, want, atol=AXES_ATOL), (
            'axes differ:\n%s\nvs\n%s' % (got, want))
    # right-handed and orthonormal whatever the case
    assert np.allclose(got @ got.T, np.eye(3), atol=1e-9)
    assert np.dot(np.cross(got[0], got[1]), got[2]) > 0


def test_fixtures_are_current():
    backend = Path(__file__).resolve().parents[2] / 'src' / 'backend'
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    try:
        import apps.catalog.frame  # noqa: F401
    except Exception as error:   # the client-only (Rhino 8) stack
        pytest.skip('backend stack not importable here: %s' % error)
    stale = []
    for path in FIXTURES:
        doc = _load(path)
        now = frame_cases.server_expected(
            np.array(doc['points']), doc['original_function'])
        old = doc['expected']
        same = (now['frame_version'] == old['frame_version']
                and np.allclose(_axes(now['frame']), _axes(old['frame']),
                                atol=1e-6)
                and np.allclose(now['frame']['o'], old['frame']['o'],
                                atol=1e-4)
                and np.allclose(now['bbx'], old['bbx'], atol=1e-4))
        if not same:
            stale.append(path.stem)
    assert not stale, (
        'the server frame changed for %s: run python '
        'tests/grasshopper/frame_cases.py --write, then update csc_frame.py '
        'and its FRAME_VERSION' % stale)
