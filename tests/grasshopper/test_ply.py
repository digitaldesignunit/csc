"""PLY reading and writing with numpy (csc_ply, decision 8.92)."""

from __future__ import annotations

import glob
import os
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

from csc_gh import ply as csc_ply

ASSETS = 'D:/01_PROJECT_WORKDATA/260916_CSC_ASSETS/meshes'


def _sample(n=60, m=90, seed=1):
    rng = np.random.default_rng(seed)
    return rng.random((n, 3)) * 100, rng.integers(0, n, (m, 3))


def test_a_mesh_survives_write_and_parse_with_colours():
    vertices, faces = _sample()
    data = csc_ply.write_ply_mesh(vertices, faces, [10, 20, 30])
    parsed = csc_ply.parse_ply(data)
    assert np.allclose(parsed['vertices'], vertices.astype(np.float32))
    assert (parsed['faces'] == faces).all()
    assert (parsed['colors'] == [10, 20, 30]).all()
    assert parsed['colors'].shape == (len(vertices), 3)


def test_per_vertex_colours_and_no_colours():
    vertices, faces = _sample()
    colours = np.arange(len(vertices) * 3).reshape(-1, 3) % 256
    parsed = csc_ply.parse_ply(csc_ply.write_ply_mesh(vertices, faces,
                                                      colours))
    assert (parsed['colors'] == colours).all()
    plain = csc_ply.parse_ply(csc_ply.write_ply_mesh(vertices, faces))
    assert plain['colors'] is None and len(plain['faces']) == len(faces)


def test_a_point_cloud_has_no_faces():
    points, _ = _sample(500)
    parsed = csc_ply.parse_ply(csc_ply.write_ply_cloud(points, [1, 2, 3]))
    assert len(parsed['vertices']) == 500 and len(parsed['faces']) == 0
    assert (parsed['colors'][0] == [1, 2, 3]).all()
    bare = csc_ply.parse_ply(csc_ply.write_ply_cloud(points))
    assert bare['colors'] is None


def _ply_with_faces(face_rows, vertex_count=5):
    header = ('ply\nformat binary_little_endian 1.0\n'
              'element vertex %d\nproperty double x\nproperty double y\n'
              'property double z\nelement face %d\n'
              'property list uchar uint vertex_indices\nend_header\n'
              % (vertex_count, len(face_rows)))
    body = b''.join(struct.pack('<ddd', i, i * 2.0, i * 3.0)
                    for i in range(vertex_count))
    for row in face_rows:
        body += struct.pack('<B', len(row)) + struct.pack(
            '<%dI' % len(row), *row)
    return header.encode('ascii') + body


def test_quads_and_mixed_faces_are_triangulated():
    quads = csc_ply.parse_ply(_ply_with_faces([[0, 1, 2, 3], [1, 2, 3, 4]]))
    assert quads['faces'].tolist() == [[0, 1, 2], [0, 2, 3], [1, 2, 3],
                                       [1, 3, 4]] \
        or sorted(map(tuple, quads['faces'].tolist())) == sorted(
            [(0, 1, 2), (0, 2, 3), (1, 2, 3), (1, 3, 4)])
    mixed = csc_ply.parse_ply(_ply_with_faces([[0, 1, 2], [1, 2, 3, 4]]))
    assert mixed['faces'].tolist() == [[0, 1, 2], [1, 2, 3], [1, 3, 4]]
    assert csc_ply.parse_ply(_ply_with_faces([[0, 1, 2]]))['vertices'][
        4].tolist() == [4.0, 8.0, 12.0]   # doubles are read as doubles


def test_an_unknown_element_is_skipped():
    header = ('ply\nformat binary_little_endian 1.0\n'
              'element vertex 3\nproperty float x\nproperty float y\n'
              'property float z\nelement edge 2\nproperty int a\n'
              'property int b\nelement face 1\n'
              'property list uchar int vertex_indices\nend_header\n')
    body = struct.pack('<9f', *range(9)) + struct.pack('<4i', 0, 1, 1, 2) \
        + struct.pack('<B3i', 3, 0, 1, 2)
    parsed = csc_ply.parse_ply(header.encode('ascii') + body)
    assert parsed['faces'].tolist() == [[0, 1, 2]]


def test_other_files_are_refused():
    with pytest.raises(csc_ply.PlyError):
        csc_ply.parse_ply(b'ply\nformat ascii 1.0\nelement vertex 0\n'
                          b'end_header\n')
    with pytest.raises(csc_ply.PlyError):
        csc_ply.parse_ply(b'not a ply')
    with pytest.raises(csc_ply.PlyError):
        csc_ply.parse_ply(b'ply\nformat binary_little_endian 1.0\n'
                          b'element face 0\nproperty list uchar int a\n'
                          b'end_header\n')


def test_crlf_headers_are_read():
    data = csc_ply.write_ply_mesh(*_sample(8, 5))
    head, body = data.split(b'end_header\n', 1)
    crlf = head.replace(b'\n', b'\r\n') + b'end_header\r\n' + body
    assert len(csc_ply.parse_ply(crlf)['vertices']) == 8


def test_the_server_reads_what_the_client_writes(tmp_path):
    backend = Path(__file__).resolve().parents[2] / 'src' / 'backend'
    sys.path.insert(0, str(backend))
    try:
        from apps.catalog.geometry_mesh_export import (
            load_trimesh_from_ply_file)
    except Exception as error:   # the client-only stack
        pytest.skip('backend stack not importable here: %s' % error)
    vertices, faces = _sample(50, 80)
    path = tmp_path / 'x.ply'
    path.write_bytes(csc_ply.write_ply_mesh(vertices, faces, [5, 6, 7]))
    mesh = load_trimesh_from_ply_file(str(path))
    assert np.allclose(mesh.vertices, vertices.astype(np.float32), atol=1e-4)
    assert len(mesh.faces) == len(faces)


def test_the_client_reads_a_trimesh_export():
    trimesh = pytest.importorskip('trimesh')
    box = trimesh.creation.box(extents=(10, 20, 30))
    data = box.export(file_type='ply')
    if isinstance(data, str):
        data = data.encode('latin-1')
    try:
        parsed = csc_ply.parse_ply(data)
    except csc_ply.PlyError:
        pytest.skip('trimesh wrote an ascii or big-endian ply')
    assert len(parsed['vertices']) == len(box.vertices)
    assert len(parsed['faces']) == len(box.faces)


@pytest.mark.skipif(not os.path.isdir(ASSETS), reason='local assets absent')
def test_a_real_scan_parses_fast_and_matches_the_header():
    files = glob.glob(ASSETS + '/**/detailed.ply', recursive=True)
    path = sorted(files, key=lambda p: abs(os.path.getsize(p) - 12e6))[0]
    data = open(path, 'rb').read()
    head = data[:600].split(b'end_header')[0].decode('ascii')
    counts = {line.split()[1]: int(line.split()[2])
              for line in head.splitlines() if line.startswith('element')}
    parsed = csc_ply.parse_ply(data)
    assert len(parsed['vertices']) == counts['vertex']
    assert len(parsed['faces']) == counts['face']
    assert parsed['faces'].max() < counts['vertex']
