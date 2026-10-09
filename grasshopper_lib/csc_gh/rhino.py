# The Rhino-bound helpers of the Grasshopper bridge (decisions 8.92, 8.95).
#
# Everything that touches RhinoCommon lives here, so a headless Rhino
# (rhinoinside) can run it in a test; the components import it from the
# shared package (decision 8.111). It uses ``ply``, ``build`` and ``read``.
#
# The mesh build is swappable (``MESH_BUILD_MODE``): the measurement of 8.92
# compares the candidates. First numbers (headless Rhino 8.34, the p90 reduced
# mesh of the catalog, 62 136 vertices): one call per element (loop, bulk)
# 3.3 - 4.3 s, blit 0.14 s without colours, Rhino's own importer 0.34 s with
# colours; the median original mesh (281 072 vertices) 15 - 19 s against
# 0.63 s. 'import' is the default; it falls back to 'blit' and that to 'bulk'.
#
# Python 3.9 compatible (Rhino 8 CPython).

import ctypes  # NOQA
import math  # NOQA
import os  # NOQA
import tempfile  # NOQA

import numpy as np  # NOQA

import System  # NOQA
import Rhino  # NOQA

# the other modules of the package
from .ply import (parse_ply, write_ply_cloud, write_ply_mesh)  # NOQA
from .build import (POINT_CLOUD_STAGING_THRESHOLD, box_proxy, geometry_body, inline_mesh, inline_point_cloud, manifest, mesh_levels, prism_proxy)  # NOQA
from .read import (drawable_proxy)  # NOQA

# 'loop' = one call per vertex / face (the 0.5 way), 'bulk' = AddVertices /
# AddFaces with .NET collections, 'blit' = the arrays copied into pinned .NET
# arrays of Point3d / MeshFace, 'import' = Rhino's own PLY importer
# The environment variable CSC_MESH_BUILD_MODE (set before Rhino starts) picks
# another one without editing a script, e.g. if an import ever opens a dialog.
MESH_BUILD_MODES = ('loop', 'bulk', 'blit', 'import')
MESH_BUILD_MODE = os.environ.get('CSC_MESH_BUILD_MODE', 'import')
if MESH_BUILD_MODE not in MESH_BUILD_MODES:
    MESH_BUILD_MODE = 'import'


# NET <-> NUMPY ---------------------------------------------------------------
def to_numpy(net_array, dtype):
    """A .NET primitive array as numpy (buffer protocol, else a copy loop)."""
    try:
        return np.frombuffer(net_array, dtype=dtype).copy()
    except (TypeError, ValueError, BufferError):
        return np.fromiter(net_array, dtype=dtype, count=len(net_array))


# PLANES AND TRANSFORMS -------------------------------------------------------
def plane_from_frame(frame):
    """A Rhino plane from ``{o, x, y, z}`` (z follows from x and y)."""
    return Rhino.Geometry.Plane(
        Rhino.Geometry.Point3d(*[float(v) for v in frame['o'][:3]]),
        Rhino.Geometry.Vector3d(*[float(v) for v in frame['x'][:3]]),
        Rhino.Geometry.Vector3d(*[float(v) for v in frame['y'][:3]]))


def frame_from_plane(plane):
    """``{o, x, y, z}`` of a Rhino plane."""
    return {
        'o': [plane.OriginX, plane.OriginY, plane.OriginZ],
        'x': [plane.XAxis.X, plane.XAxis.Y, plane.XAxis.Z],
        'y': [plane.YAxis.X, plane.YAxis.Y, plane.YAxis.Z],
        'z': [plane.ZAxis.X, plane.ZAxis.Y, plane.ZAxis.Z]}


def transform_from_matrix(matrix):
    """A Rhino transform from a 4x4 row-major matrix (numpy or lists)."""
    xform = Rhino.Geometry.Transform(1.0)
    for row in range(4):
        for col in range(4):
            xform[row, col] = float(matrix[row][col])
    return xform


