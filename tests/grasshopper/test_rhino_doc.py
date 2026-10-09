"""Bake and read-back in a headless Rhino 8 (``CSC_TEST_RHINO=1``): the
built-in path (BakeComponents -> move in the document -> SyncWithRhinoDoc),
the D2P path (PassportToD2P -> commit -> move -> ReadFromD2P) and the two read
by each other, with a rotated and translated placement (P8 part B, decision
8.98). The documents are headless (``RhinoDoc.CreateHeadless``), the scripts
the real ones, a fake Session core answers (and records) what they ask."""

from __future__ import annotations

import json
import os
import types

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
from libns import namespace  # noqa: E402

NS = namespace()
G = Rhino.Geometry
UUID_I = '11111111-1111-4111-8111-111111111111'
UUID_S = '22222222-2222-4222-8222-222222222222'
UUID_I2 = '44444444-4444-4444-8444-444444444444'
UUID_S2 = '55555555-5555-4555-8555-555555555555'

d2p = pytest.importorskip('d2p_core')


class _RhinoProxy:
    """``Rhino`` for a component under test: the real module, with an active
    document (a headless Rhino has none)."""

    def __init__(self, doc):
        self.RhinoDoc = types.SimpleNamespace(ActiveDoc=doc)

    def __getattr__(self, name):
        return getattr(Rhino, name)


@pytest.fixture()
def doc():
    document = Rhino.RhinoDoc.CreateHeadless(None)
    d2p.Settings.ActiveDoc = document
    yield document
    document.Dispose()


class FakeSession:
    """A signed-in Session core: answers passport reads, records requests
    (the read-back must never write)."""

    def __init__(self, passports=None):
        self.passports = passports or {}
        self.requests = []

    def is_valid(self):
        return True

    def cached_get_passport(self, identity_id, snapshots=None,
                            extra_headers=None, timeout=20):
        self.requests.append(('GET', identity_id, snapshots))
        passport = self.passports.get(identity_id)
        code = 200 if passport else 404
        return types.SimpleNamespace(
            status_code=code, json=lambda: passport)

    def normalize_passport_output(self, passport):
        return passport

    def cached_get_snapshot_mesh(self, *args, **kwargs):
        self.requests.append(('MESH',) + args)
        return None, None, False

    def cached_get_snapshot_point_cloud(self, *args, **kwargs):
        self.requests.append(('CLOUD',) + args)
        return None


def _load(name, doc, sticky=None):
    module = compstub.load_component(name, sticky=sticky, real_rhino=True)
    compstub.patch_library(module, 'Rhino', _RhinoProxy(doc))
    return module, compstub.instance(module, name)


# PIECES ----------------------------------------------------------------------
def _box_mesh(centre=(500.0, 0.0, 0.0), size=(60.0, 20.0, 10.0), angle=45.0):
    a = np.radians(angle)
    plane = G.Plane(G.Point3d(*centre), G.Vector3d(np.cos(a), np.sin(a), 0),
                    G.Vector3d(-np.sin(a), np.cos(a), 0))
    box = G.Box(plane, G.Interval(-size[0] / 2, size[0] / 2),
                G.Interval(-size[1] / 2, size[1] / 2),
                G.Interval(-size[2] / 2, size[2] / 2))
    return G.Mesh.CreateFromBox(box, 1, 1, 1)


def _passport(identity_id=UUID_I, snapshot_id=UUID_S, mesh=None, cloud=None,
              proxies=None, **snapshot_patch):
    meshes, clouds = [], []
    points = []
    if mesh is not None:
        v, f, _ = NS['mesh_arrays'](mesh)
        meshes.append(NS['inline_mesh'](v, f))
        points.append(v.astype(float))
    if cloud is not None:
        clouds.append(NS['inline_point_cloud'](cloud))
        points.append(np.asarray(cloud, dtype=float))
    for proxy in proxies or []:
        points.append(NS['proxy_points'](proxy))
    result = NS['compute_frame'](np.vstack(points), 'IfcBeam')
    snapshot = {
        '_id': snapshot_id, 'name': 'Piece', 'color': [10, 20, 30],
        'frame': result['frame'], 'bbx': result['bbx'],
        'geometry': {'meshes': meshes, 'point_clouds': clouds,
                     'proxies': list(proxies or [])}}
    snapshot.update(snapshot_patch)
    return {'identity': {'_id': identity_id, 'original_function': 'IfcBeam',
                         'material': 'concrete'}, 'snapshots': [snapshot]}


