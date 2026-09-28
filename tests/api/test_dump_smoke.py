"""
The app serves a real catalog dump (opt-in).

Set CSC_DUMP_DIR to a local export folder, e.g.
``mongodb_collections_local/260916``. The dumps are not in the repository.
"""

import os
import random

import pytest

from support import load_dump

DUMP_DIR = os.getenv('CSC_DUMP_DIR')
pytestmark = pytest.mark.skipif(
    not DUMP_DIR, reason='set CSC_DUMP_DIR to run against a local dump')


def test_real_catalog_lists_and_composes(api, db, auth_headers):
    counts = load_dump(db, DUMP_DIR)
    identities = counts['component_identities']
    admin = auth_headers('admin')

    listed = api.get('/identities', headers=admin, params={
        'validated': 0, 'consumed_filter': 'all', 'expand': 'shallow'})
    assert listed.status_code == 200, listed.text[:500]
    body = listed.json()
    rows = body if isinstance(body, list) else body.get('items', [])
    assert len(rows) == identities

    ids = [d['_id'] for d in db['component_identities'].find({}, {'_id': 1})]
    for identity_id in random.Random(0).sample(ids, min(25, len(ids))):
        response = api.get(f'/identities/{identity_id}/compose', headers=admin)
        assert response.status_code == 200, (identity_id, response.text[:300])