def canonical_transform(frame):
    """Rhino transform stored -> canonical for a frame (``ApplyFrame``)."""
    return Rhino.Geometry.Transform.PlaneToPlane(
        plane_from_frame(frame), Rhino.Geometry.Plane.WorldXY)


def placement_transform(frame):
    """Rhino transform from a proxy's local axes to stored coordinates."""
    return Rhino.Geometry.Transform.PlaneToPlane(
        Rhino.Geometry.Plane.WorldXY, plane_from_frame(frame))


# BLITTING: numpy <-> .NET arrays of structs -----------------------------------
# Point3d is 3 doubles (24 bytes), MeshFace 4 ints (16 bytes): sequential
# structs, so a pinned array is a block of memory numpy can copy into and out
# of in one call instead of one call per element. The vertices are written as
# float64 into a Point3d array (a float32 block into Point3d corrupts every
# vertex; ``Mesh.Vertices.AddVertices`` is given the Point3d array, which is
# what the Rhino of the user accepts; the Point3f overload failed there).
def _pinned_write(net_array, array):
    handle = System.Runtime.InteropServices.GCHandle.Alloc(
        net_array, System.Runtime.InteropServices.GCHandleType.Pinned)
    try:
        ctypes.memmove(handle.AddrOfPinnedObject().ToInt64(),
                       array.ctypes.data, array.nbytes)
    finally:
        handle.Free()


def _pinned_read(net_array, dtype, width):
    out = np.empty((len(net_array), width), dtype=dtype)
    if len(net_array):
        handle = System.Runtime.InteropServices.GCHandle.Alloc(
            net_array, System.Runtime.InteropServices.GCHandleType.Pinned)
        try:
            ctypes.memmove(out.ctypes.data,
                           handle.AddrOfPinnedObject().ToInt64(), out.nbytes)
        finally:
            handle.Free()
    return out


_BLIT = {}


def blit_works():
    """True when the structs have the layout the blit assumes (checked once
    on a tiny mesh: sizes and the values that come back)."""
    if 'ok' not in _BLIT:
        try:
            marshal = System.Runtime.InteropServices.Marshal
            geometry = Rhino.Geometry
            ok = (marshal.SizeOf(geometry.MeshFace) == 16
                  and marshal.SizeOf(geometry.Point3d) == 24)
            if ok:
                points = System.Array.CreateInstance(geometry.Point3d, 2)
                _pinned_write(points, np.array([[1, 2, 3], [4, 5, 6]],
                                               dtype=np.float64))
                faces = System.Array.CreateInstance(geometry.MeshFace, 1)
                _pinned_write(faces, np.array([[0, 1, 1, 1]],
                                              dtype=np.int32))
                ok = (points[1].Y == 5.0 and points[0].Z == 3.0
                      and faces[0].B == 1 and faces[0].A == 0)
            _BLIT['ok'] = bool(ok)
        except Exception:
            _BLIT['ok'] = False
    return _BLIT['ok']


# VALIDITY GUARD --------------------------------------------------------------
# A mesh, cloud or proxy that is not valid, has a bounding box that is not
# finite, or is wider than this (10 km in mm) is not a piece: it is dropped
# and the component warns with the identity, the kind and the index, instead of
# handing the preview a box of billions of millimetres.
MAX_EXTENT_MM = 1.0e7


def reject_reason(geometry):
    """None when the geometry may be shown, else why not."""
    if geometry is None:
        return 'empty'
    if not geometry.IsValid:
        return 'not valid'
    box = geometry.GetBoundingBox(True)
    if not box.IsValid:
        return 'no bounding box'
    corners = (box.Min.X, box.Min.Y, box.Min.Z, box.Max.X, box.Max.Y,
               box.Max.Z)
    if not all(math.isfinite(value) for value in corners):
        return 'bounding box not finite'
    sides = (box.Max.X - box.Min.X, box.Max.Y - box.Min.Y,
             box.Max.Z - box.Min.Z)
    if max(sides) > MAX_EXTENT_MM:
        return 'bounding box wider than %g mm' % MAX_EXTENT_MM
    return None


