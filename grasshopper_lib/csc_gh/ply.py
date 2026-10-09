# PLY reading and writing with numpy (decision 8.92). Pure: no Rhino import.
#
# Part of the package csc_gh (decision 8.111).
# Python 3.9 compatible (Rhino 8 CPython).

import numpy as np  # NOQA

_PLY_TYPES = {
    'char': 'i1', 'int8': 'i1',
    'uchar': 'u1', 'uint8': 'u1',
    'short': 'i2', 'int16': 'i2',
    'ushort': 'u2', 'uint16': 'u2',
    'int': 'i4', 'int32': 'i4',
    'uint': 'u4', 'uint32': 'u4',
    'float': 'f4', 'float32': 'f4',
    'double': 'f8', 'float64': 'f8',
}


class PlyError(ValueError):
    """The bytes are not a PLY this client reads."""


def _split_header(data):
    """(header text, offset of the first body byte)."""
    head = bytes(data[:65536])
    marker = b'end_header'
    at = head.find(marker)
    if at == -1:
        raise PlyError('PLY: missing end_header')
    end = at + len(marker)
    if head[end:end + 2] == b'\r\n':
        end += 2
    elif head[end:end + 1] == b'\n':
        end += 1
    else:
        raise PlyError('PLY: malformed end_header')
    return head[:at].decode('ascii', 'ignore'), end


def _parse_header(text):
    """Elements in file order: [name, count, [property, ...]]."""
    elements = []
    binary_le = False
    for raw in text.splitlines():
        tok = raw.split()
        if not tok:
            continue
        if tok[0] == 'format':
            binary_le = tok[1] == 'binary_little_endian'
        elif tok[0] == 'element':
            elements.append([tok[1], int(tok[2]), []])
        elif tok[0] == 'property' and elements:
            if tok[1] == 'list':
                elements[-1][2].append(
                    ('list', tok[4], _PLY_TYPES[tok[2]], _PLY_TYPES[tok[3]]))
            else:
                elements[-1][2].append(('scalar', tok[2], _PLY_TYPES[tok[1]]))
    if not binary_le:
        raise PlyError('PLY: only binary_little_endian is supported')
    return elements


def parse_ply(data):
    """Parse a binary little-endian PLY into numpy arrays.

    Returns a dict: ``vertices`` (n, 3) float64, ``colors`` (n, 3) uint8 or
    None, ``faces`` (m, 3) int32 (polygons are fan-triangulated; empty when
    the file has no faces).
    """
    text, offset = _split_header(data)
    elements = _parse_header(text)
    buffer = memoryview(data)
    vertices = None
    colors = None
    faces = np.zeros((0, 3), dtype=np.int32)
    for name, count, props in elements:
        if name == 'vertex' and all(p[0] == 'scalar' for p in props):
            dtype = np.dtype([(p[1], '<' + p[2]) for p in props])
            block = np.frombuffer(buffer, dtype=dtype, count=count,
                                  offset=offset)
            offset += count * dtype.itemsize
            fields = dtype.names
            if not all(axis in fields for axis in ('x', 'y', 'z')):
                raise PlyError('PLY: vertex needs x, y and z')
            vertices = np.column_stack(
                [block['x'], block['y'], block['z']]).astype(np.float64)
            if all(c in fields for c in ('red', 'green', 'blue')):
                colors = np.column_stack(
                    [block['red'], block['green'], block['blue']]
                ).astype(np.uint8)
        elif name == 'face' and props and props[0][0] == 'list':
            faces, offset = _parse_faces(buffer, offset, count, props)
        else:
            offset = _skip_element(buffer, offset, count, props)
    if vertices is None:
        raise PlyError('PLY: no vertex element')
    return {'vertices': vertices, 'colors': colors, 'faces': faces}


def _skip_element(buffer, offset, count, props):
    if all(p[0] == 'scalar' for p in props):
        row = np.dtype([(p[1], '<' + p[2]) for p in props])
        return offset + count * row.itemsize
    for _ in range(count):  # rare: an unknown element with lists, walk it
        for p in props:
            if p[0] == 'scalar':
                offset += np.dtype('<' + p[2]).itemsize
            else:
                n = int(np.frombuffer(buffer, dtype='<' + p[2], count=1,
                                      offset=offset)[0])
                offset += np.dtype('<' + p[2]).itemsize
                offset += n * np.dtype('<' + p[3]).itemsize
    return offset