def _box_proxy():
    z = np.array([0.0, 0.0, 1.0])
    x = np.array([np.cos(0.6), np.sin(0.6), 0.0])
    corners = np.array([[a, b, c] for a in (0, 80) for b in (0, 30)
                        for c in (0, 20)], dtype=float) + [300, -100, 40]
    proxy = NS['box_proxy'](corners, x, z)
    proxy['fit'] = {'method': 'authored'}
    return proxy


def _rotation(degrees, shift):
    xform = G.Transform.Rotation(np.radians(degrees), G.Vector3d.ZAxis,
                                 G.Point3d(0, 0, 0))
    return G.Transform.Translation(*shift) * xform


def _matrix(xform):
    return np.array([[xform[r, c] for c in range(4)] for r in range(4)])


def _move_everything(doc, xform):
    for obj in list(doc.Objects):
        doc.Objects.Transform(obj.Id, xform, True)


def _geometries(doc, kind=None):
    return [o.Geometry for o in doc.Objects
            if kind is None or isinstance(o.Geometry, kind)]


def _bake(doc, passport, level='preview', with_passport=True, core=None):
    items = NS['piece_items'](core, passport['snapshots'][0], level)
    return NS['bake_piece'](doc, passport, items, with_passport)


def _frame_of_plane(plane):
    return NS['frame_from_plane'](plane)


# THE BUILT-IN PATH, LIBRARY ---------------------------------------------------
def test_a_baked_piece_stands_in_its_frame_with_a_tag_at_the_world_plane(doc):
    passport = _passport(mesh=_box_mesh())
    result = _bake(doc, passport)
    meshes = _geometries(doc, G.Mesh)
    assert len(meshes) == 1
    bbox = meshes[0].GetBoundingBox(True)
    size = [bbox.Max.X - bbox.Min.X, bbox.Max.Y - bbox.Min.Y,
            bbox.Max.Z - bbox.Min.Z]
    # canonical: longest side along X, the box centred on the origin
    assert size == pytest.approx(passport['snapshots'][0]['bbx'], abs=1e-4)
    assert size[0] >= size[1] >= size[2]
    centre = bbox.Center
    assert [centre.X, centre.Y, centre.Z] == pytest.approx([0, 0, 0],
                                                           abs=1e-4)
    tags = NS['tagged_objects'](doc)
    assert len(tags) == 1
    plane = tags[0]['plane']
    assert [plane.OriginX, plane.OriginY, plane.OriginZ] == pytest.approx(
        [0, 0, 0], abs=1e-9)
    assert tags[0]['tags']['problems'] == []
    assert tags[0]['tags']['identity_id'] == UUID_I
    assert tags[0]['tags']['snapshot_id'] == UUID_S
    assert tags[0]['tags']['passport'] is not None
    # every baked object names its piece; the geometry carries no plane
    for obj in doc.Objects:
        assert obj.Attributes.GetUserString('csc_identity_id') == UUID_I
        assert obj.Attributes.GetUserString('csc_snapshot_id') == UUID_S
    assert [o.Attributes.GetUserString('csc_placement')
            for o in doc.Objects if isinstance(o.Geometry, G.Mesh)] == [None]
    assert doc.Layers.FindByFullPath('CSC_COMPONENTS::' + UUID_I, -1) >= 0
    assert doc.Groups.Count == 1 and result['group'] == UUID_I + '_1'