def usable(geometry):
    """The geometry, or None when ``reject_reason`` says to drop it."""
    return geometry if reject_reason(geometry) is None else None


# MESH IN ---------------------------------------------------------------------
def _build_loop(vertices, faces, colors):
    mesh = Rhino.Geometry.Mesh()
    for x, y, z in np.asarray(vertices, dtype=np.float64).tolist():
        mesh.Vertices.Add(x, y, z)
    for a, b, c in np.asarray(faces, dtype=np.int64).tolist():
        mesh.Faces.AddFace(a, b, c)
    _set_colors(mesh, colors, len(vertices))
    return mesh


def _build_bulk(vertices, faces, colors):
    mesh = Rhino.Geometry.Mesh()
    points = System.Array[Rhino.Geometry.Point3d](
        [Rhino.Geometry.Point3d(x, y, z) for x, y, z in
         np.asarray(vertices, dtype=np.float64).tolist()])
    mesh.Vertices.AddVertices(points)
    mesh_faces = System.Array[Rhino.Geometry.MeshFace](
        [Rhino.Geometry.MeshFace(a, b, c) for a, b, c in
         np.asarray(faces, dtype=np.int64).tolist()])
    mesh.Faces.AddFaces(mesh_faces)
    _set_colors(mesh, colors, len(vertices))
    return mesh


def _build_blit(vertices, faces, colors):
    if not blit_works():
        return _build_bulk(vertices, faces, colors)
    v = np.ascontiguousarray(vertices, dtype=np.float64).reshape(-1, 3)
    f = np.asarray(faces, dtype=np.int32).reshape(-1, 3)
    quads = np.empty((len(f), 4), dtype=np.int32)
    quads[:, :3] = f
    quads[:, 3] = f[:, 2]            # a triangle: the fourth corner repeats
    mesh = Rhino.Geometry.Mesh()
    points = System.Array.CreateInstance(Rhino.Geometry.Point3d, len(v))
    _pinned_write(points, v)
    mesh.Vertices.AddVertices(points)
    mesh_faces = System.Array.CreateInstance(Rhino.Geometry.MeshFace, len(f))
    _pinned_write(mesh_faces, quads)
    mesh.Faces.AddFaces(mesh_faces)
    _set_colors(mesh, colors, len(v))
    return mesh


def _set_colors(mesh, colors, count):
    """Vertex colours from (n, 3) uint8 (one call per vertex: Color is not a
    blittable struct; the importer path avoids this)."""
    if colors is None or len(colors) != count:
        return
    for r, g, b in np.asarray(colors, dtype=np.int64).tolist():
        mesh.VertexColors.Add(r, g, b)


MESH_BUILDERS = {'loop': _build_loop, 'bulk': _build_bulk,
                 'blit': _build_blit}


def import_geometry(data, suffix='.ply'):
    """The one object Rhino's own importer makes of the bytes of a file
    (a PLY: a mesh or a point cloud, colours and normals kept), as a copy;
    None when the import fails or makes anything else. The file goes through
    a temporary folder and a headless document, never the open one."""
    path = None
    try:
        handle, path = tempfile.mkstemp(suffix=suffix, prefix='csc_')
        os.close(handle)
        with open(path, 'wb') as stream:
            stream.write(data)
        doc = Rhino.RhinoDoc.CreateHeadless(None)
        try:
            if not doc.Import(path):
                return None
            objects = list(doc.Objects)
            if len(objects) != 1:
                return None
            return objects[0].Geometry.Duplicate()
        finally:
            doc.Dispose()
    except Exception:
        return None
    finally:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def build_mesh(vertices, faces, colors=None, mode=None):
    """A Rhino mesh from numpy arrays (vertices (n, 3), triangles (m, 3),
    optional uchar colors (n, 3)), normals computed and compacted. ``import``
    needs the bytes of a file (``mesh_from_ply``): here it builds like
    ``blit``."""
    mode = mode or MESH_BUILD_MODE
    builder = MESH_BUILDERS.get(mode, _build_blit)
    mesh = builder(vertices, faces, colors)
    mesh.Normals.ComputeNormals()
    mesh.Compact()
    return usable(mesh)


