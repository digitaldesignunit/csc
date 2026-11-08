"""
Two booleans tell the web that something is open (decision 8.195, #47):
``has_open_snapshot`` on the identity payload and ``has_open_correction`` on an
evidence record. A draft or pending version is visible only to its author and
the moderators, so a contributor cannot see from the rows that another
person's version is open; the flag gives the fact and nothing else, to the
contributors and moderators of the dataset and admins. Everyone else, a member
who only reviews included, gets a constant False. The
ETag follows the flag, and the exports do not carry either field.
"""

from __future__ import annotations

import pytest

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from evidence_samples import claim_body
from support import iid, seed_05_catalog, sid

BEAM = iid('beam')
OPEN_VERSION = sid('beam', 2)


@pytest.fixture
def world(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    author, author_id = member_headers({'dbu_zirkus': ['contributor']})
    other, _ = member_headers({'dbu_zirkus': ['contributor']})
    reviewer, _ = member_headers({'dbu_zirkus': ['reviewer']})
    moderator, _ = member_headers({'dbu_zirkus': ['moderator']})
    elsewhere, _ = member_headers({'ddu_aggregations': ['moderator']})
    return {'api': api, 'db': db, 'author': author, 'author_id': author_id,
            'other': other, 'reviewer': reviewer, 'moderator': moderator,
            'elsewhere': elsewhere, 'admin': auth_headers('admin'),
            'user': auth_headers('user')}


MEMBERS = ('author', 'other', 'moderator', 'admin')     # told
NOT_MEMBERS = ('reviewer', 'elsewhere', 'user')           # not told


def _open_snapshot(w, status='draft'):
    snapshot = w['db']['component_snapshots'].find_one({'_id': sid('beam', 1)})
    snapshot.update({'_id': OPEN_VERSION, 'version': 2, 'status': status,
                     'superseded_by': None, 'supersedes': None,
                     'added_by_user_id': w['author_id']})
    w['db']['component_snapshots'].insert_one(snapshot)


def _public(w):
    """The element public, so that callers outside the dataset read it too."""
    w['db']['component_identities'].update_one({'_id': BEAM}, {'$set': {
        'is_public': True}})


def _flag(w, who, route='compose'):
    headers = {} if who is None else w[who]
    url = f'/identities/{BEAM}/compose' if route == 'compose' \
        else f'/identities/{BEAM}'
    params = {} if route == 'compose' else {'expand': 'none'}
    response = w['api'].get(url, params=params, headers=headers)
    assert response.status_code == 200, (who, response.text)
    body = response.json()
    return (body['identity'] if route == 'compose' else body)[
        'has_open_snapshot']


# HAS_OPEN_VERSION ------------------------------------------------------------
@pytest.mark.parametrize('route', ['compose', 'none'])
@pytest.mark.parametrize('status', ['draft', 'pending'])
def test_the_members_and_admins_are_told_of_an_open_snapshot(
        world, route, status):
    w = world
    _public(w)
    for who in (*MEMBERS, *NOT_MEMBERS, None):
        assert _flag(w, who, route) is False, who
    _open_snapshot(w, status)
    for who in MEMBERS:
        assert _flag(w, who, route) is True, who
    # nobody else, an anonymous caller included: a constant False
    for who in (*NOT_MEMBERS, None):
        assert _flag(w, who, route) is False, who


def test_a_closed_version_is_not_open(world):
    w = world
    for status in ('published', 'rejected', 'withdrawn'):
        w['db']['component_snapshots'].delete_many({'_id': OPEN_VERSION})
        _open_snapshot(w, status)
        assert _flag(w, 'author') is False, status


def test_a_non_member_costs_no_query():
    """The gate answers before it touches the database: a database that
    refuses every call is not asked for an anonymous caller, a signed-in
    stranger or a moderator of another dataset."""
    import asyncio
    from types import SimpleNamespace

    from apps.catalog.api.access import (
        has_open_snapshot, may_know_open)
    from apps.catalog.documents import Dataset
    from apps.catalog.permissions import ANONYMOUS, Viewer

    dataset = Dataset.model_validate({
        '_id': 'ds', 'name': 'ds', 'visibility': 'members',
        'members': [{'user_id': 'm', 'roles': ['reviewer']}],
        'created': '1970-01-01T00:00:00Z',
        'lastmodified': '1970-01-01T00:00:00Z'})

    class Refusing:
        async def find_one(self, *args, **kwargs):
            raise AssertionError('the database was asked')

    request = SimpleNamespace(
        state=SimpleNamespace(csc_datasets={'ds': dataset}),
        app=SimpleNamespace(mongodb_component_snapshots=Refusing()))
    identity = {'_id': 'x', 'dataset': 'ds'}
    for viewer in (ANONYMOUS, Viewer('stranger', 'user')):
        assert asyncio.run(has_open_snapshot(request, viewer, identity)) is False
    assert may_know_open(Viewer('m', 'user'), dataset) is False    # a reviewer only
    dataset.members[0].roles = ['reviewer', 'contributor']
    assert may_know_open(Viewer('m', 'user'), dataset) is True
    dataset.members[0].roles = ['moderator']
    assert may_know_open(Viewer('m', 'user'), dataset) is True
    assert may_know_open(Viewer('a', 'admin'), dataset) is True
    assert may_know_open(Viewer('stranger', 'user'), dataset) is False
    assert may_know_open(ANONYMOUS, dataset) is False


def test_the_etag_follows_the_flag(world):
    w, api = world, world['api']
    first = api.get(f'/identities/{BEAM}/compose', headers=w['other'])
    etag = first.headers['etag']
    assert first.json()['identity']['has_open_snapshot'] is False
    same = api.get(f'/identities/{BEAM}/compose',
                   headers={**w['other'], 'If-None-Match': etag})
    assert same.status_code == 304
    # someone else's draft changes neither the identity nor the versions shown
    _open_snapshot(w)
    again = api.get(f'/identities/{BEAM}/compose',
                    headers={**w['other'], 'If-None-Match': etag})
    assert again.status_code == 200
    assert again.json()['identity']['has_open_snapshot'] is True
    assert again.headers['etag'] != etag
    # and back: the draft leaves, the old validator does not give True
    w['db']['component_snapshots'].delete_one({'_id': OPEN_VERSION})
    gone = api.get(f'/identities/{BEAM}/compose',
                   headers={**w['other'], 'If-None-Match': again.headers['etag']})
    assert gone.status_code == 200
    assert gone.json()['identity']['has_open_snapshot'] is False


def test_the_flag_is_not_in_the_exports(world):
    w, api = world, world['api']
    _open_snapshot(w)
    for params in ({'format': 'jsonld'},):
        text = api.get(f'/identities/{BEAM}/compose', params=params,
                       headers=w['moderator']).text
        assert 'has_open_snapshot' not in text
    for params in ({}, {'format': 'jsonld'}):
        response = api.get(f'/identities/{BEAM}/export/cero', params=params,
                           headers=w['moderator'])
        assert response.status_code == 200, response.text
        assert 'has_open_snapshot' not in response.text
    # the plain compose body carries it
    assert _flag(w, 'moderator') is True


# HAS_OPEN_CORRECTION ---------------------------------------------------------
def _published_record(w):
    api = w['api']
    created = api.post(f'/identities/{BEAM}/evidence', json=claim_body(),
                       headers=w['author'])
    assert created.status_code == 201, created.text
    eid = created.json()['_id']
    assert api.post(f'/evidence/{eid}/submit',
                    headers=w['author']).status_code == 200
    assert api.post(f'/evidence/{eid}/publish',
                    headers=w['moderator']).status_code == 200
    return eid


def _correct(w, eid, submit=True):
    made = w['api'].post(f'/evidence/{eid}/supersede', json=claim_body(),
                         headers=w['author'])
    assert made.status_code == 201, made.text
    return made.json()['_id']


def _listed(w, who):
    headers = {} if who is None else w[who]
    response = w['api'].get(f'/identities/{BEAM}/evidence',
                            params={'status': 'all'}, headers=headers)
    assert response.status_code == 200, (who, response.text)
    return {row['_id']: row.get('has_open_correction')
            for row in response.json() if 'method' in row}


def test_members_are_told_of_an_open_correction_nobody_else(world):
    w = world
    _public(w)
    old = _published_record(w)
    for who in (*MEMBERS, *NOT_MEMBERS, None):
        assert _listed(w, who).get(old) is False, who
    new = _correct(w, old)
    for who in MEMBERS:
        rows = _listed(w, who)
        assert rows[old] is True, who
        # a pending correction is seen by its author and the moderators
        assert rows.get(new, False) is False, who
        assert (new in rows) == (who in ('author', 'moderator', 'admin')), who
    # a draft or pending record is not shown to the others at all; the
    # published one carries a constant False
    for who in (*NOT_MEMBERS, None):
        assert _listed(w, who)[old] is False, who
    # the single record agrees
    for who in MEMBERS:
        got = w['api'].get(f'/evidence/{old}', headers=w[who])
        assert got.json()['has_open_correction'] is True, who
    for who in NOT_MEMBERS:
        got = w['api'].get(f'/evidence/{old}', headers=w[who])
        assert got.json()['has_open_correction'] is False, who
    assert w['api'].get(f'/evidence/{old}').json()[
        'has_open_correction'] is False


def test_a_closed_correction_is_not_open(world):
    w = world
    old = _published_record(w)
    new = _correct(w, old)
    assert _listed(w, 'other')[old] is True
    w['api'].post(f'/evidence/{new}/reject', json={'reason': 'x'},
                  headers=w['moderator'])
    assert _listed(w, 'other')[old] is False


def test_the_list_asks_once(world, monkeypatch):
    w = world
    old = _published_record(w)
    other = _published_record(w)
    _correct(w, old)
    from apps.catalog.api import evidence as route
    calls = []
    original = route.open_corrections

    async def counting(*args, **kwargs):
        calls.append(1)
        return await original(*args, **kwargs)
    monkeypatch.setattr(route, 'open_corrections', counting)
    rows = _listed(w, 'other')
    assert rows[old] is True and rows[other] is False
    assert len(calls) == 1


def test_the_record_etag_follows_the_flag(world):
    w, api = world, world['api']
    old = _published_record(w)
    first = api.get(f'/evidence/{old}', headers=w['other'])
    etag = first.headers['etag']
    assert first.json()['has_open_correction'] is False
    assert api.get(f'/evidence/{old}', headers={
        **w['other'], 'If-None-Match': etag}).status_code == 304
    _correct(w, old)
    again = api.get(f'/evidence/{old}', headers={
        **w['other'], 'If-None-Match': etag})
    assert again.status_code == 200
    assert again.json()['has_open_correction'] is True


def test_the_flag_is_not_in_the_evidence_of_the_passport(world):
    w, api = world, world['api']
    old = _published_record(w)
    _correct(w, old)
    got = api.get(f'/identities/{BEAM}/compose', params={'include': 'evidence'},
                  headers=w['moderator'])
    assert got.status_code == 200
    assert got.json()['evidence']
    assert 'has_open_correction' not in got.text
    jsonld = api.get(f'/identities/{BEAM}/compose',
                     params={'include': 'evidence', 'format': 'jsonld'},
                     headers=w['moderator'])
    assert 'has_open_correction' not in jsonld.text


def test_a_route_that_did_not_look_it_up_does_not_claim_false(world):
    """`identity_body` leaves `has_open_snapshot` out; only compose, `expand=none`
    and the passport of an element without a current version compute it."""
    w, api = world, world['api']
    _open_snapshot(w)
    patched = api.patch(f'/identities/{BEAM}', json={'trade_name': 'Open flag'},
                        headers=w['moderator'])
    assert patched.status_code == 200, patched.text
    assert 'has_open_snapshot' not in patched.json()
    listed = api.get('/identities', params={'expand': 'none', 'circulation': 'all'},
                     headers=w['moderator'])
    assert listed.status_code == 200, listed.text
    rows = [r for r in listed.json() if r.get('_id') == BEAM]
    if rows:
        assert 'has_open_snapshot' not in rows[0]
    # the routes that look it up say so, also while it is open
    assert _flag(w, 'moderator') is True
    assert _flag(w, 'moderator', 'none') is True


def test_a_reviewer_only_member_is_told_of_neither_flag(world):
    """8.195 amended: a member who only reviews gets False on both flags, on
    the single and on the list routes, with a version and a correction open."""
    w = world
    _public(w)
    old = _published_record(w)
    new = _correct(w, old)
    _open_snapshot(w, 'pending')
    for route in ('compose', 'none'):
        assert _flag(w, 'reviewer', route) is False, route
        assert _flag(w, 'moderator', route) is True, route
    # the list: the reviewer sees the pending correction and the published
    # record, and both say False
    rows = _listed(w, 'reviewer')
    assert new in rows and rows[old] is False and rows[new] is False
    assert _listed(w, 'moderator')[old] is True
    for rid in (old, new):
        got = w['api'].get(f'/evidence/{rid}', headers=w['reviewer'])
        assert got.status_code == 200, got.text
        assert got.json()['has_open_correction'] is False, rid
    assert w['api'].get(f'/evidence/{old}', headers=w['moderator']).json()[
        'has_open_correction'] is True