@pytest.mark.parametrize('with_passport', [True, False])
def test_a_moved_piece_reads_back_with_the_placement_that_moves_the_geometry(
        doc, with_passport):
    """The point of the whole convention: after a rotation and a move in the
    document, the placement read back puts the STORED geometry where the
    baked objects are now."""
    mesh = _box_mesh()
    passport = _passport(mesh=mesh)
    _bake(doc, passport, with_passport=with_passport)
    X = _rotation(33.0, (1000.0, -200.0, 50.0))
    _move_everything(doc, X)
    session = FakeSession({UUID_I: passport})
    pieces = NS['read_document'](doc, NS['passport_fetcher'](session))
    assert len(pieces) == 1 and pieces[0]['problems'] == []
    placed = NS['placement_of'](pieces[0]['passport'])
    assert placed is not None
    # the stored mesh moved by the placement lies on the baked mesh
    stored = mesh.DuplicateMesh()
    stored.Transform(NS['placement_transform'](placed))
    baked = _geometries(doc, G.Mesh)[0]
    v_stored, _, _ = NS['mesh_arrays'](stored)
    v_baked, _, _ = NS['mesh_arrays'](baked)
    assert np.allclose(v_stored, v_baked, atol=1e-3)
    # and the placement is the move applied to the placement drawn with
    q0 = NS['canonical_placement'](passport['snapshots'][0]['frame'])
    assert np.allclose(NS['placement_matrix'](placed),
                       _matrix(X) @ NS['placement_matrix'](q0), atol=1e-6)
    # a read with the passport on the tag needs no request at all
    assert (session.requests == []) == with_passport
    assert all(r[0] == 'GET' for r in session.requests)


def test_a_placed_piece_is_baked_where_its_placement_says(doc):
    mesh = _box_mesh(centre=(10.0, 20.0, 30.0), angle=10.0)
    base = _passport(mesh=mesh)
    placed = NS['with_placement'](base, NS['frame_from_plane'](G.Plane(
        G.Point3d(-400, 250, 80), G.Vector3d(0, 1, 0), G.Vector3d(-1, 0, 0))))
    _bake(doc, placed)
    baked = _geometries(doc, G.Mesh)[0]
    stored = mesh.DuplicateMesh()
    stored.Transform(NS['placement_transform'](NS['placement_of'](placed)))
    v_stored, _, _ = NS['mesh_arrays'](stored)
    v_baked, _, _ = NS['mesh_arrays'](baked)
    assert np.allclose(v_stored, v_baked, atol=1e-3)
    # untouched, it reads back exactly as it was baked
    piece = NS['read_document'](doc)[0]
    assert np.allclose(
        NS['placement_matrix'](NS['placement_of'](piece['passport'])),
        NS['placement_matrix'](NS['placement_of'](placed)), atol=1e-8)


def test_an_authored_box_is_baked_from_its_parameters(doc):
    proxy = _box_proxy()
    passport = _passport(proxies=[proxy])
    _bake(doc, passport)
    breps = _geometries(doc, G.Brep)
    assert len(breps) == 1
    bbox = breps[0].GetBoundingBox(True)
    size = sorted([bbox.Max.X - bbox.Min.X, bbox.Max.Y - bbox.Min.Y,
                   bbox.Max.Z - bbox.Min.Z])
    assert size == pytest.approx(sorted(proxy['params']['size']), abs=1e-6)
    assert bbox.Center.DistanceTo(G.Point3d.Origin) < 1e-6
    obj = [o for o in doc.Objects if isinstance(o.Geometry, G.Brep)][0]
    assert obj.Attributes.GetUserString('csc_proxy_index') == '0'
    X = _rotation(-70.0, (5.0, 6.0, 7.0))
    _move_everything(doc, X)
    piece = NS['read_document'](doc)[0]
    placed = NS['placement_of'](piece['passport'])
    assert np.allclose(
        NS['placement_matrix'](placed),
        _matrix(X) @ NS['placement_matrix'](
            NS['canonical_placement'](passport['snapshots'][0]['frame'])),
        atol=1e-6)


def test_a_scan_piece_bakes_its_cloud_and_mesh(doc):
    rng = np.random.default_rng(3)
    cloud = rng.uniform([0, 0, 0], [120, 30, 12], size=(400, 3)) + 50
    passport = _passport(mesh=_box_mesh(), cloud=cloud)
    result = _bake(doc, passport)
    assert len(_geometries(doc, G.Mesh)) == 1
    assert len(_geometries(doc, G.PointCloud)) == 1
    assert len(result['ids']) == 2
    kinds = sorted((o.Attributes.GetUserString('csc_mesh_index') or '',
                    o.Attributes.GetUserString('csc_point_cloud_index') or '')
                   for o in doc.Objects if not isinstance(
                       o.Geometry, G.TextEntity))
    assert kinds == [('', '0'), ('0', '')]