def mesh_from_ply(data, mode=None):
    """A Rhino mesh from the bytes of a binary PLY; None if it has no
    faces. In ``import`` mode Rhino reads the file itself; if that fails the
    numpy parse and the ``blit`` build take over."""
    mode = mode or MESH_BUILD_MODE
    if mode == 'import':
        mesh = import_geometry(data)
        if isinstance(mesh, Rhino.Geometry.Mesh) and mesh.Faces.Count:
            return usable(mesh)
    parsed = parse_ply(data)
    if len(parsed['faces']) == 0:
        return None
    return build_mesh(parsed['vertices'], parsed['faces'], parsed['colors'],
                      mode if mode in MESH_BUILDERS else 'blit')


def _cloud_from_arrays(points, colors):
    cloud = Rhino.Geometry.PointCloud()
    count = len(points)
    if blit_works():
        net_points = System.Array.CreateInstance(Rhino.Geometry.Point3d,
                                                 count)
        _pinned_write(net_points, np.ascontiguousarray(points,
                                                       dtype=np.float64))
    else:
        net_points = System.Array[Rhino.Geometry.Point3d](
            [Rhino.Geometry.Point3d(x, y, z) for x, y, z in
             np.asarray(points, dtype=np.float64).tolist()])
    if colors is not None and len(colors) == count:
        net_colors = System.Array[System.Drawing.Color](
            [System.Drawing.Color.FromArgb(r, g, b) for r, g, b in
             np.asarray(colors, dtype=np.int64).tolist()])
        cloud.AddRange(net_points, net_colors)
    else:
        cloud.AddRange(net_points)
    return cloud


def point_cloud_from_ply(data, mode=None):
    """A Rhino point cloud from the bytes of a PLY; None when empty."""
    mode = mode or MESH_BUILD_MODE
    if mode == 'import':
        cloud = import_geometry(data)
        if isinstance(cloud, Rhino.Geometry.PointCloud) and cloud.Count:
            return usable(cloud)
    parsed = parse_ply(data)
    if len(parsed['vertices']) == 0:
        return None
    cloud = _cloud_from_arrays(parsed['vertices'], parsed['colors'])
    return usable(cloud) if cloud.Count > 0 else None


def inline_mesh_to_rhino(entry, default_color=None, mode=None):
    """A Rhino mesh from an inline ``{vertices, faces[, colors]}`` entry."""
    vertices = np.asarray(entry.get('vertices') or [], dtype=np.float64)
    faces = np.asarray(entry.get('faces') or [], dtype=np.int64)
    if len(vertices) == 0 or len(faces) == 0:
        return None
    triangles = []
    for face in faces.tolist() if faces.ndim == 1 else faces:
        face = list(face)
        for k in range(1, len(face) - 1):
            triangles.append((face[0], face[k], face[k + 1]))
    colors = entry.get('colors')
    if colors and len(colors) == len(vertices):
        colors = np.asarray(colors, dtype=np.int64)
    elif default_color:
        colors = np.tile(np.asarray(default_color[:3], dtype=np.int64),
                         (len(vertices), 1))
    else:
        colors = None
    return build_mesh(vertices, np.asarray(triangles, dtype=np.int64),
                      colors, mode)


