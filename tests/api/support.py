"""Constants and payload builders shared by the route tests."""

TEST_CLIENT_HEADER = 'test-suite/0.0.0'
DEFAULT_PASSWORD = 'correct horse battery'


def identity_frame():
    return {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]}


def panel_payload(**overrides):
    """A 400 x 200 x 12 mm panel as the 0.5 web wizard would create it."""
    payload = {
        'type': 'panel',
        'material': 'corian',
        'dataset': 'test_dataset',
        'complexity': 1,
        'fragment': False,
        'assembly': False,
        'geometry': {'extrusions': [{
            'profile': [[-200, -100], [200, -100], [200, 100], [-200, 100]],
            'height': 12,
        }]},
        'bbx': [400, 200, 12],
        'bbx_origin': [0, 0, 0],
        'iframe': identity_frame(),
        'pca_frame': identity_frame(),
    }
    payload.update(overrides)
    return payload


# LOCAL DUMPS -----------------------------------------------------------------
# Folders like mongodb_collections_local/260916 hold Compass JSON exports named
# csc.<collection>.json. Used by the dump smoke test and `invoke seed`.

def dump_files(dump_dir):
    """Map collection name -> file path for every export in *dump_dir*."""
    import os
    files = {}
    for name in sorted(os.listdir(dump_dir)):
        if name.startswith('csc.') and name.endswith('.json'):
            files[name[len('csc.'):-len('.json')]] = os.path.join(dump_dir, name)
    return files


def load_dump(database, dump_dir, replace=False):
    """Insert every exported collection; returns {collection: count}."""
    from bson import json_util
    counts = {}
    for collection, path in dump_files(dump_dir).items():
        with open(path, encoding='utf-8') as handle:
            docs = json_util.loads(handle.read())
        if replace:
            database[collection].delete_many({})
        if docs:
            database[collection].insert_many(docs, ordered=False)
        counts[collection] = len(docs)
    return counts


# A SMALL 0.5 CATALOG ---------------------------------------------------------
# The shapes of dump 260916, one piece per migration case: a Corian panel cut
# into a child and a grandchild, a robot-scanned stone with rig markers and
# the gripper mesh, a ZirKuS beam with a reinforced v1, two graded pieces.

ROSSKOPF = 'Rosskopf + Partner AG, Bahnhofstra\u00dfe 16, 09573 Augustusburg'
T_CUT = '2026-04-29T09:41:30.620849Z'
FRAME = {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]}
PIECES = ('panel', 'cut', 'cut2', 'stone', 'beam', 'feld')


def iid(name):
    """The identity UUID of a seeded piece (routes accept UUIDs only)."""
    import uuid
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'csc-test/{name}'))


def sid(name, version=0):
    """The snapshot UUID of a seeded piece's version."""
    import uuid
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'csc-test/{name}/v{version}'))


def _identity(name, dataset, type_, current=0, parents=None, **fields):
    doc = {'_id': iid(name), 'catalog_number': PIECES.index(name) + 1,
           'type': type_, 'material': 'concrete', 'dataset': dataset,
           'manufactured_at': None, 'manufactured_precision': 'unknown',
           'salvage_source': None, 'salvaged_at': None, 'reserved': '',
           'attributes': {},
           'parent_identities': [iid(p) for p in parents] if parents else None,
           'consumed_at': None, 'current_snapshot_id': sid(name, current),
           'created': '2026-01-01T00:00:00Z',
           'lastmodified': '2026-01-01T00:00:00Z', 'is_public': False}
    doc.update(fields)
    return doc


def _snapshot(name, version=0, geometry=None, **fields):
    doc = {'_id': sid(name, version), 'identity_id': iid(name),
           'version': version, 'virtual': False, 'name': name,
           'geometry': geometry or {'extrusions': [{
               'profile': [[-10, -5], [10, -5], [10, 5], [-10, 5]], 'height': 2}]},
           'descriptors': {}, 'bbx': [20, 10, 2], 'bbx_origin': [0, 0, 0],
           'complexity': 1, 'fragment': False, 'assembly': False, 'condition': 2,
           'color': [128, 128, 128], 'location': {'lat': 49.87, 'lon': 8.65},
           'processes': {}, 'iframe': FRAME, 'pca_frame': FRAME, 'validated': True,
           'created': '2026-01-01T00:00:00Z', 'lastmodified': '2026-01-01T00:00:00Z',
           'etag': 'x', 'added_by_user_id': 'u-ddu', 'added_by_username': 'ddu',
           'quantity': 1}
    doc.update(fields)
    return doc


