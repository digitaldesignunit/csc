"""The script components in a headless Rhino 8 (``CSC_TEST_RHINO=1``): the
Create components end to end into the Add components, the read-path
components on real geometry, the frame components and the Session's mesh
download. Run in the Python 3.9 stack of Rhino 8 (a scratch venv)."""

from __future__ import annotations

import json
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

import compstub  # noqa: E402
from csc_gh import build as b  # noqa: E402
from csc_gh import frame as csc_frame  # noqa: E402
from csc_gh import read as r  # noqa: E402
from libns import namespace  # noqa: E402
from test_components import _core, _token, CREATED, UUID_A, UUID_B  # noqa
from test_upload import FakeCore, Response  # noqa: E402

NS = namespace()

G = Rhino.Geometry
COLUMNS = ('IdentityID', 'Name', 'OriginalFunction', 'Material', 'Color', 'Location',
           'BoundingBox', 'Frame', 'Descriptors', 'Proxies',
           'CaptureMarkers', 'Capture', 'Attributes', 'ConditionGrade',
           'ManufacturedAt', 'ManufacturedPrecision', 'Origin',
           'ParentIdentities')


def _curve(points):
    polyline = G.Polyline()
    for point in points:
        polyline.Add(point)
    return polyline.ToPolylineCurve()


def _sphere(subdivisions=5):
    return G.Mesh.CreateIcoSphere(G.Sphere(G.Point3d(100, 200, 300), 50),
                                  subdivisions)


def _box():
    plane = G.Plane(G.Point3d(500, 0, 0), G.Vector3d(1, 1, 0),
                    G.Vector3d(-1, 1, 0))
    return G.Box(plane, G.Interval(-30, 30), G.Interval(-10, 10),
                 G.Interval(-5, 5)).ToBrep()


def _extrusion():
    pts = [G.Point3d(x, y, 0) for x, y in
           ((0, 0), (40, 0), (40, 20), (0, 20), (0, 0))]
    return G.Extrusion.Create(_curve(pts), 10.0, True)


def _create_identity(tmp_path, geometry, **kwargs):
    module = compstub.load_component('CreateComponentIdentity')
    compstub.patch_library(module, 'staging_root', lambda: str(tmp_path))
    obj = compstub.instance(module, 'CreateComponentIdentity')
    args = dict(
        ClearLocalStorage=False, IdentityID=UUID_A, Dataset='ds',
        Identity=json.dumps(b.identity_metadata('IfcBeam', 'concrete')),
        Snapshot=json.dumps(b.snapshot_metadata('Lintel', color=[9, 8, 7])),
        Capture=None, Geometry=geometry, ParentIdentity=None, Centre=False)
    args.update(kwargs)
    return obj.RunScript(**args), obj, module


def test_create_identity_stages_and_describes_all_three_kinds(tmp_path):
    text_json, obj, module = _create_identity(
        tmp_path, [_sphere(5), _box(), _extrusion()])
    assert compstub.messages(obj)['error'] == [], compstub.messages(obj)
    body = json.loads(text_json)
    assert b.problems_of_identity(body) == []
    snapshot = body['snapshot']
    geometry = snapshot['geometry']
    assert len(geometry['meshes']) == 1
    assert len(geometry['meshes'][0]['faces']) < 5000          # the Preview
    assert [p['primitive'] for p in geometry['proxies']] == ['box', 'prism']
    assert [p['role'] for p in geometry['proxies']] == ['primary', 'part']
    assert snapshot['color'] == [9, 8, 7] and snapshot['name'] == 'Lintel'
    assert body['original_function'] == 'IfcBeam' and body['id'] == UUID_A
    # nothing the server derives and nothing 0.5 is in the request
    assert not {'bbx', 'bbx_origin', 'iframe', 'pca_frame', 'complexity',
                'type'} & (set(body) | set(snapshot))
    folder = tmp_path / b.staging_key(text_json)
    manifest = json.loads((folder / 'manifest.json').read_text())
    assert manifest['meshes'] == {'0': ['detailed', 'reduced']}
    assert (folder / 'meshes' / '0' / 'detailed.ply').stat().st_size > 0
    assert (folder / 'meshes' / '0' / 'reduced.ply').stat().st_size > 0
    assert 'file(s) staged' in obj.Component.Message
    assert [p.name for p in tmp_path.iterdir()] == [folder.name]  # no tmp