def inline_cloud_to_rhino(entry):
    """A Rhino point cloud from an inline ``{points[, colors]}`` entry."""
    points = entry.get('points') or []
    if not points:
        return None
    cloud = Rhino.Geometry.PointCloud()
    colors = entry.get('colors')
    if colors and len(colors) == len(points):
        for p, c in zip(points, colors):
            cloud.Add(Rhino.Geometry.Point3d(float(p[0]), float(p[1]),
                                             float(p[2])),
                      System.Drawing.Color.FromArgb(int(c[0]), int(c[1]),
                                                    int(c[2])))
    else:
        for p in points:
            cloud.Add(Rhino.Geometry.Point3d(float(p[0]), float(p[1]),
                                             float(p[2])))
    return usable(cloud) if cloud.Count > 0 else None


# MESH OUT --------------------------------------------------------------------
def mesh_arrays(mesh):
    """``(vertices (n, 3) float32, triangles (m, 3) int32, colors or None)``
    of a Rhino mesh, quads split (``ToFloatArray`` / ``ToIntArray(True)`` /
    ``ToARGBArray``: one call each)."""
    flat = to_numpy(mesh.Vertices.ToFloatArray(), np.float32)
    vertices = flat.reshape(-1, 3)
    triangles = to_numpy(mesh.Faces.ToIntArray(True), np.int32).reshape(-1, 3)
    colors = None
    if mesh.VertexColors.Count == mesh.Vertices.Count > 0:
        argb = to_numpy(mesh.VertexColors.ToARGBArray(),
                        np.int32).view(np.uint32)
        colors = np.column_stack([(argb >> 16) & 255, (argb >> 8) & 255,
                                  argb & 255]).astype(np.uint8)
    return vertices, triangles, colors


def reduce_mesh(mesh, target_faces):
    """A copy of the mesh reduced to about ``target_faces`` faces."""
    reduced = mesh.DuplicateMesh()
    reduced.Reduce(int(target_faces), True, 5, False, True)
    reduced.Faces.ConvertQuadsToTriangles()
    reduced.Compact()
    return reduced


def export_mesh(mesh, directory, index, default_rgb):
    """Reduce, stage and describe one mesh (8.95 1).

    Writes ``<directory>/meshes/<index>/detailed.ply`` (the Original) and,
    for a big mesh, ``reduced.ply``; returns the inline Preview entry and the
    list of staged levels. Files always carry colours (the piece's colour
    when the mesh has none); the inline entry only the mesh's own.
    """
    vertices, triangles, own_colors = mesh_arrays(mesh)
    file_colors = own_colors if own_colors is not None         else np.asarray(default_rgb[:3], dtype=np.uint8)
    plan = mesh_levels(len(triangles))
    levels = []
    folder = os.path.join(directory, 'meshes', str(index))
    if plan['save_original'] or plan['reduced_target']:
        os.makedirs(folder, exist_ok=True)
    if plan['save_original']:
        with open(os.path.join(folder, 'detailed.ply'), 'wb') as handle:
            handle.write(write_ply_mesh(vertices, triangles, file_colors))
        levels.append('detailed')
    if plan['reduced_target']:
        rv, rt, rc = mesh_arrays(reduce_mesh(mesh, plan['reduced_target']))
        with open(os.path.join(folder, 'reduced.ply'), 'wb') as handle:
            handle.write(write_ply_mesh(
                rv, rt, rc if rc is not None else file_colors))
        levels.append('reduced')
    if plan['preview_target']:
        pv, pt, pc = mesh_arrays(reduce_mesh(mesh, plan['preview_target']))
    else:
        pv, pt, pc = vertices, triangles, own_colors
    return inline_mesh(pv, pt, pc), levels


def point_cloud_arrays(cloud):
    """``(points (n, 3) float64, colors (n, 3) uint8 or None)``; the points
    are copied in one block (the colours, a .NET Color each, one by one)."""
    net_points = cloud.GetPoints()
    if blit_works():
        points = _pinned_read(net_points, np.float64, 3)
    else:
        points = np.array([[p.X, p.Y, p.Z] for p in net_points],
                          dtype=np.float64).reshape(-1, 3)
    colors = None
    if cloud.ContainsColors:
        colors = np.array([[c.R, c.G, c.B] for c in cloud.GetColors()],
                          dtype=np.uint8).reshape(-1, 3)
    return points, colors


