"""
What the web form needs of the backend (P6 part 2, decisions 8.82, 8.83):
"repeat from my last record" in one request (``recorded_by=me``,
``order``, ``limit`` on ``GET /evidence``) and the fixed 25 MB cap of an
evidence file, checked on the bytes received.
"""

from __future__ import annotations

from evidence_samples import PDF, rebound_body, claim_body
from support import sid
from test_evidence_routes import (  # noqa: F401  (world is a fixture)
    BEAM,
    create,
    made,
    world,
)


def stamp(w, eid, created):
    w['db']['component_evidence'].update_one(
        {'_id': eid}, {'$set': {'created': created}})


def test_my_newest_record_of_a_method_in_one_request(world):
    w = world
    api = w['api']
    first = made(w, rebound_body())
    second = made(w, rebound_body())
    theirs = made(w, rebound_body(), headers=w['c2'])
    other_method = made(w, claim_body())
    stamp(w, first['_id'], '2026-06-01T10:00:00Z')
    stamp(w, second['_id'], '2026-06-03T10:00:00Z')
    stamp(w, theirs['_id'], '2026-06-05T10:00:00Z')
    stamp(w, other_method['_id'], '2026-06-07T10:00:00Z')
    params = {'dataset': 'dbu_zirkus', 'method': 'rebound_hammer',
              'status': 'all', 'recorded_by': 'me', 'order': 'newest',
              'limit': 1}
    rows = api.get('/evidence', params=params, headers=w['c']).json()
    assert [r['_id'] for r in rows] == [second['_id']]
    # the other contributor's newest is theirs
    rows = api.get('/evidence', params=params, headers=w['c2']).json()
    assert [r['_id'] for r in rows] == [theirs['_id']]
    # oldest first, all of mine
    rows = api.get('/evidence', params={**params, 'order': 'oldest',
                                        'limit': 10},
                   headers=w['c']).json()
    assert [r['_id'] for r in rows] == [first['_id'], second['_id']]
    # without recorded_by the others' records are in
    everyone = api.get('/evidence', params={
        'dataset': 'dbu_zirkus', 'method': 'rebound_hammer',
        'status': 'all', 'order': 'newest'}, headers=w['m']).json()
    assert [r['_id'] for r in everyone][0] == theirs['_id']


def test_recorded_by_needs_a_login_and_only_means_me(world):
    w = world
    api = w['api']
    assert api.get('/evidence', params={'recorded_by': 'me'}).status_code \
        == 401
    assert api.get('/evidence', params={'recorded_by': 'someone-else'},
                   headers=w['c']).status_code == 422
    assert api.get('/evidence', params={'order': 'sideways'},
                   headers=w['c']).status_code == 422


def test_the_default_order_is_unchanged(world):
    w = world
    api = w['api']
    late = made(w, rebound_body(observed_at='2026-06-02T09:00:00Z'))
    early = made(w, rebound_body(observed_at='2026-06-01T09:00:00Z'))
    rows = api.get('/evidence', params={'status': 'all',
                                        'method': 'rebound_hammer'},
                   headers=w['c']).json()
    assert [r['_id'] for r in rows] == [early['_id'], late['_id']]


def test_an_evidence_file_is_capped_at_25_mb_on_the_bytes_received(world):
    w = world
    api = w['api']
    limit = 25 * 1024 * 1024
    assert api.app.evidence_upload_limit_bytes == limit
    record = made(w, claim_body())
    eid = record['_id']
    too_big = PDF + b'0' * (limit - len(PDF) + 1)
    assert len(too_big) == limit + 1
    response = api.post(
        '/evidence/attachments', data={'record_ids': [eid]},
        files={'file': ('big.pdf', too_big, 'application/pdf')},
        headers=w['c'])
    assert response.status_code == 413, response.text[:200]
    assert '25 MB' in response.text
    stored = w['db']['component_evidence'].find_one({'_id': eid})
    assert stored['attachments'] == []


def grid_body(kind=None, rows=3, cols=3, readings=None, **position):
    """A rebound test area laid as a grid on a face (A.1, decision 8.43)."""
    body = rebound_body(readings=readings or [44, 42, 41, 45, 43, 42, 40,
                                              44, 43][:rows * cols])
    body['payload']['test_area']['grid'] = {
        'origin': [100.0, 50.0, 25.0], 'u': [1, 0, 0], 'v': [0, 1, 0],
        'rows': rows, 'cols': cols, 'spacing_mm': 50}
    body['position'] = {'snapshot_id': sid('beam', 1),
                        **({'kind': kind} if kind else {}), **position}
    return body


def test_a_grid_is_saved_with_its_points_and_a_region_at_its_centre(world):
    """What the form sends for a grid laid on a picked face: the position is
    a region on the snapshot; the server derives the points and the centre."""
    record = made(world, grid_body(kind='region',
                                   description='north face'))
    grid = record['payload']['test_area']['grid']
    assert len(grid['points']) == 9
    assert grid['points'][0] == [100.0, 50.0, 25.0]
    assert grid['points'][-1] == [200.0, 150.0, 25.0]
    assert record['position']['kind'] == 'region'
    assert record['position']['snapshot_id'] == sid('beam', 1)
    assert record['position']['point'] == [150.0, 100.0, 25.0]
    again = world['api'].get(f'/evidence/{record["_id"]}',
                             headers=world['c']).json()
    assert again['payload']['test_area']['grid']['points'] == grid['points']


def test_a_grid_is_never_a_point_or_a_position_none(world):
    """The refusal a hand-written request got (G2): the 422 names the field."""
    for kind, where in (('none', 'position.kind'),
                        ('point', 'position.kind')):
        response = create(world, grid_body(kind=kind))
        assert response.status_code == 422, kind
        paths = [e['path'] for e in response.json()['detail']['errors']]
        assert where in paths, (kind, paths)
    # a grid needs the snapshot it is laid on
    body = grid_body(kind='region')
    del body['position']['snapshot_id']
    response = create(world, body)
    assert response.status_code == 422
    assert 'position.snapshot_id' in [
        e['path'] for e in response.json()['detail']['errors']]


def test_a_grid_needs_a_reading_per_point_and_unit_directions(world):
    response = create(world, grid_body(kind='region', rows=3, cols=3,
                                       readings=[44, 42, 41, 45, 43, 42]))
    assert response.status_code == 422
    assert 'payload.test_area.grid' in [
        e['path'] for e in response.json()['detail']['errors']]
    body = grid_body(kind='region')
    body['payload']['test_area']['grid']['u'] = [2, 0, 0]
    response = create(world, body)
    assert response.status_code == 422
    assert 'payload.test_area.grid.u' in [
        e['path'] for e in response.json()['detail']['errors']]