def test_create_then_add_uploads_what_was_staged(tmp_path):
    text_json, _, _ = _create_identity(tmp_path, [_sphere(5)])
    core = _core()
    core.is_valid = lambda: True
    add = compstub.load_component('AddComponentIdentity',
                                  sticky={'CSC_AuthCore': core})
    compstub.patch_library(add, 'staging_root', lambda: str(tmp_path))
    obj = compstub.instance(add, 'AddComponentIdentity')
    tree = obj.RunScript(text_json, True)
    puts = [c for c in core.calls if c[0] == 'PUT']
    assert [c[1].rsplit('/', 2)[-2:] for c in puts] == [['0', 'detailed'],
                                                        ['0', 'reduced']]
    assert all(c[4][:3] == b'ply' for c in puts)       # real PLY bytes
    assert tree.DataCount == 1 and compstub.messages(obj)['error'] == []


def test_a_small_mesh_stages_nothing(tmp_path):
    text_json, obj, _ = _create_identity(tmp_path, [_sphere(2), _box()])
    body = json.loads(text_json)
    assert len(body['snapshot']['geometry']['meshes'][0]['faces']) == 320
    assert list(tmp_path.iterdir()) == []              # no files to upload
    assert 'staged' not in obj.Component.Message


def test_centring_is_an_input_and_off_by_default(tmp_path):
    plain, _, _ = _create_identity(tmp_path, [_sphere(2)])
    centred, obj, _ = _create_identity(tmp_path, [_sphere(2)], Centre=True)
    p = np.array(json.loads(plain)['snapshot']['geometry']['meshes'][0][
        'vertices'])
    c = np.array(json.loads(centred)['snapshot']['geometry']['meshes'][0][
        'vertices'])
    assert p.mean(axis=0) == pytest.approx([100, 200, 300], abs=1e-2)
    assert c.mean(axis=0) == pytest.approx([0, 0, 0], abs=1e-2)
    assert any('Centred' in m for m in compstub.messages(obj)['remark'])


def test_a_cut_names_its_parents_and_states_nothing_else(tmp_path):
    text_json, obj, _ = _create_identity(
        tmp_path, [_box()], Identity=None, ParentIdentity=[UUID_B],
        IdentityID=None)
    body = json.loads(text_json)
    assert body['parent_identities'] == [UUID_B]
    assert 'original_function' not in body and 'id' not in body
    assert body['snapshot']['geometry']['proxies'][0]['primitive'] == 'box'


@pytest.mark.parametrize('kwargs, fragment', [
    (dict(geometry=[]), 'Geometry'),
    (dict(geometry=[G.Sphere(G.Point3d.Origin, 5).ToBrep()]), 'box'),
    (dict(geometry=[G.Point3d(0, 0, 0)]), 'not supported'),
    (dict(geometry=[_box()], Dataset=''), 'Dataset'),
    (dict(geometry=[_box()], Identity=None), 'original_function'),
    (dict(geometry=[_box()], IdentityID='nope'), 'UUID'),
])
def test_create_identity_explains_a_refusal(tmp_path, kwargs, fragment):
    geometry = kwargs.pop('geometry')
    text_json, obj, _ = _create_identity(tmp_path, geometry, **kwargs)
    assert text_json == ''
    assert fragment in ' '.join(compstub.messages(obj)['error'])
    assert list(tmp_path.iterdir()) == []              # nothing left behind