def export_point_cloud(cloud, directory, index):
    """Stage the full cloud as a file when it is bigger than the inline
    Preview; returns the inline entry and whether a file was written."""
    points, colors = point_cloud_arrays(cloud)
    staged = False
    if len(points) > POINT_CLOUD_STAGING_THRESHOLD:
        folder = os.path.join(directory, 'point_clouds')
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, '%d.ply' % index), 'wb') as handle:
            handle.write(write_ply_cloud(points, colors))
        staged = True
    return inline_point_cloud(points, colors), staged


# AUTHORED GEOMETRY (8.95 8, 9) -----------------------------------------------
def _polyline_points(curve):
    """Corner points of a closed profile curve as ``[(x, y, z), ...]``."""
    ok, polyline = curve.TryGetPolyline()
    if not ok:
        poly_curve = curve.ToPolyline(0.01, 0.01, 0, 0)
        if poly_curve is None:
            raise ValueError('the profile curve cannot be turned into a '
                             'polyline')
        ok, polyline = poly_curve.TryGetPolyline()
        if not ok:
            raise ValueError('the profile curve is not a polyline')
    return [(p.X, p.Y, p.Z) for p in polyline]


def prism_from_extrusion(extrusion):
    """An authored prism proxy dict from a Rhino extrusion (outer profile
    first, further profiles are holes)."""
    start, end = extrusion.PathStart, extrusion.PathEnd
    axis = end - start
    height = start.DistanceTo(end)
    outer = _polyline_points(extrusion.Profile3d(0, 0.0))
    holes = [_polyline_points(extrusion.Profile3d(i, 0.0))
             for i in range(1, extrusion.ProfileCount)]
    return prism_proxy(outer, (axis.X, axis.Y, axis.Z), height, holes)


def box_from_brep(brep, tolerance=None):
    """An authored box proxy dict from a box-shaped brep, or None when the
    brep is not a box."""
    tol = Rhino.RhinoMath.SqrtEpsilon if tolerance is None else tolerance
    if not brep.IsBox(tol):
        return None
    ok, plane = brep.Faces[0].TryGetPlane()
    if not ok:
        return None
    edge = brep.Edges[brep.Faces[0].OuterLoop.Trims[0].Edge.EdgeIndex]
    along = edge.PointAtEnd - edge.PointAtStart
    corners = [(v.Location.X, v.Location.Y, v.Location.Z)
               for v in brep.Vertices]
    return box_proxy(corners, (along.X, along.Y, along.Z),
                     (plane.ZAxis.X, plane.ZAxis.Y, plane.ZAxis.Z))


def curve_points(curve, tolerance=None):
    """The points of a curve as ``[(x, y, z), ...]``: the vertices of a
    polyline, else a polyline approximation within ``tolerance`` (default:
    the document's absolute tolerance, else 0.01)."""
    ok, polyline = curve.TryGetPolyline()
    if not ok:
        if tolerance is None:
            doc = Rhino.RhinoDoc.ActiveDoc
            tolerance = doc.ModelAbsoluteTolerance if doc is not None                 else 0.01
        approx = curve.ToPolyline(tolerance, tolerance, 0, 0)
        if approx is None:
            raise ValueError('a curve could not be turned into a polyline')
        ok, polyline = approx.TryGetPolyline()
        if not ok:
            raise ValueError('a curve could not be turned into a polyline')
    return [(p.X, p.Y, p.Z) for p in polyline]