def _mesh(radius, z0, z1):
    vertices = [[-radius, 0, z0], [radius, 0, z0], [0, radius, z1], [0, -radius, z1]]
    return {'vertices': vertices, 'faces': [[0, 1, 2], [0, 2, 3], [1, 2, 3],
                                            [0, 1, 3]], 'colors': None}


def seed_05_catalog(db):
    """A small 0.5 catalog covering every 0.6 migration case (see
    test_migration06_steps); users admin / ddu / alice. Ids: iid() / sid()."""
    db['users'].insert_many([
        {'_id': f'u-{name}', 'username': name, 'email': f'{name}@example.org',
         'role': role, 'disabled': False}
        for name, role in (('admin', 'admin'), ('ddu', 'user'), ('alice', 'user'))
    ])
    rosskopf = {'salvage_source': ROSSKOPF,
                'salvaged_at': '2022-10-26T00:00:00.000000Z', 'material': 'corian'}
    db['component_identities'].insert_many([
        _identity('panel', 'mineral_composite_panels', 'panel', consumed_at=T_CUT,
                  **rosskopf),
        _identity('cut', 'ddu_aggregations', 'panel', parents=['panel'],
                  manufactured_at=T_CUT, manufactured_precision='exact',
                  consumed_at='2026-05-01T10:00:00Z', **rosskopf),
        _identity('cut2', 'ddu_aggregations', 'panel', material='corian',
                  parents=['cut'], manufactured_at='2026-05-01T10:00:00Z',
                  manufactured_precision='exact'),
        _identity('stone', 'ddu_build_with_debris', 'rubble',
                  consumed_at='2026-03-01T12:00:00Z',
                  attributes={'3d_scan_metadata': {
                      'created_utc': '2025-10-30T00:26:28.345536Z',
                      'run_dir': 'C:\\Users\\x'}}),
        _identity('beam', 'dbu_zirkus', 'beam', current=1),
        _identity('feld', 'schoenes_neues_feld', 'other', current=1,
                  material='wood',
                  salvage_source='ExFeld Architektur, TU Darmstadt',
                  salvaged_at='2026-05-19T00:00:00Z'),
    ])
    stone_geometry = {
        'meshes': [_mesh(60, 250, 400), _mesh(150, -60, 240)],
        'marker_points': [[-120, 0.6, -0.5], [120, 0.6, -0.5], [0, 120, 0.3],
                          [0, -120, 0.1], [10, 20, 380]],
        'point_clouds': None, 'reinforcements': None,
    }
    db['component_snapshots'].insert_many([
        _snapshot('panel'),
        _snapshot('cut', created=T_CUT),
        _snapshot('cut2', created='2026-05-01T10:00:00Z'),
        _snapshot('stone', geometry=stone_geometry, complexity=2,
                  created='2025-11-02T09:00:00Z',
                  mesh_ply_resolutions={'0': ['reduced', 'detailed'],
                                        '1': ['reduced', 'detailed']}),
        _snapshot('beam', geometry={'meshes': [_mesh(3000, 0, 300)]},
                  created='2026-06-15T15:23:01Z'),
        _snapshot('beam', 1, geometry={
            'meshes': [_mesh(3000, 0, 300)],
            'reinforcements': [{'spec': 'BSt III', 'diameter': 8,
                                'points': [[0, 0, 20], [6000, 0, 20]]}]},
            created='2026-06-15T15:27:38Z'),
        _snapshot('feld', created='2026-05-19T14:56:28Z', condition=1),
        _snapshot('feld', 1, created='2026-06-09T07:21:10Z', condition=2),
    ])
