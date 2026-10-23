"""The Rhino-bound helpers (csc_rhino) in a headless Rhino 8.

Runs only with ``CSC_TEST_RHINO=1`` and ``rhinoinside`` importable, in the
Python 3.9 stack of Rhino 8 (numpy 2.0.2, scipy 1.13.1, trimesh 4.12.2). No
test installs anything into a user environment: use a scratch venv.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

pytestmark = pytest.mark.slow    # headless Rhino: run by `invoke test-release`

if os.environ.get('CSC_TEST_RHINO') != '1':
    pytest.skip('set CSC_TEST_RHINO=1 to run the headless Rhino tests',
                allow_module_level=True)
pytest.importorskip('rhinoinside')
import rhino_runtime  # noqa: E402

rhino_runtime.load()
import Rhino  # noqa: E402
import System  # noqa: E402,F401

from libns import namespace  # noqa: E402

NS = namespace()
G = Rhino.Geometry


def _curve(points):
    polyline = G.Polyline()
    for point in points:
        polyline.Add(point)
    return polyline.ToPolylineCurve()


def _sphere(subdivisions):
    return G.Mesh.CreateIcoSphere(G.Sphere(G.Point3d(10, 20, 30), 50),
                                  subdivisions)


MODES = ('loop', 'bulk', 'blit', 'import')


def _coloured_ply(subdivisions=3):
    v, f, _ = NS['mesh_arrays'](_sphere(subdivisions))
    colours = (np.arange(len(v) * 3).reshape(-1, 3) * 7) % 256
    return NS['write_ply_mesh'](v, f, colours), v, f, colours.astype(np.uint8)


@pytest.mark.parametrize('mode', MODES)
def test_every_build_mode_makes_the_same_mesh(mode):
    data, v, f, colours = _coloured_ply()
    mesh = NS['mesh_from_ply'](data, mode)
    got_v, got_f, got_c = NS['mesh_arrays'](mesh)
    assert got_v.shape == v.shape and got_f.shape == f.shape
    assert np.allclose(got_v, v, atol=1e-4)
    assert (got_f == f).all()
    assert (got_c == colours).all()
    assert mesh.Normals.Count == mesh.Vertices.Count


@pytest.mark.parametrize('mode', MODES)
def test_every_build_mode_builds_from_arrays_too(mode):
    v, f, _ = NS['mesh_arrays'](_sphere(2))
    mesh = NS['build_mesh'](v, f, None, mode)
    assert mesh.Faces.Count == len(f) and mesh.VertexColors.Count == 0
    assert (NS['mesh_arrays'](mesh)[1] == f).all()


def test_import_is_the_default_and_blit_is_checked():
    assert NS['MESH_BUILD_MODE'] == 'import'
    assert NS['blit_works']() is True


def test_the_importer_makes_one_mesh_or_one_cloud():
    data, v, f, colours = _coloured_ply()
    mesh = NS['import_geometry'](data)
    assert isinstance(mesh, G.Mesh) and mesh.Faces.Count == len(f)
    cloud_data = NS['write_ply_cloud'](v[:30], [4, 5, 6])
    cloud = NS['import_geometry'](cloud_data)
    assert isinstance(cloud, G.PointCloud) and cloud.Count == 30
    assert NS['import_geometry'](b'not a ply') is None


def test_a_failed_import_falls_back_to_the_blit():
    data, v, f, colours = _coloured_ply()
    saved = NS['import_geometry']
    NS['import_geometry'] = lambda *a, **k: None
    try:
        mesh = NS['mesh_from_ply'](data)           # the default is import
        cloud = NS['point_cloud_from_ply'](
            NS['write_ply_cloud'](v[:40], [1, 2, 3]))
    finally:
        NS['import_geometry'] = saved
    assert mesh.Faces.Count == len(f) and mesh.VertexColors.Count == len(v)
    assert cloud.Count == 40 and cloud.ContainsColors


@pytest.mark.parametrize('mode', ['import', 'blit', 'loop'])
def test_every_cloud_mode_keeps_points_and_colours(mode):
    rng = np.random.default_rng(3)
    points = rng.random((200, 3)) * 100
    colours = rng.integers(0, 256, (200, 3)).astype(np.uint8)
    cloud = NS['point_cloud_from_ply'](
        NS['write_ply_cloud'](points, colours), mode)
    got, got_c = NS['point_cloud_arrays'](cloud)
    assert np.allclose(got, points.astype(np.float32), atol=1e-3)
    assert (got_c == colours).all()
    bare = NS['point_cloud_from_ply'](NS['write_ply_cloud'](points), mode)
    assert NS['point_cloud_arrays'](bare)[1] is None


def test_a_mesh_survives_write_and_parse():
    mesh = _sphere(2)
    v, f, c = NS['mesh_arrays'](mesh)
    assert c is None
    back = NS['parse_ply'](NS['write_ply_mesh'](v, f))
    assert np.allclose(back['vertices'], v, atol=1e-4)
    assert (back['faces'] == f).all()
    again = NS['mesh_from_ply'](NS['write_ply_mesh'](v, f))
    assert again.Faces.Count == mesh.Faces.Count


def test_export_levels_of_a_big_mesh(tmp_path):
    mesh = _sphere(5)                      # 20480 faces
    assert mesh.Faces.Count > NS['MESH_REDUCED_THRESHOLD']
    entry, levels = NS['export_mesh'](mesh, str(tmp_path), 0, [110, 110, 110])
    assert levels == ['detailed', 'reduced']
    original = (tmp_path / 'meshes' / '0' / 'detailed.ply').read_bytes()
    reduced = (tmp_path / 'meshes' / '0' / 'reduced.ply').read_bytes()
    assert len(NS['parse_ply'](original)['faces']) == mesh.Faces.Count
    reduced_faces = len(NS['parse_ply'](reduced)['faces'])
    assert 0.5 * NS['MESH_REDUCED_TARGET'] < reduced_faces \
        < 1.5 * NS['MESH_REDUCED_TARGET']
    assert len(entry['faces']) < 0.5 * NS['MESH_REDUCED_TARGET']
    assert 'colors' not in entry           # the mesh had none


def test_a_small_mesh_is_its_own_preview(tmp_path):
    mesh = _sphere(2)                      # 320 faces
    entry, levels = NS['export_mesh'](mesh, str(tmp_path), 1, [1, 2, 3])
    assert levels == [] and len(entry['faces']) == mesh.Faces.Count
    assert not (tmp_path / 'meshes').exists()


def test_a_mesh_above_the_inline_budget_is_reduced_for_the_preview(tmp_path):
    mesh = _sphere(3)                      # 1280 faces: above the 1000 of the inline budget
    assert NS['MESH_PRIMITIVE_TARGET'] < mesh.Faces.Count <= NS['MESH_REDUCED_THRESHOLD']
    entry, levels = NS['export_mesh'](mesh, str(tmp_path), 0, [1, 2, 3])
    assert levels == ['detailed']
    assert len(entry['faces']) <= NS['MESH_PRIMITIVE_TARGET'] * 1.1
    original = (tmp_path / 'meshes' / '0' / 'detailed.ply').read_bytes()
    assert len(NS['parse_ply'](original)['faces']) == mesh.Faces.Count


def test_a_cloud_up_to_the_budget_is_inline_only(tmp_path):
    cloud = G.PointCloud()
    for p in np.random.default_rng(2).random((NS['POINT_CLOUD_INLINE_MAX'], 3)) * 100:
        cloud.Add(G.Point3d(float(p[0]), float(p[1]), float(p[2])))
    entry, staged = NS['export_point_cloud'](cloud, str(tmp_path), 0)
    assert not staged and len(entry['points']) == NS['POINT_CLOUD_INLINE_MAX']
    assert not (tmp_path / 'point_clouds').exists()


def test_a_big_cloud_is_staged_and_thinned(tmp_path):
    cloud = G.PointCloud()
    rng = np.random.default_rng(1)
    for p in rng.random((6000, 3)) * 100:
        cloud.Add(G.Point3d(float(p[0]), float(p[1]), float(p[2])))
    entry, staged = NS['export_point_cloud'](cloud, str(tmp_path), 0)
    assert staged and len(entry['points']) == NS['POINT_CLOUD_INLINE_MAX']
    data = (tmp_path / 'point_clouds' / '0.ply').read_bytes()
    assert len(NS['parse_ply'](data)['vertices']) == 6000
    assert NS['point_cloud_from_ply'](data).Count == 6000


@pytest.mark.parametrize('clockwise', [False, True])
def test_an_extrusion_becomes_a_prism_and_back(clockwise):
    ring = [(0, 0), (40, 0), (40, 20), (0, 20)]
    if clockwise:
        ring.reverse()
    pts = [G.Point3d(x + 5, y - 3, 7) for x, y in ring]
    pts.append(pts[0])
    profile = _curve(pts)
    extrusion = G.Extrusion.Create(profile, 10.0, True)
    assert extrusion is not None
    proxy = NS['prism_from_extrusion'](extrusion)
    assert proxy['primitive'] == 'prism'
    assert proxy['fit']['method'] == 'authored'
    assert proxy['params']['height'] == pytest.approx(10.0)
    sizes = np.ptp(np.array(proxy['params']['profile']), axis=0)
    assert sorted(sizes) == pytest.approx([20.0, 40.0])
    assert NS['drawable_proxy'](proxy)
    rebuilt = NS['proxy_to_rhino'](proxy)
    a = extrusion.GetBoundingBox(True)
    b = rebuilt.GetBoundingBox(True)
    assert b.Min.DistanceTo(a.Min) < 1e-6 and b.Max.DistanceTo(a.Max) < 1e-6


def test_an_extrusion_with_a_hole_keeps_it():
    def ring(x0, y0, x1, y1, z):
        pts = [G.Point3d(x0, y0, z), G.Point3d(x1, y0, z),
               G.Point3d(x1, y1, z), G.Point3d(x0, y1, z),
               G.Point3d(x0, y0, z)]
        return _curve(pts)
    extrusion = G.Extrusion.Create(ring(0, 0, 100, 60, 0), 12.0, True)
    extrusion.AddInnerProfile(ring(30, 20, 60, 40, 0))
    proxy = NS['prism_from_extrusion'](extrusion)
    assert len(proxy['params']['holes']) == 1
    rebuilt = NS['proxy_to_rhino'](proxy)
    assert rebuilt.ProfileCount == 2


def test_a_box_brep_becomes_a_box_and_back():
    plane = G.Plane(G.Point3d(100, -50, 20), G.Vector3d(1, 1, 0),
                    G.Vector3d(-1, 1, 0))
    box = G.Box(plane, G.Interval(-30, 30), G.Interval(-10, 10),
                G.Interval(-5, 5))
    brep = box.ToBrep()
    proxy = NS['box_from_brep'](brep)
    assert proxy['primitive'] == 'box'
    assert sorted(proxy['params']['size']) == pytest.approx([10, 20, 60])
    assert np.allclose(proxy['placement']['o'], [100, -50, 20], atol=1e-6)
    rebuilt = NS['proxy_to_rhino'](proxy)
    assert rebuilt.GetBoundingBox(True).Diagonal.Length == pytest.approx(
        brep.GetBoundingBox(True).Diagonal.Length, rel=1e-6)
    assert rebuilt.GetVolume() == pytest.approx(brep.GetVolume(), rel=1e-6)


def test_other_geometry_is_refused():
    sphere_brep = G.Sphere(G.Point3d.Origin, 5).ToBrep()
    with pytest.raises(ValueError):
        NS['split_geometry']([sphere_brep])
    with pytest.raises(ValueError):
        NS['split_geometry']([G.Point3d(0, 0, 0)])
    unit_box = G.Box(G.Plane.WorldXY, G.Interval(0, 1), G.Interval(0, 2),
                     G.Interval(0, 3)).ToBrep()
    meshes, clouds, proxies = NS['split_geometry']([_sphere(1), None,
                                                    unit_box])
    assert len(meshes) == 1 and not clouds and len(proxies) == 1


def test_centre_vector_moves_the_centroid_to_the_origin():
    move = NS['centre_vector']([_sphere(2)])
    assert np.allclose(move, [-10, -20, -30], atol=1e-3)


def test_cylinder_and_hull_proxies_draw():
    placement = {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0],
                 'z': [0, 0, 1]}
    cylinder = {'primitive': 'cylinder', 'role': 'primary',
                'params': {'radius': 10.0, 'height': 40.0},
                'placement': placement, 'fit': {'method': 'authored'}}
    brep = NS['proxy_to_rhino'](cylinder)
    assert brep.GetVolume() == pytest.approx(np.pi * 100 * 40, rel=1e-6)
    hull = {'primitive': 'hull', 'role': 'primary',
            'params': {'vertices': [[0, 0, 0], [1, 0, 0], [0, 1, 0],
                                    [0, 0, 1]],
                       'faces': [[0, 2, 1], [0, 1, 3], [1, 2, 3], [0, 3, 2]]},
            'placement': placement, 'fit': {'method': 'authored'}}
    assert NS['proxy_to_rhino'](hull).Faces.Count == 4


def test_canonical_transform_agrees_with_the_matrix_form():
    frame = {'o': [10, 20, 30], 'x': [0, 1, 0], 'y': [-1, 0, 0],
             'z': [0, 0, 1]}
    xform = NS['canonical_transform'](frame)
    points = np.array([[10, 20, 30], [11, 22, 33], [-5, 7, 9.5]])
    expected = NS['apply_matrix'](points, NS['canonical_matrix'](frame))
    for p, e in zip(points, expected):
        q = G.Point3d(*[float(v) for v in p])
        q.Transform(xform)
        assert np.allclose([q.X, q.Y, q.Z], e, atol=1e-9)
    assert np.allclose(expected[0], 0, atol=1e-9)


def test_plane_frame_round_trip_and_matrix_transform():
    frame = {'o': [1, 2, 3], 'x': [0, 0, 1], 'y': [1, 0, 0], 'z': [0, 1, 0]}
    back = NS['frame_from_plane'](NS['plane_from_frame'](frame))
    for key in 'oxyz':
        assert np.allclose(back[key], frame[key], atol=1e-12)
    matrix = NS['placement_matrix'](frame)
    p = G.Point3d(1.0, 2.0, 3.0)
    p.Transform(NS['transform_from_matrix'](matrix))
    assert np.allclose([p.X, p.Y, p.Z],
                       matrix[:3, :3] @ [1, 2, 3] + matrix[:3, 3])


def test_inline_entries_become_rhino_geometry():
    entry = {'vertices': [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]],
             'faces': [[0, 1, 2], [1, 3, 2]],
             'colors': [[1, 2, 3]] * 4}
    mesh = NS['inline_mesh_to_rhino'](entry)
    assert mesh.Faces.Count == 2 and mesh.VertexColors.Count == 4
    plain = NS['inline_mesh_to_rhino'](
        {k: v for k, v in entry.items() if k != 'colors'}, [9, 9, 9])
    assert plain.VertexColors[0].R == 9
    cloud = NS['inline_cloud_to_rhino'](
        {'points': [[0, 0, 0], [1, 1, 1]],
         'colors': [[5, 6, 7], [8, 9, 10]]})
    assert cloud.Count == 2 and cloud.ContainsColors


def test_the_build_mode_can_be_set_from_the_environment(monkeypatch):
    rhino = ('csc_rhino',)
    monkeypatch.setenv('CSC_MESH_BUILD_MODE', 'blit')
    assert namespace(rhino, fresh=True)['MESH_BUILD_MODE'] == 'blit'
    monkeypatch.setenv('CSC_MESH_BUILD_MODE', 'nonsense')
    assert namespace(rhino, fresh=True)['MESH_BUILD_MODE'] == 'import'
    monkeypatch.delenv('CSC_MESH_BUILD_MODE')
    assert namespace(rhino, fresh=True)['MESH_BUILD_MODE'] == 'import'


# THE BLIT WRITES float64 INTO Point3d (part C) ----------------------------------
def test_the_blit_assumes_the_byte_sizes_it_writes():
    """Point3d is 3 doubles = 24 bytes, so the numpy block must be float64;
    a float32 block (12 bytes a point) corrupts every vertex."""
    marshal = System.Runtime.InteropServices.Marshal
    assert marshal.SizeOf(Rhino.Geometry.Point3d) == 24
    assert marshal.SizeOf(Rhino.Geometry.MeshFace) == 16
    assert np.dtype(np.float64).itemsize * 3 == 24
    assert NS['blit_works']() is True


def test_a_blit_mesh_has_the_vertices_it_was_given():
    vertices = np.array([[0, 0, 0], [10.5, 0, 0], [0, 20.25, 0],
                         [1234567.125, -3.5, 7.75]], dtype=np.float64)
    faces = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
    mesh = NS['build_mesh'](vertices, faces, None, 'blit')
    got = np.array([[v.X, v.Y, v.Z] for v in mesh.Vertices])
    assert np.allclose(got, vertices, atol=1e-3)     # (stored as float32)
    assert mesh.Faces.Count == 2
    # the same through the Point3d array path (bulk)
    bulk = NS['build_mesh'](vertices, faces, None, 'bulk')
    assert np.allclose(np.array([[v.X, v.Y, v.Z] for v in bulk.Vertices]),
                       vertices, atol=1e-3)


# THE VALIDITY GUARD (part C) ----------------------------------------------------
def _triangle(scale=1.0, z=0.0):
    return {'vertices': [[0, 0, z], [scale, 0, z], [0, scale, z]],
            'faces': [[0, 1, 2]]}


def test_a_sane_mesh_passes_the_guard():
    mesh = NS['inline_mesh_to_rhino'](_triangle(100.0))
    assert mesh is not None and NS['reject_reason'](mesh) is None


@pytest.mark.parametrize('entry', [
    _triangle(1.0e12),                                     # wider than 10 km
    {'vertices': [[0, 0, 0], [float('nan'), 0, 0], [0, 1, 0]],
     'faces': [[0, 1, 2]]},                                # not finite
    {'vertices': [[0, 0, 0], [float('inf'), 0, 0], [0, 1, 0]],
     'faces': [[0, 1, 2]]},
])
def test_a_wild_mesh_is_dropped(entry):
    assert NS['inline_mesh_to_rhino'](entry) is None


def test_a_wild_cloud_is_dropped():
    assert NS['inline_cloud_to_rhino'](
        {'points': [[0, 0, 0], [5.0e9, 0, 0]]}) is None
    assert NS['inline_cloud_to_rhino'](
        {'points': [[0, 0, 0], [1, 1, 1]]}) is not None


def test_a_huge_proxy_is_dropped():
    box = {'primitive': 'box', 'params': {'size': [5.0e7, 10, 10]},
           'placement': {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0],
                         'z': [0, 0, 1]},
           'fit': {'method': 'authored'}}
    assert NS['proxy_to_rhino'](box) is None
    box['params']['size'] = [400, 200, 12]
    assert NS['proxy_to_rhino'](box) is not None


# REINFORCEMENT LAYOUTS (RL9, RL11) ------------------------------------------------
def _random_plane(seed):
    rng = np.random.default_rng(seed)
    q, r = np.linalg.qr(rng.normal(size=(3, 3)))
    q = q * np.sign(np.diag(r))
    if np.linalg.det(q) < 0:
        q[:, 2] = -q[:, 2]
    return {'o': rng.uniform(-4000, 4000, 3).tolist(), 'x': q[:, 0].tolist(),
            'y': q[:, 1].tolist(), 'z': q[:, 2].tolist()}


@pytest.mark.parametrize('seed', range(5))
def test_the_numpy_placement_is_the_rhino_placement_transform(seed):
    """stored -> placed in numpy (the library) is ``placement_transform`` on a
    Rhino point; and the inverse maps it back."""
    plane = _random_plane(seed)
    xform = NS['placement_transform'](plane)
    stored = np.random.default_rng(seed + 100).uniform(-900, 900, (10, 3))
    placed = NS['points_to_document'](stored, plane)
    for point, want in zip(stored, placed):
        moved = G.Point3d(*[float(v) for v in point])
        moved.Transform(xform)
        assert np.allclose([moved.X, moved.Y, moved.Z], want, atol=1e-6)
    assert np.allclose(NS['points_to_stored'](placed, plane), stored,
                       atol=1e-6)


def test_the_document_unit_is_millimetres_per_unit():
    for system, factor in ((Rhino.UnitSystem.Millimeters, 1.0),
                           (Rhino.UnitSystem.Meters, 1000.0),
                           (Rhino.UnitSystem.Centimeters, 10.0),
                           (Rhino.UnitSystem.Inches, 25.4)):
        doc = Rhino.RhinoDoc.CreateHeadless(None)
        doc.ModelUnitSystem = system
        scale, name = NS['mm_per_document_unit'](doc)
        assert scale == pytest.approx(factor) and name == str(system)
        doc.Dispose()


def test_bars_become_polylines_and_pipes():
    points = [(0, 0, 0), (200, 0, 0), (200, 100, 0)]
    curve = NS['polyline_curve'](points)
    assert curve.PointCount == 3
    assert NS['curve_points'](curve) == [(0.0, 0.0, 0.0), (200.0, 0.0, 0.0),
                                         (200.0, 100.0, 0.0)]
    pipe = NS['pipe_brep'](curve, 4.0, 0.01)
    assert pipe is not None and pipe.IsSolid
    length = 300.0
    assert pipe.GetVolume() == pytest.approx(np.pi * 16 * length, rel=0.02)


# VERTEX COLOURS FROM THE TEXTURE (8.175) -------------------------------------
import System.Drawing as _sd  # noqa: E402
import System.Drawing.Imaging as _sdi  # noqa: E402

DO = Rhino.DocObjects
CENTRE = G.Point3d(10, 20, 30)


def _gradient_png(path, size=64):
    """An image whose red is the column (x * 4), green the row counted from
    the BOTTOM ((size - 1 - y) * 4) and blue 128: a colour tells where it was
    sampled, and the V axis is checked."""
    bitmap = _sd.Bitmap(size, size)
    for y in range(size):
        for x in range(size):
            bitmap.SetPixel(x, y, _sd.Color.FromArgb(255, x * 4, (size - 1 - y) * 4, 128))
    bitmap.Save(str(path), _sdi.ImageFormat.Png)
    bitmap.Dispose()
    return str(path)


def _with_uv(mesh, centre=CENTRE, radius=50.0):
    """Spherical texture coordinates: u around the z axis, v from the south
    to the north pole."""
    mesh.TextureCoordinates.Clear()
    for i in range(mesh.Vertices.Count):
        v = mesh.Vertices[i]
        u = 0.5 + np.arctan2(v.Y - centre.Y, v.X - centre.X) / (2 * np.pi)
        w = 0.5 + np.arcsin(np.clip((v.Z - centre.Z) / radius, -1, 1)) / np.pi
        mesh.TextureCoordinates.Add(float(u), float(w))
    return mesh


def _expected_gradient(vertices, size=64):
    """What the gradient image gives a vertex of the spherical mapping (away
    from the seam and the poles, where the mapping itself is not smooth)."""
    rel = vertices - np.array([10.0, 20.0, 30.0])
    u = 0.5 + np.arctan2(rel[:, 1], rel[:, 0]) / (2 * np.pi)
    v = 0.5 + np.arcsin(np.clip(rel[:, 2] / 50.0, -1, 1)) / np.pi
    red = np.clip(u * size - 0.5, 0, size - 1) * 4
    green = np.clip(v * size - 0.5, 0, size - 1) * 4        # v up = green up
    return np.column_stack([red, green]), u, v


def _doc_with_texture(path, **texture):
    doc = Rhino.RhinoDoc.CreateHeadless(None)
    material = DO.Material()
    material.ToPhysicallyBased()
    tex = DO.Texture()
    tex.FileName = path
    for key, value in texture.items():
        setattr(tex, key, value)
    assert material.SetTexture(tex, DO.TextureType.PBR_BaseColor)
    attributes = DO.ObjectAttributes()
    attributes.MaterialIndex = doc.Materials.Add(material)
    attributes.MaterialSource = DO.ObjectMaterialSource.MaterialFromObject
    return doc, attributes


def _add_mesh(doc, attributes, mesh):
    return doc.Objects.AddMesh(mesh, attributes)


def test_reduce_keeps_the_texture_coordinates_with_their_vertices():
    """The stop point of 8.175: Mesh.Reduce (as reduce_mesh calls it) keeps
    one texture coordinate per vertex, and each stays with its vertex."""
    mesh = _with_uv(_sphere(5))
    for target in (500, 2000, 6000):
        reduced = NS['reduce_mesh'](mesh, target)
        assert reduced.TextureCoordinates.Count == reduced.Vertices.Count > 0
        vertices, _, _ = NS['mesh_arrays'](reduced)
        _, u, v = _expected_gradient(vertices.astype(float))
        tc = np.array([[reduced.TextureCoordinates[i].X, reduced.TextureCoordinates[i].Y]
                       for i in range(reduced.Vertices.Count)])
        off_seam = (np.abs(u - 0.5) < 0.45) & (np.abs(v - 0.5) < 0.45)
        # the coordinate still belongs to the vertex it is stored with
        assert np.abs(tc[off_seam, 0] - u[off_seam]).max() < 0.06
        assert np.abs(tc[off_seam, 1] - v[off_seam]).max() < 0.06


def test_an_image_file_is_read_as_bgra_without_a_call_per_pixel(tmp_path):
    path = _gradient_png(tmp_path / 'g.png', 16)
    pixels, keep = NS['read_image'](path)
    assert pixels.shape == (16, 16, 4) and pixels.dtype == np.uint8
    top_left = pixels[0, 0]                                  # B, G, R, A of (x 0, y 0)
    assert top_left.tolist() == [128, 15 * 4, 0, 255]
    assert pixels[15, 15].tolist() == [128, 0, 15 * 4, 255]
    with pytest.raises(ValueError):
        NS['read_image'](str(tmp_path / 'missing.png'))


def test_a_mesh_is_coloured_from_its_texture_with_the_v_axis_up(tmp_path):
    path = _gradient_png(tmp_path / 'g.png')
    mesh = G.Mesh.CreateFromPlane(G.Plane.WorldXY, G.Interval(0, 1), G.Interval(0, 1), 8, 8)
    mesh.TextureCoordinates.Clear()
    for i in range(mesh.Vertices.Count):                      # u = x, v = y of the plane
        mesh.TextureCoordinates.Add(float(mesh.Vertices[i].X), float(mesh.Vertices[i].Y))
    doc, attributes = _doc_with_texture(path)
    guid = _add_mesh(doc, attributes, mesh)
    texture, reason = NS['texture_image_for'](guid, mesh, doc)
    assert reason is None and texture.wrap_u == 'repeat' and texture.name == 'g.png'
    colors = NS['texture_colors'](texture, mesh)
    vertices, _, _ = NS['mesh_arrays'](mesh)
    for position, colour in zip(vertices, colors):
        x, y = position[0], position[1]
        if not (0.05 < x < 0.95 and 0.05 < y < 0.95):
            continue                       # at the edge a repeating texture blends with its far side
        assert abs(int(colour[0]) - np.clip(x * 64 - 0.5, 0, 63) * 4) <= 4      # red follows u
        assert abs(int(colour[1]) - np.clip(y * 64 - 0.5, 0, 63) * 4) <= 4      # green follows v (up)
        assert colour[2] == 128
    doc.Dispose()


@pytest.mark.parametrize('own_colours', [False, True])
def test_every_level_takes_its_colours_from_its_own_texture_coordinates(tmp_path, own_colours):
    path = _gradient_png(tmp_path / 'g.png')
    mesh = _with_uv(_sphere(5))                               # 20480 faces: Original, Reduced, Preview
    if own_colours:
        for i in range(mesh.Vertices.Count):
            mesh.VertexColors.Add(200, 10, 10)
    doc, attributes = _doc_with_texture(path)
    guid = _add_mesh(doc, attributes, mesh)
    texture, _ = NS['texture_image_for'](guid, mesh, doc)
    info = {}
    entry, levels = NS['export_mesh'](mesh, str(tmp_path / 'out'), 0, [1, 2, 3], texture, info)
    assert levels == ['detailed', 'reduced']
    assert info['textured'] and info['replaced'] is own_colours and not info['lost']
    folder = tmp_path / 'out' / 'meshes' / '0'
    for name in ('detailed.ply', 'reduced.ply'):
        ply = NS['parse_ply']((folder / name).read_bytes())
        expected, u, v = _expected_gradient(np.asarray(ply['vertices'], dtype=float))
        colours = np.asarray(ply['colors'], dtype=float)
        away = (np.abs(u - 0.5) < 0.4) & (np.abs(v - 0.5) < 0.4)
        assert np.abs(colours[away, 0] - expected[away, 0]).max() < 14, name
        assert np.abs(colours[away, 1] - expected[away, 1]).max() < 14, name
        assert set(colours[:, 2]) == {128.0}                  # the texture, not the 200 10 10 of the mesh
    # the inline Preview carries the texture colours, from its own reduction
    pv = np.asarray(entry['vertices'], dtype=float)
    pc = np.asarray(entry['colors'], dtype=float)
    expected, u, v = _expected_gradient(pv)
    away = (np.abs(u - 0.5) < 0.4) & (np.abs(v - 0.5) < 0.4)
    assert len(pv) < 4000 and np.abs(pc[away, 0] - expected[away, 0]).max() < 14
    doc.Dispose()


def test_stage_geometry_colours_a_referenced_mesh_and_says_so(tmp_path):
    path = _gradient_png(tmp_path / 'g.png')
    mesh = _with_uv(_sphere(5))
    for i in range(mesh.Vertices.Count):
        mesh.VertexColors.Add(200, 10, 10)
    doc, attributes = _doc_with_texture(path)
    guid = _add_mesh(doc, attributes, mesh)
    notes = []
    geometry, mani, move = NS['stage_geometry'](
        [mesh], str(tmp_path / 'stage'), references=[guid], doc=doc, notes=notes)
    assert mani['meshes'] == {0: ['detailed', 'reduced']} or mani['meshes'] == {'0': ['detailed', 'reduced']}
    # said because the texture replaced colours the mesh had
    assert len(notes) == 1 and 'its vertex colours were replaced by colours from the texture g.png' in notes[0]
    assert 'bilinear' in notes[0] and 'wrap repeat' in notes[0]
    assert 'colors' in geometry['meshes'][0]
    # the input mesh is not touched
    assert mesh.VertexColors.Count == mesh.Vertices.Count and mesh.VertexColors[0].R == 200
    doc.Dispose()


def test_a_texture_on_a_mesh_without_colours_colours_it_and_stays_silent(tmp_path):
    path = _gradient_png(tmp_path / 'g.png')
    mesh = _with_uv(_sphere(5))                               # no vertex colours of its own
    doc, attributes = _doc_with_texture(path)
    guid = _add_mesh(doc, attributes, mesh)
    geometry, notes = _staged(mesh, guid, doc, tmp_path)
    assert 'colors' in geometry['meshes'][0] and notes == []
    doc.Dispose()


def _staged(mesh, reference, doc, tmp_path):
    notes = []
    geometry, _, _ = NS['stage_geometry']([mesh], str(tmp_path / 'stage'), references=[reference],
                                          doc=doc, notes=notes)
    return geometry, notes


def test_the_usual_cases_are_staged_as_before_and_say_nothing(tmp_path):
    """No reference (internalised or Grasshopper-made), an object that is not
    in the document, a material without a bitmap: the old behaviour, silent
    (8.175), also when the mesh has colours of its own."""
    path = _gradient_png(tmp_path / 'g.png')
    coloured = _with_uv(_sphere(3))
    for i in range(coloured.Vertices.Count):
        coloured.VertexColors.Add(200, 10, 10)
    doc, attributes = _doc_with_texture(path)
    # 1 no reference at all
    geometry, notes = _staged(coloured, None, doc, tmp_path)
    assert notes == []                                        # the preview is reduced: its colours are the mesh's own
    assert set(map(tuple, geometry['meshes'][0]['colors'])) == {(200, 10, 10)}
    plain = _sphere(3)
    geometry, notes = _staged(plain, None, doc, tmp_path)
    assert notes == [] and 'colors' not in geometry['meshes'][0]
    # 2 a reference to an object that is not in the document
    _, notes = _staged(plain, System.Guid.NewGuid(), doc, tmp_path)
    assert notes == []
    doc.Dispose()
    # 3 a material without a bitmap
    doc2 = Rhino.RhinoDoc.CreateHeadless(None)
    bare = _with_uv(_sphere(3))
    bare_guid = doc2.Objects.AddMesh(bare)
    geometry, notes = _staged(bare, bare_guid, doc2, tmp_path)
    assert notes == [] and 'colors' not in geometry['meshes'][0]
    doc2.Dispose()


def test_a_texture_that_cannot_be_used_is_staged_as_before_with_a_remark(tmp_path):
    path = _gradient_png(tmp_path / 'g.png')
    # the mesh has no texture coordinates
    plain = _sphere(3)
    doc, attributes = _doc_with_texture(path)
    guid = _add_mesh(doc, attributes, plain)
    geometry, notes = _staged(plain, guid, doc, tmp_path)
    assert len(notes) == 1 and 'no texture coordinates' in notes[0] and 'keeps its own colours' in notes[0]
    assert 'colors' not in geometry['meshes'][0]
    doc.Dispose()
    # the file is gone
    doc3, attributes3 = _doc_with_texture(str(tmp_path / 'gone.png'))
    textured = _with_uv(_sphere(3))
    gone = _add_mesh(doc3, attributes3, textured)
    _, notes = _staged(textured, gone, doc3, tmp_path)
    assert 'texture file is missing (gone.png)' in notes[0]
    doc3.Dispose()
    # a file that is no image
    junk = tmp_path / 'junk.png'
    junk.write_bytes(b'not an image')
    doc5, attributes5 = _doc_with_texture(str(junk))
    shown = _with_uv(_sphere(3))
    guid5 = _add_mesh(doc5, attributes5, shown)
    _, notes = _staged(shown, guid5, doc5, tmp_path)
    assert 'cannot be read' in notes[0]
    doc5.Dispose()
    # a texture transform in the material; the texture switched off
    # (the mapping channel of a texture is read-only in RhinoCommon: tested in test_texture.py)
    for settings, words in (({'UvwTransform': G.Transform.Scale(G.Plane.WorldXY, 2.0, 2.0, 1.0)}, 'transform'),
                            ({'Enabled': False}, 'switched off')):
        doc4, attributes4 = _doc_with_texture(path, **settings)
        shown = _with_uv(_sphere(3))
        guid4 = _add_mesh(doc4, attributes4, shown)
        geometry, notes = _staged(shown, guid4, doc4, tmp_path)
        assert words in notes[0] and 'colors' not in geometry['meshes'][0], settings
        doc4.Dispose()


def test_a_texture_that_clamps_clamps(tmp_path):
    path = _gradient_png(tmp_path / 'g.png')
    mesh = G.Mesh.CreateFromPlane(G.Plane.WorldXY, G.Interval(0, 1), G.Interval(0, 1), 1, 1)
    mesh.TextureCoordinates.Clear()
    for i in range(mesh.Vertices.Count):                      # coordinates far outside 0..1
        mesh.TextureCoordinates.Add(3.0 + float(mesh.Vertices[i].X), 5.0 + float(mesh.Vertices[i].Y))
    doc, attributes = _doc_with_texture(path, WrapU=DO.TextureUvwWrapping.Clamp,
                                        WrapV=DO.TextureUvwWrapping.Clamp)
    guid = _add_mesh(doc, attributes, mesh)
    texture, _ = NS['texture_image_for'](guid, mesh, doc)
    assert texture.wrap_u == 'clamp' and texture.wrap_v == 'clamp'
    colours = NS['texture_colors'](texture, mesh)
    assert (colours[:, 0] == 252).all() and (colours[:, 1] == 252).all()    # the top right corner pixel
    doc.Dispose()


class _Goo:
    """A GH_Mesh as the helpers read it: IsReferencedGeometry, ReferenceID, Value."""

    def __init__(self, value, reference=None):
        self.Value = value
        self.IsReferencedGeometry = reference is not None
        self.ReferenceID = reference


class _Param:
    def __init__(self, name, goos):
        self.Name = self.NickName = name

        class _Data:
            def AllData(_, skip_null):
                return iter(goos)
        self.VolatileData = _Data()


class _Component:
    def __init__(self, *params):
        class _Params:
            Input = list(params)
        self.Params = _Params()


def test_the_references_of_a_geometry_input_line_up_with_its_items():
    a, b, c = _sphere(1), _sphere(2), G.PointCloud()
    guid = System.Guid.NewGuid()
    component = _Component(_Param('Capture', []),
                           _Param('Geometry', [_Goo(a, guid), _Goo(b), _Goo(c)]))
    got = NS['input_references'](component, 'Geometry', [a, b, c])
    assert got == [guid, None, None]
    assert NS['input_references'](component, 'Geometry', [a, b]) is None          # counts differ
    assert NS['input_references'](component, 'Geometry', [b, a, c]) is None       # another mesh in the slot
    assert NS['input_references'](component, 'Nothing', [a]) is None
    assert NS['input_references'](_Component(_Param('Geometry', [_Goo(a, System.Guid.Empty)])),
                                  'Geometry', [a]) == [None]


def test_a_texture_on_a_render_material_is_found_too(tmp_path):
    """A textured scan imported into Rhino 8 carries a render material."""
    path = _gradient_png(tmp_path / 'g.png', 16)
    doc = Rhino.RhinoDoc.CreateHeadless(None)
    material = DO.Material()
    material.ToPhysicallyBased()
    tex = DO.Texture()
    tex.FileName = path
    assert material.SetTexture(tex, DO.TextureType.PBR_BaseColor)
    render = Rhino.Render.RenderMaterial.CreateBasicMaterial(material, doc)
    doc.RenderMaterials.Add(render)
    attributes = DO.ObjectAttributes()
    attributes.RenderMaterial = render
    mesh = _with_uv(_sphere(2))
    guid = doc.Objects.AddMesh(mesh, attributes)
    texture, reason = NS['texture_image_for'](guid, mesh, doc)
    assert reason is None and texture.name == 'g.png'
    doc.Dispose()