def split_geometry(geometries):
    """Sort the input geometry: ``(meshes, clouds, proxies)`` with Rhino
    meshes, Rhino point clouds and authored proxy dicts (an extrusion becomes
    a prism, a box-shaped brep a box). Raises ValueError for anything else.
    """
    meshes, clouds, proxies = [], [], []
    for geometry in geometries:
        if geometry is None:
            continue
        if isinstance(geometry, Rhino.Geometry.Mesh):
            meshes.append(geometry)
        elif isinstance(geometry, Rhino.Geometry.PointCloud):
            clouds.append(geometry)
        elif isinstance(geometry, Rhino.Geometry.Extrusion):
            proxies.append(prism_from_extrusion(geometry))
        elif isinstance(geometry, Rhino.Geometry.Brep):
            box = box_from_brep(geometry)
            if box is None:
                raise ValueError('a brep is only accepted when it is a box; '
                                 'mesh it first')
            proxies.append(box)
        else:
            raise ValueError('geometry of type %s is not supported (mesh, '
                             'point cloud, extrusion or box-shaped brep)'
                             % type(geometry).__name__)
    return meshes, clouds, proxies


def geometry_points(geometries):
    """All points of the input geometry as an (n, 3) array: mesh vertices,
    cloud points, brep / extrusion vertices (other geometry: the corners of
    its bounding box)."""
    chunks = []
    for geometry in geometries:
        if geometry is None:
            continue
        if isinstance(geometry, Rhino.Geometry.Mesh):
            chunks.append(to_numpy(geometry.Vertices.ToFloatArray(),
                                   np.float32).reshape(-1, 3)
                          .astype(np.float64))
        elif isinstance(geometry, Rhino.Geometry.PointCloud):
            chunks.append(point_cloud_arrays(geometry)[0])
        else:
            brep = geometry if isinstance(geometry, Rhino.Geometry.Brep)                 else (geometry.ToBrep() if hasattr(geometry, 'ToBrep')
                      else None)
            if brep is not None and brep.Vertices.Count:
                chunks.append(np.array(
                    [[v.Location.X, v.Location.Y, v.Location.Z]
                     for v in brep.Vertices], dtype=np.float64))
            else:
                box = geometry.GetBoundingBox(True)
                chunks.append(np.array([[c.X, c.Y, c.Z]
                                        for c in box.GetCorners()]))
    return np.vstack(chunks) if chunks else np.zeros((0, 3))


def centre_vector(geometries):
    """The translation that moves the centroid of the mesh vertices and
    cloud points (else the bounding box centre) to the origin."""
    total, count = np.zeros(3), 0
    for geometry in geometries:
        if geometry is None:
            continue
        if isinstance(geometry, Rhino.Geometry.Mesh):
            vertices = to_numpy(geometry.Vertices.ToFloatArray(),
                                np.float32).reshape(-1, 3)
            total += vertices.astype(np.float64).sum(axis=0)
            count += len(vertices)
        elif isinstance(geometry, Rhino.Geometry.PointCloud):
            points, _ = point_cloud_arrays(geometry)
            total += points.sum(axis=0)
            count += len(points)
    if count:
        return tuple(float(v) for v in -total / count)
    box = Rhino.Geometry.BoundingBox.Empty
    for geometry in geometries:
        if geometry is not None:
            box.Union(geometry.GetBoundingBox(True))
    if not box.IsValid:
        return (0.0, 0.0, 0.0)
    centre = box.Center
    return (-centre.X, -centre.Y, -centre.Z)


