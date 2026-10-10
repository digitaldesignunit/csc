"""The ``derivation_due`` marker and the batched geometry runner (decision
8.136): every write that changes a stage input marks the snapshot; the
frequent run (``--due``) reads only the marked ones and clears the marker only
if it still holds the value it read; a full run still finds a stale snapshot
nobody marked."""

from __future__ import annotations

import asyncio

import pytest
import trimesh

from apps.catalog.geometry_runner import DUE_FIELD, settle_due
from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import iid, seed_05_catalog, sid

BEAM = iid('beam')
V1 = sid('beam', 1)


@pytest.fixture
def story(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    contributor, _ = member_headers({'dbu_zirkus': ['contributor']})
    moderator, _ = member_headers({'dbu_zirkus': ['moderator']})
    return {'api': api, 'db': db, 'c': contributor, 'm': moderator,
            'admin': auth_headers('admin')}


def block(sx=300, sy=200, sz=150):
    mesh = trimesh.creation.box(extents=(sx, sy, sz))
    return {'meshes': [{'vertices': mesh.vertices.tolist(),
                        'faces': mesh.faces.tolist()}],
            'point_clouds': [], 'proxies': []}


def marker(story, snapshot_id):
    return story['db']['component_snapshots'].find_one(
        {'_id': snapshot_id}).get(DUE_FIELD)


def clear_markers(story):
    story['db']['component_snapshots'].update_many(
        {}, {'$unset': {DUE_FIELD: ''}})


def draft(story):
    response = story['api'].post(f'/identities/{BEAM}/snapshots',
                                 json={'geometry': block()}, headers=story['c'])
    assert response.status_code == 201, response.text
    return response.json()


# EVERY WRITE PATH SETS THE MARKER --------------------------------------------
def test_a_new_version_is_marked(story):
    created = draft(story)
    assert created[DUE_FIELD]                      # in the stored document
    assert marker(story, created['_id'])


def test_a_correction_is_marked(story):
    response = story['api'].post(
        f'/snapshots/{V1}/supersede', json={'geometry': block(310)},
        headers=story['c'])
    assert response.status_code == 201, response.text
    assert marker(story, response.json()['_id'])


def test_a_new_component_is_marked(story):
    body = {'dataset': 'dbu_zirkus', 'original_function': 'IfcBeam',
            'material': 'concrete', 'origin': {'kind': 'unknown'},
            'snapshot': {'geometry': block()}}
    response = story['api'].post('/identities', json=body, headers=story['c'])
    assert response.status_code == 201, response.text
    assert marker(story, response.json()['snapshot']['_id'])


def test_a_file_upload_and_its_removal_mark_the_snapshot(story):
    created = draft(story)
    clear_markers(story)
    mesh = trimesh.creation.box(extents=(300, 200, 150))
    put = story['api'].put(
        f'/snapshots/{created["_id"]}/meshes/0/reduced',
        files={'mesh_file': ('reduced.ply', mesh.export(file_type='ply'),
                             'application/octet-stream')},
        headers=story['c'])
    assert put.status_code in (200, 201), put.text
    assert marker(story, created['_id'])
    clear_markers(story)
    gone = story['api'].delete(f'/snapshots/{created["_id"]}/meshes/0/reduced',
                               headers=story['c'])
    assert gone.status_code in (200, 204), gone.text
    assert marker(story, created['_id'])


@pytest.mark.parametrize('patch', [
    {'color': [10, 20, 30]},                         # the previews read it
    {'geometry': block(320)},                        # every stage
    {'shape_class': 'planar'},                       # override
    {'complexity': 2},                               # override
])
def test_a_patch_of_a_stage_input_marks_the_snapshot(story, patch):
    created = draft(story)
    clear_markers(story)
    got = story['api'].patch(f'/snapshots/{created["_id"]}', json=patch,
                             headers=story['c'])
    assert got.status_code == 200, got.text
    assert marker(story, created['_id'])


def test_a_patch_of_something_else_does_not_mark(story):
    created = draft(story)
    clear_markers(story)
    got = story['api'].patch(f'/snapshots/{created["_id"]}',
                             json={'notes': 'hello'}, headers=story['c'])
    assert got.status_code == 200
    assert marker(story, created['_id']) is None


def test_the_function_of_the_piece_marks_all_its_snapshots(story):
    clear_markers(story)
    got = story['api'].patch(f'/identities/{BEAM}',
                             json={'original_function': 'IfcColumn'},
                             headers=story['m'])
    assert got.status_code == 200, got.text
    snapshots = story['db']['component_snapshots']
    assert snapshots.count_documents({'identity_id': BEAM}) >= 1
    assert snapshots.count_documents(
        {'identity_id': BEAM, DUE_FIELD: {'$type': 'string'}}) == \
        snapshots.count_documents({'identity_id': BEAM})
    clear_markers(story)
    story['api'].patch(f'/identities/{BEAM}', json={'trade_name': 'x'},
                       headers=story['m'])                # not an input
    assert snapshots.count_documents({DUE_FIELD: {'$type': 'string'}}) == 0


def test_a_client_cannot_set_the_marker(story):
    created = draft(story)
    got = story['api'].patch(f'/snapshots/{created["_id"]}',
                             json={DUE_FIELD: '2026-01-01T00:00:00Z'},
                             headers=story['c'])
    assert got.status_code == 422


def test_the_marker_is_not_part_of_the_etag():
    from apps.catalog.etag import compute_snapshot_etag
    doc = {'_id': 'a', 'name': 'x'}
    assert compute_snapshot_etag({**doc, DUE_FIELD: '2026-10-10T00:00:00Z'}) \
        == compute_snapshot_etag(doc)


# CLEARING -------------------------------------------------------------------
def test_clearing_keeps_a_marker_a_write_set_meanwhile(story):
    snapshots = story['db']['component_snapshots']
    snapshots.update_one({'_id': V1}, {'$set': {DUE_FIELD: '2026-10-10T08:00:00Z'}})
    read = snapshots.find_one({'_id': V1})                     # the runner's read
    snapshots.update_one({'_id': V1}, {'$set': {DUE_FIELD: '2026-10-10T08:05:00Z'}})

    async def settle():
        from pymongo import AsyncMongoClient
        import os
        client = AsyncMongoClient(os.environ['MONGODB_URI'])
        try:
            col = client[os.environ['MONGODB_DB']]['component_snapshots']
            await settle_due(col, read, errors=False)
        finally:
            await client.close()

    asyncio.run(settle())
    assert marker(story, V1) == '2026-10-10T08:05:00Z'        # kept
    read = snapshots.find_one({'_id': V1})
    asyncio.run(settle())
    assert marker(story, V1) is None                          # cleared when unchanged


# THE RUNNER ------------------------------------------------------------------
def _run(argv):
    import main_geometry
    return asyncio.run(main_geometry.run(main_geometry._parse_args(argv)))


def test_due_reads_only_marked_snapshots_and_clears_them(story):
    created = draft(story)                      # marked, frame / class derived
    other = story['db']['component_snapshots'].find_one({'_id': V1})
    # an unmarked snapshot whose derivation is stale: no stamps at all
    story['db']['component_snapshots'].update_one(
        {'_id': V1}, {'$unset': {'derivation': '', DUE_FIELD: ''}})
    assert marker(story, V1) is None and other is not None
    assert marker(story, created['_id'])
    code = _run(['--due', '--limit', '10', '--stages', 'frame,shape_class'])
    assert code in (0, 1)
    # the marked one was looked at and its marker cleared (all server stages
    # were not asked for, so with --stages it is kept: see below)
    assert marker(story, created['_id'])
    v1 = story['db']['component_snapshots'].find_one({'_id': V1})
    assert not v1.get('derivation')              # --due never looked at it


def test_due_with_all_stages_clears_the_marker_and_leaves_the_rest(story):
    created = draft(story)
    story['db']['component_snapshots'].update_one(
        {'_id': V1}, {'$unset': {'derivation': ''}})
    _run(['--due', '--limit', '10'])
    assert marker(story, created['_id']) is None
    assert not story['db']['component_snapshots'].find_one(
        {'_id': V1}).get('derivation')            # unmarked: not looked at


def test_a_full_run_still_finds_a_stale_snapshot_nobody_marked(story):
    story['db']['component_snapshots'].update_one(
        {'_id': V1}, {'$unset': {'derivation': '', DUE_FIELD: ''}})
    _run(['--limit', '50', '--stages', 'frame,shape_class'])
    assert story['db']['component_snapshots'].find_one(
        {'_id': V1}).get('derivation')            # the nightly safety net


def test_a_run_with_errors_keeps_the_marker_but_moves_it_to_the_back(story):
    snapshots = story['db']['component_snapshots']
    snapshots.update_one({'_id': V1}, {'$set': {DUE_FIELD: '2026-10-10T08:00:00Z'}})
    read = snapshots.find_one({'_id': V1})

    async def settle():
        import os
        from pymongo import AsyncMongoClient
        client = AsyncMongoClient(os.environ['MONGODB_URI'])
        try:
            col = client[os.environ['MONGODB_DB']]['component_snapshots']
            await settle_due(col, read, errors=True)
        finally:
            await client.close()

    asyncio.run(settle())
    later = marker(story, V1)
    assert later and later > '2026-10-10T08:00:00Z'      # kept, newer: last in line