def test_create_snapshot_makes_the_envelope(tmp_path):
    module = compstub.load_component('CreateComponentSnapshot')
    compstub.patch_library(module, 'staging_root', lambda: str(tmp_path))
    obj = compstub.instance(module, 'CreateComponentSnapshot')
    text_json = obj.RunScript(False, UUID_A, json.dumps(
        b.snapshot_metadata('Scan 2')), json.dumps(b.capture('lidar')),
        [_sphere(5)], UUID_B, False)
    envelope = json.loads(text_json)
    assert envelope['identity_id'] == UUID_A
    assert envelope['supersedes'] == UUID_B
    assert envelope['snapshot']['capture'] == {'method': 'lidar'}
    assert b.problems_of_envelope(envelope) == []
    assert (tmp_path / b.staging_key(text_json) / 'manifest.json').is_file()
    # ClearLocalStorage empties the folder and makes nothing
    assert obj.RunScript(True, None, None, None, [], None, False) == ''
    assert list(tmp_path.iterdir()) == []


# READ PATH -------------------------------------------------------------------
FRAME = {'o': [10, 20, 30], 'x': [0, 1, 0], 'y': [-1, 0, 0], 'z': [0, 0, 1]}


def _passport(snapshot_patch=None, identity_patch=None):
    snapshot = {
        '_id': UUID_B, 'name': 'Lintel', 'color': [10, 20, 30],
        'location': {'lat': 49.8, 'lon': 8.6}, 'frame': FRAME,
        'bbx': [400, 200, 50], 'properties': {
            'condition_grade': {'range': [3, 2]}},
        'capture': {'method': 'lidar', 'markers': [
            {'label': 'blue_1', 'role': 'rig', 'point': [1, 2, 3]}]},
        'descriptors': {'hks': [1, 2]},
        'geometry': {'meshes': [b.inline_mesh(
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]])],
            'point_clouds': [], 'proxies': []}}
    identity = {'_id': UUID_A, 'original_function': 'IfcBeam',
                'material': 'concrete', 'attributes': {'k': 1},
                'manufactured_at': '2001-01-01T00:00:00Z',
                'manufactured_precision': 'year',
                'origin': {'kind': 'surplus'},
                'parent_identities': [UUID_B]}
    snapshot.update(snapshot_patch or {})
    identity.update(identity_patch or {})
    return {'identity': identity, 'snapshots': [snapshot]}


def _disassemble(passport):
    module = compstub.load_component('DisassembleComponent')
    obj = compstub.instance(module, 'DisassembleComponent')
    tree = compstub.FakeInputTree([[json.dumps(passport)]])
    results = obj.RunScript(tree)
    return dict(zip(COLUMNS, results)), obj


def test_disassemble_reads_the_0_6_fields():
    out, obj = _disassemble(_passport())
    assert compstub.messages(obj)['error'] == [], compstub.messages(obj)
    value = {name: tree.values for name, tree in out.items()}
    assert value['IdentityID'] == [UUID_A] and value['Name'] == ['Lintel']
    assert value['OriginalFunction'] == ['IfcBeam']
    assert value['Material'] == ['concrete']
    assert value['ConditionGrade'] == [2]
    assert value['ManufacturedPrecision'] == ['year']
    assert json.loads(value['Origin'][0]) == {'kind': 'surplus'}
    assert value['ParentIdentities'] == [UUID_B]
    assert json.loads(value['Capture'][0])['method'] == 'lidar'
    marker = value['CaptureMarkers'][0]
    assert (marker.X, marker.Y, marker.Z) == (1.0, 2.0, 3.0)
    frame = value['Frame'][0]
    assert (frame.Origin.X, frame.Origin.Y, frame.Origin.Z) == (10, 20, 30)
    assert (frame.XAxis.Y, frame.YAxis.X) == (1.0, -1.0)
    box = value['BoundingBox'][0]
    assert (box.X.Length, box.Y.Length, box.Z.Length) == pytest.approx(
        (400, 200, 50))
    mesh = value['Proxies'][0]
    assert mesh.Faces.Count == 1 and mesh.GetUserString('csc_mesh_index') \
        == '0'
    assert mesh.VertexColors[0].R == 10          # the piece colour
    assert 'ReinforcementJson' not in value


