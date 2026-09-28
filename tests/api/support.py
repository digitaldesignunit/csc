"""Constants and payload builders shared by the route tests."""

TEST_CLIENT_HEADER = 'test-suite/0.0.0'
DEFAULT_PASSWORD = 'correct horse battery'


def identity_frame():
    return {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]}


def panel_payload(**overrides):
    """A 400 × 200 × 12 mm panel as the 0.5 web wizard would create it."""
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