def test_capture_markers_are_not_baked_but_the_piece_is_unharmed(doc):
    passport = _passport(mesh=_box_mesh(), capture={
        'method': 'lidar', 'markers': [
            {'label': 'rig1', 'role': 'rig', 'point': [1, 2, 3]}]})
    _bake(doc, passport)
    assert len(_geometries(doc, G.Mesh)) == 1
    assert NS['read_document'](doc)[0]['passport'] is not None


def test_a_piece_without_a_frame_is_refused_before_anything_is_added(doc):
    passport = _passport(mesh=_box_mesh())
    del passport['snapshots'][0]['frame']
    with pytest.raises(NS['ConventionError'], match='frame'):
        _bake(doc, passport)
    assert doc.Objects.Count == 0 and doc.Layers.Count == 1


def test_two_bakes_are_two_pieces_each_read_back_on_its_own(doc):
    passport = _passport(mesh=_box_mesh())
    _bake(doc, passport)
    first = [o.Id for o in doc.Objects]
    _bake(doc, passport)
    pieces = NS['read_document'](doc)
    assert len(pieces) == 2
    assert doc.Groups.Count == 2
    # move one of the two only: they are told apart
    X = _rotation(10.0, (500.0, 0.0, 0.0))
    for guid in first:
        doc.Objects.Transform(guid, X, True)
    moved = sorted(
        NS['placement_of'](p['passport'])['o'][0]
        for p in NS['read_document'](doc))
    assert moved[0] != moved[1]


# HOSTILE TEXT IN THE DOCUMENT -------------------------------------------------
def _add_text(doc, values, plane=None):
    entity = G.TextEntity()
    entity.Text = 'tag'
    entity.Plane = plane or G.Plane.WorldXY
    attributes = Rhino.DocObjects.ObjectAttributes()
    for key, value in values.items():
        attributes.SetUserString(key, value)
    return doc.Objects.Add(entity, attributes)


def test_a_document_with_hostile_tags_gives_no_piece_and_no_request(doc):
    good = _passport(mesh=_box_mesh())
    other = _passport(identity_id=UUID_I2, snapshot_id=UUID_S2,
                      mesh=_box_mesh())
    plane = '{"o":[0,0,0],"x":[1,0,0],"y":[0,1,0],"z":[0,0,1]}'
    for values in (
            {'csc_identity_id': '../../admin', 'csc_snapshot_id': UUID_S},
            {'csc_identity_id': UUID_I, 'csc_snapshot_id': 'x' * 5000},
            {'csc_identity_id': UUID_I, 'csc_snapshot_id': UUID_S,
             'csc_placement': '{"o": 1}'},
            {'csc_identity_id': UUID_I, 'csc_snapshot_id': UUID_S,
             'csc_placement': plane,
             'csc_component': json.dumps(other)},    # somebody else's
            {'csc_identity_id': UUID_I, 'csc_snapshot_id': UUID_S,
             'csc_placement': plane,
             'csc_component': '{"identity": {"_id": 1}}'}):
        _add_text(doc, values)
    session = FakeSession({UUID_I: good})
    pieces = NS['read_document'](doc, NS['passport_fetcher'](session))
    assert len(pieces) == 5
    # only the cases whose ids are fine ask the server, by their own id,
    # with a GET, and never an id taken from somebody else's text
    for request in session.requests:
        assert request[0] == 'GET' and request[1] == UUID_I
        assert request[2] == [UUID_S]
    for piece in pieces[:3]:
        assert piece['problems']
    # an unplaced tag (no csc_placement) is read from its own plane
    assert all(p['passport'] is None or p['identity_id'] == UUID_I
               for p in pieces)


def test_objects_that_are_not_text_are_never_pieces(doc):
    attributes = Rhino.DocObjects.ObjectAttributes()
    attributes.SetUserString('csc_identity_id', UUID_I)
    doc.Objects.AddPoint(G.Point3d(1, 2, 3), attributes)
    assert NS['read_document'](doc) == []