def test_disassemble_applies_the_client_side_placement():
    plain, _ = _disassemble(_passport())
    placed = r.with_placement(_passport(), {
        'o': [1000, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]})
    moved, _ = _disassemble(placed)
    a = plain['Proxies'].values[0].GetBoundingBox(True)
    c = moved['Proxies'].values[0].GetBoundingBox(True)
    assert c.Min.X - a.Min.X == pytest.approx(1000)
    assert moved['Frame'].values[0].OriginX == pytest.approx(1010)
    # no condition, no frame yet: the outputs are empty, not wrong
    bare, obj = _disassemble(_passport({'properties': {}, 'frame': None}))
    assert bare['ConditionGrade'].DataCount == 0
    assert bare['Frame'].DataCount == 0
    assert any('no frame' in w for w in compstub.messages(obj)['warning'])


def test_disassemble_builds_an_authored_shape_without_a_scan():
    box = b.box_proxy(np.array([[x, y, z] for x in (0, 40) for y in (0, 20)
                                for z in (0, 10)]), (1, 0, 0), (0, 0, 1))
    out, obj = _disassemble(_passport({'geometry': {
        'meshes': [], 'point_clouds': [], 'proxies': [box]}}))
    shape = out['Proxies'].values[0]
    assert shape.GetBoundingBox(True).Diagonal.Length == pytest.approx(
        np.linalg.norm([40, 20, 10]))
    assert shape.GetUserString('csc_proxy_index') == '0'
    # a scanned piece does not show its fitted proxies
    fitted = dict(box, fit={'method': 'ransac'})
    out, _ = _disassemble(_passport())
    assert out['Proxies'].DataCount == 1


class FetchCore:
    """What the fetch components ask of the Session core."""

    def __init__(self, passport=None, meshes=None):
        self.passport = passport
        self.meshes = meshes or {}
        self.mesh_calls = []

    def is_valid(self):
        return True

    def validate_uuid(self, value):
        return len(str(value)) == 36

    def passport_json_string(self, passport):
        return json.dumps(passport)

    def normalize_passport_output(self, passport):
        return passport

    def cached_get_passport(self, identity_id, snapshots=None):
        return Response(200, self.passport)

    def cached_get_snapshot_mesh(self, snapshot_id, index, resolution):
        self.mesh_calls.append((snapshot_id, index, resolution))
        mesh = self.meshes.get((index, resolution))
        return mesh, 'etag', False

    def cached_get_snapshot_point_cloud(self, snapshot_id, index):
        return None


def _fetch(name, passport, core=None):
    core = core or FetchCore(passport)
    module = compstub.load_component(name, sticky={'CSC_AuthCore': core})
    obj = compstub.instance(module, name)
    geometry, source, snapshot_id = obj.RunScript(json.dumps(passport))
    return (list(geometry), list(source), list(snapshot_id)), obj, core


def _authored_passport():
    box = b.box_proxy(np.array([[x, y, z] for x in (0, 40) for y in (0, 20)
                                for z in (0, 10)]), (1, 0, 0), (0, 0, 1))
    return _passport({'geometry': {'meshes': [], 'point_clouds': [],
                                   'proxies': [box]}})


@pytest.mark.parametrize('name', ['FetchReducedGeometry',
                                  'FetchOriginalGeometry'])
