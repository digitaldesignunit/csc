"""
What the web form needs of the backend (P6 part 2, decisions 8.82, 8.83):
"repeat from my last record" in one request (``recorded_by=me``,
``order``, ``limit`` on ``GET /evidence``) and the fixed 25 MB cap of an
evidence file, checked on the bytes received.
"""

from __future__ import annotations

from evidence_samples import PDF, rebound_body, claim_body
from test_evidence_routes import (  # noqa: F401  (world is a fixture)
    BEAM,
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