# THE COMPONENTS --------------------------------------------------------------
def test_bake_and_sync_components_round_trip(doc):
    mesh = _box_mesh()
    passport = _passport(mesh=mesh)
    text = json.dumps(passport)
    session = FakeSession({UUID_I: passport})
    module, bake = _load('BakeComponents', doc, {'CSC_AuthCore': session})
    bake.RunScript(True, [text, 'not json'], 'preview', True)
    messages = compstub.messages(bake)
    assert messages['error'] == [], messages
    assert any('not component passport JSON' in w for w in messages['warning'])
    assert 'Baked 1' in bake.Component.Message
    assert len(NS['tagged_objects'](doc)) == 1
    X = _rotation(120.0, (-50.0, 75.0, 10.0))
    _move_everything(doc, X)

    module, sync = _load('SyncWithRhinoDoc', doc, {'CSC_AuthCore': session})
    tree = sync.RunScript(True)
    assert compstub.messages(sync)['error'] == []
    assert tree.DataCount == 1
    out = json.loads(tree.values[0])
    q0 = NS['canonical_placement'](passport['snapshots'][0]['frame'])
    assert np.allclose(NS['placement_matrix'](NS['placement_of'](out)),
                       _matrix(X) @ NS['placement_matrix'](q0), atol=1e-6)
    assert session.requests == []                  # no request was needed

    # off: nothing happens
    tree = sync.RunScript(False)
    assert tree.DataCount == 0


def test_bake_asks_for_levels_it_can_name_and_falls_back_without_a_session(
        doc):
    passport = _passport(mesh=_box_mesh())
    module, bake = _load('BakeComponents', doc, {})
    bake.RunScript(True, [json.dumps(passport)], 'original', True)
    messages = compstub.messages(bake)
    assert any('preview geometry is baked' in w for w in messages['warning'])
    assert len(_geometries(doc, G.Mesh)) == 1
    bake.RunScript(True, [json.dumps(passport)], 'huge', True)
    assert any('level is one of' in e
               for e in compstub.messages(bake)['error'])


def test_a_piece_without_a_frame_is_reported_and_the_rest_is_baked(doc):
    broken = _passport(mesh=_box_mesh())
    del broken['snapshots'][0]['frame']
    fine = _passport(identity_id=UUID_I2, snapshot_id=UUID_S2,
                     mesh=_box_mesh())
    module, bake = _load('BakeComponents', doc, {})
    bake.RunScript(True, [json.dumps(broken), json.dumps(fine)], 'preview',
                   False)
    messages = compstub.messages(bake)
    assert any('frame' in w for w in messages['warning'])
    assert 'Baked 1' in bake.Component.Message
    tags = NS['tagged_objects'](doc)
    assert len(tags) == 1 and tags[0]['tags']['identity_id'] == UUID_I2
    assert tags[0]['tags']['passport'] is None     # WithComponentPassport was false


# THE D2P PATH ----------------------------------------------------------------
def _d2p_pieces(doc, passports, core=None, mode='inline'):
    module, comp = _load('PassportToD2P', doc, {'CSC_AuthCore': core}
                         if core else {})
    tree = types.SimpleNamespace(
        DataCount=len(passports), BranchCount=len(passports),
        Paths=[compstub.FakePath(i) for i in range(len(passports))],
        Branches=[[json.dumps(p)] for p in passports])
    out = comp.RunScript(tree, mode, mode, 'current', None)
    return comp, out


def test_passport_to_d2p_places_the_piece_like_the_bake_and_labels_it(doc):
    mesh = _box_mesh()
    passport = _passport(mesh=mesh)
    comp, out = _d2p_pieces(doc, [passport])
    assert compstub.messages(comp)['error'] == [], compstub.messages(comp)
    assert out.DataCount == 1
    component = out.values[0]
    assert component.TypeId == 'BM'
    plane = component.Plane
    assert plane.Origin.DistanceTo(G.Point3d.Origin) < 1e-9   # canonical
    component.Commit(False)
    # the label carries the convention; every key readable by Sync
    pieces = NS['read_document'](doc)
    assert len(pieces) == 1 and pieces[0]['problems'] == []
    assert pieces[0]['identity_id'] == UUID_I
    # D2P commits the label without user text: the keys are on the members
    keyed = [o for o in doc.Objects
             if o.Attributes.GetUserString('csc_identity_id')]
    assert keyed and not any(isinstance(o.Geometry, G.TextEntity)
                             for o in keyed)
    carrier = [o for o in keyed if o.Attributes.GetUserString(
        'csc_placement')]
    assert len(carrier) == 1                 # the first object carries it all
    assert carrier[0].Attributes.GetUserString(
        'csc_original_function') == 'IfcBeam'
    assert carrier[0].Attributes.GetUserString('csc_assembly') is None
    assert carrier[0].Attributes.GetUserString('csc_component')
    baked = [o.Geometry for o in doc.Objects
             if isinstance(o.Geometry, G.Mesh)]
    assert len(baked) == 1
    b = baked[0].GetBoundingBox(True)
    assert b.Center.DistanceTo(G.Point3d.Origin) < 1e-4