def _parse_faces(buffer, offset, count, props):
    lists = [p for p in props if p[0] == 'list']
    index_prop = next((p for p in lists if p[1] in (
        'vertex_indices', 'vertex_index')), lists[0])
    if count == 0:
        return np.zeros((0, 3), dtype=np.int32), offset
    # fast path: one list property, every face the same size
    if len(props) == 1:
        count_t, index_t = '<' + index_prop[2], '<' + index_prop[3]
        n = int(np.frombuffer(buffer, dtype=count_t, count=1,
                              offset=offset)[0])
        dtype = np.dtype([('n', count_t), ('i', index_t, (n,))])
        end = offset + count * dtype.itemsize
        if end <= len(buffer):
            block = np.frombuffer(buffer, dtype=dtype, count=count,
                                  offset=offset)
            if np.all(block['n'] == n):
                return _fan(block['i'].astype(np.int32)), end
    # general path: faces of different sizes (triangles with quads)
    rows = []
    for _ in range(count):
        for p in props:
            if p[0] == 'scalar':
                offset += np.dtype('<' + p[2]).itemsize
                continue
            n = int(np.frombuffer(buffer, dtype='<' + p[2], count=1,
                                  offset=offset)[0])
            offset += np.dtype('<' + p[2]).itemsize
            row = np.frombuffer(buffer, dtype='<' + p[3], count=n,
                                offset=offset)
            offset += n * np.dtype('<' + p[3]).itemsize
            if p is index_prop:
                rows.append(row.astype(np.int32))
    out = []
    for row in rows:
        for k in range(1, len(row) - 1):
            out.append((row[0], row[k], row[k + 1]))
    return np.asarray(out, dtype=np.int32).reshape(-1, 3), offset


def _fan(polygons):
    """(m, n) polygon indices -> (m * (n - 2), 3) triangles."""
    n = polygons.shape[1]
    if n == 3:
        return np.ascontiguousarray(polygons)
    if n < 3:
        return np.zeros((0, 3), dtype=np.int32)
    parts = [polygons[:, [0, k, k + 1]] for k in range(1, n - 1)]
    return np.ascontiguousarray(np.concatenate(parts, axis=0))


def _colors(colors, n):
    """One rgb for all, or one per vertex, as (n, 3) uint8."""
    array = np.asarray(colors)
    if array.ndim == 1:
        array = np.tile(array.reshape(1, 3), (n, 1))
    return np.clip(array.reshape(-1, 3), 0, 255).astype(np.uint8)


def write_ply_mesh(vertices, faces, colors=None):
    """Binary little-endian PLY of a triangle mesh (float x y z, uchar rgb
    when ``colors`` is given, ``list uchar int vertex_indices``)."""
    vertices = np.asarray(vertices, dtype=np.float32).reshape(-1, 3)
    faces = np.asarray(faces, dtype=np.int32).reshape(-1, 3)
    n, m = len(vertices), len(faces)
    head = ['ply', 'format binary_little_endian 1.0', 'element vertex %d' % n,
            'property float x', 'property float y', 'property float z']
    fields = [('x', '<f4'), ('y', '<f4'), ('z', '<f4')]
    if colors is not None:
        head += ['property uchar red', 'property uchar green',
                 'property uchar blue']
        fields += [('red', 'u1'), ('green', 'u1'), ('blue', 'u1')]
    head += ['element face %d' % m,
             'property list uchar int vertex_indices', 'end_header']
    block = np.empty(n, dtype=np.dtype(fields))
    block['x'], block['y'], block['z'] = (
        vertices[:, 0], vertices[:, 1], vertices[:, 2])
    if colors is not None:
        rgb = _colors(colors, n)
        block['red'], block['green'], block['blue'] = (
            rgb[:, 0], rgb[:, 1], rgb[:, 2])
    face_block = np.empty(m, dtype=np.dtype([('n', 'u1'), ('i', '<i4', (3,))]))
    face_block['n'] = 3
    face_block['i'] = faces
    return ('\n'.join(head) + '\n').encode('ascii') + block.tobytes() \
        + face_block.tobytes()


def write_ply_cloud(points, colors=None):
    """Binary little-endian PLY of a point cloud (vertices only)."""
    points = np.asarray(points, dtype=np.float32).reshape(-1, 3)
    n = len(points)
    head = ['ply', 'format binary_little_endian 1.0', 'element vertex %d' % n,
            'property float x', 'property float y', 'property float z']
    fields = [('x', '<f4'), ('y', '<f4'), ('z', '<f4')]
    if colors is not None:
        head += ['property uchar red', 'property uchar green',
                 'property uchar blue']
        fields += [('red', 'u1'), ('green', 'u1'), ('blue', 'u1')]
    head.append('end_header')
    block = np.empty(n, dtype=np.dtype(fields))
    block['x'], block['y'], block['z'] = (
        points[:, 0], points[:, 1], points[:, 2])
    if colors is not None:
        rgb = _colors(colors, n)
        block['red'], block['green'], block['blue'] = (
            rgb[:, 0], rgb[:, 1], rgb[:, 2])
    return ('\n'.join(head) + '\n').encode('ascii') + block.tobytes()