def proxy_to_rhino(proxy):
    """Rhino geometry for a drawable proxy, in stored coordinates: a brep
    for a box or cylinder, an extrusion for a prism, a mesh for a hull.
    None when the proxy cannot be drawn."""
    if not drawable_proxy(proxy):
        return None
    params = proxy['params']
    kind = proxy['primitive']
    plane = Rhino.Geometry.Plane.WorldXY
    if kind == 'box':
        sx, sy, sz = [float(v) for v in params['size']]
        geometry = Rhino.Geometry.Box(
            plane, Rhino.Geometry.Interval(-sx / 2, sx / 2),
            Rhino.Geometry.Interval(-sy / 2, sy / 2),
            Rhino.Geometry.Interval(-sz / 2, sz / 2)).ToBrep()
    elif kind == 'cylinder':
        height = float(params['height'])
        base = Rhino.Geometry.Plane(
            Rhino.Geometry.Point3d(0, 0, -height / 2),
            Rhino.Geometry.Vector3d.XAxis, Rhino.Geometry.Vector3d.YAxis)
        circle = Rhino.Geometry.Circle(base, float(params['radius']))
        geometry = Rhino.Geometry.Cylinder(circle, height).ToBrep(True, True)
    elif kind == 'prism':
        height = float(params['height'])

        def closed(ring, z=-height / 2):
            pts = [Rhino.Geometry.Point3d(float(p[0]), float(p[1]), z)
                   for p in ring]
            if pts[0].DistanceTo(pts[-1]) > Rhino.RhinoMath.SqrtEpsilon:
                pts.append(pts[0])
            polyline = Rhino.Geometry.Polyline()
            for pt in pts:
                polyline.Add(pt)
            return polyline.ToPolylineCurve()

        outer = closed(params['profile'])
        geometry = Rhino.Geometry.Extrusion.Create(outer, height, True)
        if geometry is None:
            return None
        # Extrusion.Create extrudes along the profile's normal; a clockwise
        # profile points it down, so make the sweep run from -h/2 to +h/2
        if geometry.PathEnd.Z < geometry.PathStart.Z:
            outer.Reverse()
            geometry = Rhino.Geometry.Extrusion.Create(outer, height, True)
        for hole in params.get('holes') or []:
            # inner profiles are given in the profile's own plane (z = 0)
            curve = closed(hole, 0.0)
            if curve.IsClosed:
                geometry.AddInnerProfile(curve)
    else:  # hull
        vertices = np.asarray(params['vertices'], dtype=np.float64)
        faces = np.asarray(params['faces'], dtype=np.int64)
        geometry = build_mesh(vertices, faces)
        if geometry is None:
            return None
    geometry.Transform(placement_transform(proxy['placement']))
    return usable(geometry)


# STAGING THE GEOMETRY OF A CREATE (8.95 1, 2, 8) -----------------------------
def stage_geometry(geometries, directory, default_rgb=(110, 110, 110),
                   centre=False):
    """Everything CreateComponent* needs of the input geometry.

    Works on copies. ``centre`` moves the centroid to the origin first
    (default off: stored coordinates as uploaded). Meshes are reduced and
    staged (Preview inline, Reduced and Original as files under
    ``directory``), clouds thinned and staged, an extrusion becomes a prism
    and a box-shaped brep a box.

    Returns ``(geometry block, manifest dict, translation (x, y, z))``.
    """
    copies = []
    for geometry in geometries:
        if geometry is None:
            continue
        if not isinstance(geometry, Rhino.Geometry.GeometryBase):
            raise ValueError('geometry of type %s is not supported (mesh, '
                             'point cloud, extrusion or box-shaped brep)'
                             % type(geometry).__name__)
        copies.append(geometry.Duplicate())
    move = (0.0, 0.0, 0.0)
    if centre and copies:
        move = centre_vector(copies)
        xform = Rhino.Geometry.Transform.Translation(*move)
        for geometry in copies:
            geometry.Transform(xform)
    meshes, clouds, proxies = split_geometry(copies)
    mesh_entries, staged_levels = [], {}
    for index, mesh in enumerate(meshes):
        entry, levels = export_mesh(mesh, directory, index, default_rgb)
        mesh_entries.append(entry)
        if levels:
            staged_levels[index] = levels
    cloud_entries, staged_clouds = [], []
    for index, cloud in enumerate(clouds):
        entry, staged = export_point_cloud(cloud, directory, index)
        cloud_entries.append(entry)
        if staged:
            staged_clouds.append(index)
    geometry = geometry_body(mesh_entries, cloud_entries, proxies)
    return geometry, manifest(staged_levels, staged_clouds), move