def test_an_authored_only_piece_is_fetched_from_its_parameters(name):
    (geometry, source, ids), obj, _ = _fetch(name, _authored_passport())
    assert compstub.messages(obj)['error'] == [], compstub.messages(obj)
    assert source == ['authored'] and ids == [UUID_B]
    shape = geometry[0]
    assert shape.GetBoundingBox(True).Diagonal.Length == pytest.approx(
        np.linalg.norm([40, 20, 10]))
    assert shape.GetUserString('csc_proxy_index') == '0'
    assert json.loads(shape.GetUserString('csc_component'))[
        'identity']['_id'] == UUID_A
    # the client-side placement moves it
    placed = r.with_placement(_authored_passport(), {
        'o': [0, 500, 0], 'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]})
    (moved, _, _), _, _ = _fetch(name, placed)
    assert moved[0].GetBoundingBox(True).Min.Y - \
        shape.GetBoundingBox(True).Min.Y == pytest.approx(500)


def test_the_original_fetch_prefers_the_original_then_the_reduced_level():
    passport = _passport({
        'mesh_ply_resolutions': {'0': ['reduced', 'detailed']}})
    reduced = G.Mesh.CreateIcoSphere(G.Sphere(G.Point3d.Origin, 5), 1)
    original = G.Mesh.CreateIcoSphere(G.Sphere(G.Point3d.Origin, 5), 2)
    core = FetchCore(passport, {(0, 'detailed'): original,
                                (0, 'reduced'): reduced})
    (geometry, source, _), _, _ = _fetch('FetchOriginalGeometry', passport,
                                         core)
    assert source == ['original'] and geometry[0].Faces.Count == 320
    assert core.mesh_calls == [(UUID_B, 0, 'detailed')]
    core = FetchCore(passport, {(0, 'reduced'): reduced})
    (geometry, source, _), _, _ = _fetch('FetchOriginalGeometry', passport,
                                         core)
    assert source == ['reduced'] and geometry[0].Faces.Count == 80
    core = FetchCore(passport, {(0, 'reduced'): reduced})
    (geometry, source, _), _, _ = _fetch('FetchReducedGeometry', passport,
                                         core)
    assert source == ['reduced']
    (geometry, source, _), _, _ = _fetch('FetchReducedGeometry', passport,
                                         FetchCore(passport))
    assert source == ['preview'] and geometry[0].Faces.Count == 1


# FRAMES ----------------------------------------------------------------------
def _frame_module(name):
    module = compstub.load_component(name)
    return module, compstub.instance(module, name)


def test_apply_frame_moves_the_geometry_to_its_canonical_orientation():
    module, obj = _frame_module('ApplyFrame')
    passport = _passport({'frame': FRAME})
    brep = _box()
    brep.SetUserString('csc_component', json.dumps(passport))
    out, plane = obj.RunScript(brep, None)
    assert compstub.messages(obj)['error'] == [], compstub.messages(obj)
    expected = brep.Duplicate()
    expected.Transform(NS['canonical_transform'](FRAME))
    assert out.GetBoundingBox(True).Min.DistanceTo(
        expected.GetBoundingBox(True).Min) < 1e-9
    assert (plane.OriginX, plane.OriginY, plane.OriginZ) == (10, 20, 30)
    stored = json.loads(out.GetUserString('csc_component'))
    placement = r.placement_of(stored)
    assert np.allclose(r.placement_matrix(placement),
                       r.canonical_matrix(FRAME), atol=1e-12)
    assert brep.GetBoundingBox(True).Min.X == pytest.approx(
        _box().GetBoundingBox(True).Min.X)           # the input is untouched


def test_apply_frame_on_passport_json_sets_the_placement():
    module, obj = _frame_module('ApplyFrame')
    text_json, plane = obj.RunScript(json.dumps(_passport()), None)
    placed = json.loads(text_json)
    assert r.placement_of(placed) == {
        k: [float(v) for v in r.canonical_placement(FRAME)[k]]
        for k in 'oxyz'}
    assert 'csc_placement' not in json.dumps(_passport())
    bad, plane = obj.RunScript('not a passport', None)
    assert bad is None and compstub.messages(obj)['error']


def test_apply_frame_undoes_an_earlier_placement():
    module, obj = _frame_module('ApplyFrame')
    placement = {'o': [100, 0, 0], 'x': [0, 1, 0], 'y': [-1, 0, 0],
                 'z': [0, 0, 1]}
    passport = r.with_placement(_passport(), placement)
    stored = _box()
    placed = stored.Duplicate()
    placed.Transform(NS['placement_transform'](placement))
    placed.SetUserString('csc_component', json.dumps(passport))
    out, _ = obj.RunScript(placed, None)
    direct = stored.Duplicate()
    direct.Transform(NS['canonical_transform'](FRAME))
    assert out.GetBoundingBox(True).Min.DistanceTo(
        direct.GetBoundingBox(True).Min) < 1e-6


def test_apply_frame_computes_a_missing_frame_like_the_server():
    module, obj = _frame_module('ApplyFrame')
    plank = G.Box(G.Plane.WorldXY, G.Interval(-200, 200),
                  G.Interval(-50, 50), G.Interval(-10, 10)).ToBrep()
    rot = G.Transform.Rotation(np.radians(40), G.Vector3d.ZAxis,
                               G.Point3d.Origin)
    plank.Transform(rot)
    out, plane = obj.RunScript(plank, None)
    assert compstub.messages(obj)['error'] == [], compstub.messages(obj)
    assert any('computed locally' in m
               for m in compstub.messages(obj)['remark'])
    box = out.GetBoundingBox(True)
    assert (box.Max.X - box.Min.X) == pytest.approx(400, abs=1e-3)
    assert (box.Max.Y - box.Min.Y) == pytest.approx(100, abs=1e-3)
    assert (box.Max.Z - box.Min.Z) == pytest.approx(20, abs=1e-3)
    # a column stands when its original function says so
    column = G.Box(G.Plane.WorldXY, G.Interval(-500, 500),
                   G.Interval(-50, 50), G.Interval(-60, 60)).ToBrep()
    stood, _ = obj.RunScript(column, 'IfcColumn')
    box = stood.GetBoundingBox(True)
    assert (box.Max.Z - box.Min.Z) == pytest.approx(1000, abs=1e-3)
    # too little geometry is an error, not a crash
    nothing, plane = obj.RunScript(G.Point(G.Point3d(0, 0, 0)), None)
    assert nothing is None and compstub.messages(obj)['error']


def test_compute_frame_outputs():
    module, obj = _frame_module('ComputeFrame')
    plank = G.Box(G.Plane.WorldXY, G.Interval(-200, 200),
                  G.Interval(-50, 50), G.Interval(-10, 10)).ToBrep()
    plank.Transform(G.Transform.Rotation(np.radians(25), G.Vector3d.ZAxis,
                                         G.Point3d(5, 5, 5)))
    frame, box, extents, xform, text_json = obj.RunScript([plank], None)
    assert compstub.messages(obj)['error'] == []
    assert extents == pytest.approx([400, 100, 20], abs=1e-3)
    assert box.X.Length == pytest.approx(400, abs=1e-3)
    document = json.loads(text_json)
    assert document['version'] == csc_frame.FRAME_VERSION
    points = NS['geometry_points']([plank])
    assert document['frame'] == csc_frame.compute_frame(points)['frame']
    moved = plank.Duplicate()
    moved.Transform(xform)
    bounds = moved.GetBoundingBox(True)
    assert bounds.Center.DistanceTo(G.Point3d.Origin) < 1e-6
    nothing = obj.RunScript([], None)
    assert nothing[0] is None and compstub.messages(obj)['error']


def test_transform_component_writes_the_placement_key():
    module = compstub.load_component('TransformComponent')
    obj = compstub.instance(module, 'TransformComponent')
    passport = _passport()
    move = G.Transform.Translation(7, 8, 9)
    text_json = obj.RunScript(json.dumps(passport), move)
    snapshot = json.loads(text_json)['snapshots'][0]
    assert 'iframe' not in snapshot
    assert snapshot['csc_placement']['o'] == pytest.approx([7, 8, 9])
    # applied again it adds up: the key is the one place the placement lives
    again = json.loads(obj.RunScript(text_json, move))['snapshots'][0]
    assert again['csc_placement']['o'] == pytest.approx([14, 16, 18])


# REINFORCEMENT ---------------------------------------------------------------
def test_reinforcement_layout_from_curves():
    module = compstub.load_component('ReinforcementLayout')
    obj = compstub.instance(module, 'ReinforcementLayout')
    one = _curve([G.Point3d(0, 0, 0), G.Point3d(100, 0, 0)])
    two = _curve([G.Point3d(0, 10, 0), G.Point3d(100, 10, 0),
                  G.Point3d(100, 60, 0)])
    arc = G.ArcCurve(G.Arc(G.Point3d(0, 0, 0), 50.0, np.pi / 2))
    record = json.loads(obj.RunScript(
        [one, two, arc], ['BSt III'], [8, 10, 12], UUID_A, 'drawing',
        '2024-05-03', 'Drawing 7', '1974-05', 'ref', None, None,
        'size +-20 %', 'n'))
    assert compstub.messages(obj)['error'] == [], compstub.messages(obj)
    bars = record['payload']['bars']
    assert [x['diameter_mm'] for x in bars] == [8, 10, 12]
    assert {x['spec'] for x in bars} == {'BSt III'}
    assert len(bars[1]['points']) == 3 and len(bars[2]['points']) > 3
    assert record['position']['snapshot_id'] == UUID_A
    assert record['payload']['document']['title'] == 'Drawing 7'
    assert record['observed_at'] == '2024-05-03T00:00:00Z'
    # one value per bar or one for all, else the message says so
    bad = obj.RunScript([one, two], ['a', 'b', 'c'], [8], UUID_A, 'scan',
                        None, None, None, None, None, None, None, None)
    assert bad == '' and 'one Spec' in ' '.join(
        compstub.messages(obj)['error'])
    no_id = obj.RunScript([one], None, [8], 'x', 'scan', None, None, None,
                          None, None, None, None, None)
    assert no_id == ''


# SESSION: THE MESH DOWNLOAD --------------------------------------------------
def test_the_session_downloads_a_mesh_through_the_numpy_parse():
    module = compstub.load_component('Session')
    core = module.ns['_AuthCore']('localhost:8010', disable_cache=True)
    core.set_access_token(_token(), 'ada')
    mesh = _sphere(3)
    v, f, _ = NS['mesh_arrays'](mesh)
    data = NS['write_ply_mesh'](v, f, [1, 2, 3])
    cloud_data = NS['write_ply_cloud'](v[:50], [4, 5, 6])
    seen = []

    class Http:
        def request(self, method, url, **kwargs):
            seen.append((method, url, kwargs))
            response = Response(200, {})
            response.content = data if '/meshes/' in url else cloud_data
            response.headers = {'ETag': '"e1"'}
            return response
    core._http = Http()
    got, etag, cached = core.cached_get_snapshot_mesh('sid', 0, 'reduced')
    assert got.Faces.Count == mesh.Faces.Count and etag == '"e1"'
    assert not cached
    assert seen[0][1] == 'http://localhost:8010/snapshots/sid/meshes/0/reduced'
    assert (got.VertexColors[0].R, got.VertexColors[0].B) == (1, 3)
    cloud = core.cached_get_snapshot_point_cloud('sid', 0)
    assert cloud.Count == 50 and cloud.ContainsColors
    # a broken file is None, not an exception in the component
    data = b'not a ply'
    assert core.cached_get_snapshot_mesh('sid', 0, 'reduced')[0] is None
