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
