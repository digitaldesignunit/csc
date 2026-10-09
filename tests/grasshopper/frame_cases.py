"""Shared geometries of the frame parity test (audit 4.3, decision 8.94 c).

``CASES`` are deterministic point sets with the piece's ``original_function``.
``python tests/grasshopper/frame_cases.py --write`` lets the SERVER's
``compute_frame`` (apps/catalog/frame.py) write the expected frame of each
into ``tests/fixtures/frame_parity/<name>.json``; the client's ``csc_frame``
must reproduce it (``test_frame_parity.py``), and a staleness test fails when
a fixture no longer matches the server.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

FIXTURE_DIR = Path(__file__).resolve().parents[1] / 'fixtures' / 'frame_parity'


def _box_corners(sx, sy, sz):
    return np.array([[x, y, z] for x in (-.5, .5) for y in (-.5, .5)
                     for z in (-.5, .5)]) * [sx, sy, sz]


def _rot(axis, degrees):
    a = np.radians(degrees)
    c, s = np.cos(a), np.sin(a)
    if axis == 'x':
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == 'y':
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def _place(points, rotation=None, shift=(0.0, 0.0, 0.0)):
    points = np.asarray(points, dtype=float)
    if rotation is not None:
        points = points @ rotation.T
    return points + np.asarray(shift, dtype=float)


def _surface_samples(sx, sy, sz, n, seed):
    """Points on the six faces of a box (a scan-like sampling)."""
    rng = np.random.default_rng(seed)
    out = []
    for axis, size in enumerate((sx, sy, sz)):
        for sign in (-1, 1):
            p = (rng.random((n, 3)) - .5) * [sx, sy, sz]
            p[:, axis] = sign * size / 2
            out.append(p)
    return np.vstack(out)


def _cylinder(radius, length, n, seed):
    rng = np.random.default_rng(seed)
    theta = rng.random(n) * 2 * np.pi
    x = (rng.random(n) - .5) * length
    return np.column_stack([x, radius * np.cos(theta), radius * np.sin(theta)])


def _ellipsoid(a, b, c, n, seed):
    rng = np.random.default_rng(seed)
    v = rng.normal(size=(n, 3))
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    return v * [a, b, c]


def _l_slab(n, seed):
    rng = np.random.default_rng(seed)
    a = (rng.random((n, 3)) - .5) * [600, 200, 40]
    b = (rng.random((n, 3)) - .5) * [200, 500, 40] + [-200, 350, 0]
    return np.vstack([a, b])


def build_cases():
    """``[(name, original_function, round_section, points (n, 3))]``."""
    cases = [
        ('lying_box', 'IfcBeam', False, _box_corners(400, 200, 50)),
        ('box_rotated_z_30', 'IfcBeam', False,
         _place(_box_corners(400, 200, 50), _rot('z', 30))),
        ('box_rotated_xyz', None, False,
         _place(_box_corners(380, 210, 60),
                _rot('x', 12) @ _rot('y', -20) @ _rot('z', 75),
                (35, -20, 14))),
        ('length_along_z', None, False, _box_corners(50, 200, 400)),
        ('standing_column', 'IfcColumn', False, _box_corners(1000, 100, 120)),
        ('standing_column_rotated', 'IfcColumn', False,
         _place(_box_corners(1000, 100, 120), _rot('y', 90) @ _rot('z', 17))),
        ('short_column_fragment', 'IfcColumn', False,
         _box_corners(150, 100, 80)),
        ('tied_extents', 'IfcSlab', False, _box_corners(200, 198, 50)),
        ('tied_within_3_mm', 'IfcSlab', False, _box_corners(200, 197.5, 40)),
        ('upside_down_input', 'IfcBeam', False,
         _place(_box_corners(400, 200, 50), _rot('x', 180))),
        ('shifted_box', 'IfcBeam', False,
         _place(_box_corners(400, 200, 50), None, (1000, -500, 250))),
        ('sheet_four_corners', 'IfcPlate', False,
         np.array([[0, 0, 0], [300, 0, 0], [300, 200, 0], [0, 200, 0.0]])),
        ('sheet_samples_rotated', 'IfcPlate', False,
         _place(np.column_stack([
             (np.random.default_rng(3).random(300) - .5) * 400,
             (np.random.default_rng(4).random(300) - .5) * 250,
             np.zeros(300)]), _rot('x', 33) @ _rot('z', 8))),
        ('box_surface_scan', 'IfcBeam', False,
         _place(_surface_samples(420, 190, 70, 150, 5),
                _rot('z', 47) @ _rot('y', 5))),
        ('l_shaped_slab', 'IfcSlab', False,
         _place(_l_slab(400, 6), _rot('z', 21))),
        ('ellipsoid_rubble', 'CscDebris', False,
         _place(_ellipsoid(200, 130, 70, 500, 7),
                _rot('x', 40) @ _rot('y', 25))),
        ('round_section_lying', 'IfcMember', True,
         _cylinder(40, 600, 600, 8)),
        ('round_section_rotated', 'IfcMember', True,
         _place(_cylinder(40, 600, 600, 9), _rot('z', 63) @ _rot('y', 22))),
    ]
    return [(n, f, r, np.round(p, 6)) for n, f, r, p in cases]


def server_expected(points, original_function):
    """The server's frame for the points (needs the backend on sys.path)."""
    from apps.catalog.frame import FRAME_VERSION, compute_frame
    result = compute_frame(np.asarray(points, dtype=float),
                           original_function=original_function)
    return {
        'frame': result.frame, 'bbx': list(result.bbx),
        'obb_extents': list(result.obb_extents),
        'frame_version': FRAME_VERSION,
    }


def fixture_document(name, original_function, round_section, points):
    return {
        'name': name, 'original_function': original_function,
        'round_section': round_section,
        'points': np.asarray(points).tolist(),
        'expected': server_expected(points, original_function),
    }


def write_fixtures():
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    keep = set()
    for case in build_cases():
        path = FIXTURE_DIR / (case[0] + '.json')
        path.write_text(json.dumps(fixture_document(*case), indent=1) + '\n',
                        encoding='ascii')
        keep.add(path.name)
    for stale in FIXTURE_DIR.glob('*.json'):
        if stale.name not in keep:
            stale.unlink()
    return sorted(keep)


if __name__ == '__main__':
    backend = Path(__file__).resolve().parents[2] / 'src' / 'backend'
    sys.path.insert(0, str(backend))
    if '--write' in sys.argv:
        print('wrote %d fixtures into %s' % (len(write_fixtures()),
                                             FIXTURE_DIR))
    else:
        print(__doc__)