def test_a_d2p_piece_is_read_by_sync_and_by_read_from_d2p_after_a_move(doc):
    mesh = _box_mesh()
    passport = _passport(mesh=mesh)
    comp, out = _d2p_pieces(doc, [passport])
    out.values[0].Commit(False)
    X = _rotation(-48.0, (300.0, 40.0, -9.0))
    _move_everything(doc, X)
    q0 = NS['canonical_placement'](passport['snapshots'][0]['frame'])
    want = _matrix(X) @ NS['placement_matrix'](q0)

    module, sync = _load('SyncWithRhinoDoc', doc, {})
    tree = sync.RunScript(True)
    assert tree.DataCount == 1
    assert np.allclose(NS['placement_matrix'](NS['placement_of'](
        json.loads(tree.values[0]))), want, atol=1e-6)

    session = FakeSession()
    module, read = _load('ReadFromD2P', doc, {'CSC_AuthCore': session})
    data, components = read.RunScript(True)
    assert compstub.messages(read)['error'] == [], compstub.messages(read)
    assert data.DataCount == 1
    assert np.allclose(NS['placement_matrix'](NS['placement_of'](
        json.loads(data.values[0]))), want, atol=1e-6)
    # it is a D2P component the library recognised
    assert components.values[0] is not None
    assert components.values[0].TypeId == 'BM'
    assert session.requests == []

    # the placement drives the geometry as in the bake
    again = json.loads(data.values[0])
    stored = mesh.DuplicateMesh()
    stored.Transform(NS['placement_transform'](NS['placement_of'](again)))
    v_stored, _, _ = NS['mesh_arrays'](stored)
    baked = [o.Geometry for o in doc.Objects
             if isinstance(o.Geometry, G.Mesh)][0]
    v_baked, _, _ = NS['mesh_arrays'](baked)
    assert np.allclose(v_stored, v_baked, atol=1e-3)


def test_a_built_in_bake_is_read_by_read_from_d2p_as_a_plain_tag(doc):
    mesh = _box_mesh()
    passport = _passport(mesh=mesh)
    _bake(doc, passport)
    X = _rotation(15.0, (10.0, 20.0, 30.0))
    _move_everything(doc, X)
    module, read = _load('ReadFromD2P', doc, {})
    data, components = read.RunScript(True)
    assert data.DataCount == 1
    q0 = NS['canonical_placement'](passport['snapshots'][0]['frame'])
    assert np.allclose(
        NS['placement_matrix'](NS['placement_of'](json.loads(
            data.values[0]))), _matrix(X) @ NS['placement_matrix'](q0),
        atol=1e-6)
    assert components.values[0] is None      # not a D2P component


def test_passport_to_d2p_authored_piece_and_markers(doc):
    proxy = _box_proxy()
    passport = _passport(proxies=[proxy], capture={
        'method': 'lidar', 'markers': [
            {'label': 'rig1', 'role': 'rig', 'point': [300, -100, 40]}]})
    comp, out = _d2p_pieces(doc, [passport])
    assert compstub.messages(comp)['error'] == []
    out.values[0].Commit(False)
    assert len(_geometries(doc, G.Brep)) == 1
    assert len(_geometries(doc, G.Point)) == 1       # the capture marker


def test_passport_to_d2p_refuses_a_piece_without_a_frame(doc):
    broken = _passport(mesh=_box_mesh())
    del broken['snapshots'][0]['frame']
    comp, out = _d2p_pieces(doc, [broken])
    assert out.DataCount == 0
    assert any('frame' in e for e in compstub.messages(comp)['error'])


@pytest.mark.parametrize('function,type_id', [
    ('IfcColumn', 'CL'), ('IfcSlab', 'SB'), ('CscDebris', 'RB'),
    (None, 'OT')])
def test_the_d2p_type_follows_the_original_function(doc, function, type_id):
    passport = _passport(mesh=_box_mesh())
    passport['identity']['original_function'] = function
    comp, out = _d2p_pieces(doc, [passport])
    assert out.values[0].TypeId == type_id
