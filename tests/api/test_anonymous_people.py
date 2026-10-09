"""
An anonymous caller never receives a person (decision 8.101, spec 3.6).

One catalog in which every person field carries a unique, invented marker
(``zz-...``). For each route family that an anonymous caller can reach, the
JSON of an ``is_public`` component read anonymously is scanned for the keys
that name a person and for every marker; the same read signed in still has
them. The pieces: the beam (public; a published snapshot with an author, a
published and reviewed core test with a recorder, a performer and a file, an
origin with a named performer, a reservation) and, in the cut chain
(panel -> cut -> cut2), a reserved child.
"""

from __future__ import annotations

import json

import pytest

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from apps.catalog.people import (
    PERSON_KEYS,
    PERSON_SUFFIXES,
    strip_people,
)
from evidence_samples import LAB, PDF, core_body, person
from support import iid, sid

BEAM = iid('beam')
PANEL = iid('panel')
CUT = iid('cut')
CUT2 = iid('cut2')
SNAP = sid('beam', 1)

# every person field of the fixture carries one of these
MARKERS = {
    'snapshot_author': 'zz-snapshot-author',
    'snapshot_mover': 'zz-snapshot-mover',
    'identity_creator': 'zz-identity-creator',
    'recorder': 'zz-evidence-recorder',
    'reviewer': 'zz-evidence-reviewer',
    'moderator': 'zz-evidence-moderator',
    'reserver': 'zz-reserving-user',
    'performer': 'Dr. Zed Zz-Performer',
    'performer_mail': 'zz-performer@example.invalid',
    'performer_orcid': '0000-0000-0000-0zz0',
    'origin_person': 'Zz Origin Person',
    'origin_mail': 'zz-origin@example.invalid',
}


def person_keys_in(value, path=''):
    """Every key in ``value`` (any depth) that names a person."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in PERSON_KEYS or key.endswith(PERSON_SUFFIXES):
                found.append(f'{path}.{key}')
            found += person_keys_in(item, f'{path}.{key}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found += person_keys_in(item, f'{path}[{index}]')
    return found


def actor_fields_in(value, path=''):
    """Person parts of an actor: name, role, ORCID, e-mail, user id."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ('performed_by', 'assessed_by', 'by', 'operator'):
                for actor in item if isinstance(item, list) else [item]:
                    for part in ('name', 'role', 'orcid', 'email',
                                 'user_id'):
                        if isinstance(actor, dict) and part in actor:
                            found.append(f'{path}.{key}.{part}')
            found += actor_fields_in(item, f'{path}.{key}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found += actor_fields_in(item, f'{path}[{index}]')
    return found


def markers_in(value, ids=()):
    """The markers and the ids of the fixture's accounts found in ``value``."""
    text = json.dumps(value)
    return sorted(m for m in (*MARKERS.values(), *ids) if m in text)


def assert_no_people(w, body, what):
    assert person_keys_in(body) == [], what
    assert actor_fields_in(body) == [], what
    assert markers_in(body, w['ids']) == [], what


@pytest.fixture
def world(api, db, auth_headers, member_headers, make_user):
    from support import seed_05_catalog
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    c, cid = member_headers({'dbu_zirkus': ['contributor']},
                            username=MARKERS['recorder'])
    r, rid = member_headers({'dbu_zirkus': ['reviewer']},
                            username=MARKERS['reviewer'])
    m, mid = member_headers({'dbu_zirkus': ['moderator']},
                            username=MARKERS['moderator'])
    reserver = make_user(username=MARKERS['reserver'])
    w = {'api': api, 'db': db, 'c': c, 'cid': cid, 'r': r, 'rid': rid,
         'm': m, 'mid': mid, 'user': auth_headers('user'),
         'admin': auth_headers('admin'), 'reserver': reserver,
         'ids': [cid, rid, mid, reserver['id']]}

    # the pieces that are public: the beam and the cut chain
    for piece in (BEAM, PANEL, CUT, CUT2):
        db['component_identities'].update_one(
            {'_id': piece}, {'$set': {'is_public': True}})
    db['component_identities'].update_one({'_id': BEAM}, {'$set': {
        'created_by_user_id': MARKERS['identity_creator'],
        'origin': {'kind': 'deinstallation', 'at_precision': 'unknown',
                   'performed_by': [{
                       'kind': 'person', 'name': MARKERS['origin_person'],
                       'email': MARKERS['origin_mail'],
                       'organization': 'Abbruch Muster GmbH',
                       'role': 'operator'}]},
        'reserved': reserver['id']}})
    db['component_identities'].update_one(
        {'_id': CUT}, {'$set': {'reserved': reserver['id']}})
    db['component_snapshots'].update_many(
        {'identity_id': BEAM}, {'$set': {
            'added_by_user_id': MARKERS['snapshot_author'],
            'added_by_username': MARKERS['snapshot_author'],
            'status_changed_by_user_id': MARKERS['snapshot_mover'],
            'status_history': [{
                'from': 'pending', 'to': 'published',
                'at': '2026-06-15T00:00:00Z',
                'by_user_id': MARKERS['snapshot_mover'], 'reason': None}]}})

    # a published, reviewed core test with a named performer and a file
    created = api.post(f'/identities/{BEAM}/evidence', headers=c, json=core_body(
        performed_by=[
            {**LAB, 'name': MARKERS['performer'],
             'email': MARKERS['performer_mail'],
             'orcid': MARKERS['performer_orcid']},
            person(cid)]))
    assert created.status_code == 201, created.text
    eid = created.json()['_id']
    for verb, who in (('submit', c), ('publish', m)):
        assert api.post(f'/evidence/{eid}/{verb}', headers=who
                        ).status_code == 200
    review = api.put(f'/evidence/{eid}/verification', headers=r,
                     json={'state': 'reviewed', 'note': 'checked'})
    assert review.status_code == 200, review.text
    attached = api.post('/evidence/attachments', data={'record_ids': [eid]},
                        files={'file': ('report.pdf', PDF, 'application/pdf')},
                        headers=c)
    assert attached.status_code == 201, attached.text
    w['eid'] = eid
    return w


def get(w, url, headers=None, **params):
    response = w['api'].get(url, headers=headers or {}, params=params)
    assert response.status_code == 200, (url, response.status_code,
                                         response.text)
    return response.json()


# THE FUNCTION ------------------------------------------------------------------
def test_strip_people_drops_the_person_and_keeps_the_organization():
    body = {
        'added_by_user_id': 'u', 'added_by_username': 'n', 'name': 'piece',
        'reserved': 'u', 'is_reserved': True,
        'performed_by': [{'kind': 'person', 'name': 'N', 'orcid': 'O',
                          'email': 'E', 'role': 'operator',
                          'organization': 'Lab GmbH'}],
        'verification': {'state': 'reviewed',
                         'by': {'kind': 'user', 'user_id': 'u'}},
        'status_history': [{'from': 'a', 'to': 'b', 'by_user_id': 'u'}],
        'attachments': [{'name': 'f.pdf', 'uploaded_by_user_id': 'u',
                         'removed': {'at': 't', 'by_user_id': 'u'}}]}
    out = strip_people(body)
    assert person_keys_in(out) == [] and actor_fields_in(out) == []
    assert out['name'] == 'piece' and out['is_reserved'] is True
    assert out['performed_by'] == [{'kind': 'person',
                                    'organization': 'Lab GmbH'}]
    assert out['verification'] == {'state': 'reviewed',
                                   'by': {'kind': 'user'}}
    assert out['status_history'] == [{'from': 'a', 'to': 'b'}]
    assert body['added_by_user_id'] == 'u'              # a copy


# IDENTITY, SNAPSHOT, PASSPORT ---------------------------------------------------
def test_identity_and_passport(world):
    w = world
    for url, params in (
            (f'/identities/{BEAM}', {}),
            (f'/identities/{BEAM}', {'expand': 'none'}),
            (f'/identities/{BEAM}', {'expand': 'current_snapshot'}),
            (f'/identities/{BEAM}/compose', {}),
            (f'/identities/{BEAM}/compose', {'snapshots': 'all'}),
            (f'/identities/{BEAM}/compose', {'include': 'evidence'}),
            (f'/snapshots/{SNAP}', {})):
        anon = get(w, url, **params)
        assert_no_people(w, anon, f'{url} {params}')
        signed = get(w, url, headers=w['user'], **params)
        assert signed != anon, (url, params)
    # the reservation stays visible as a status, not as a user
    shallow = get(w, f'/identities/{BEAM}')
    assert shallow['is_reserved'] is True and 'reserved' not in shallow
    passport = get(w, f'/identities/{BEAM}/compose')
    assert passport['identity']['is_reserved'] is True
    assert 'reserved' not in passport['identity']
    assert 'created_by_user_id' not in passport['identity']
    assert 'added_by_username' not in passport['snapshots'][0]
    origin_actor = passport['identity']['origin']['performed_by'][0]
    assert origin_actor['organization'] == 'Abbruch Muster GmbH'
    assert origin_actor['kind'] == 'person' and 'name' not in origin_actor
    # signed in: today's fields
    signed = get(w, f'/identities/{BEAM}/compose', headers=w['user'])
    assert signed['identity']['reserved'] == w['reserver']['id']
    assert signed['identity']['created_by_user_id'] == \
        MARKERS['identity_creator']
    assert signed['snapshots'][0]['added_by_username'] == \
        MARKERS['snapshot_author']
    assert signed['snapshots'][0]['status_history'][0]['by_user_id'] == \
        MARKERS['snapshot_mover']
    actor = signed['identity']['origin']['performed_by'][0]
    assert actor['name'] == MARKERS['origin_person']
    # another representation, another ETag
    first = w['api'].get(f'/identities/{BEAM}/compose')
    again = w['api'].get(f'/identities/{BEAM}/compose', headers={
        'If-None-Match': first.headers['etag']})
    assert again.status_code == 304
    other = w['api'].get(f'/identities/{BEAM}/compose', headers=w['user'])
    assert other.headers['etag'] != first.headers['etag']


def test_snapshot_list(world):
    w = world
    anon = get(w, f'/identities/{BEAM}/snapshots')
    assert anon and all('added_by_username' not in row for row in anon)
    assert_no_people(w, anon, 'snapshot list')
    signed = get(w, f'/identities/{BEAM}/snapshots', headers=w['user'])
    assert {row['added_by_username'] for row in signed} == {
        MARKERS['snapshot_author']}


# EVIDENCE ----------------------------------------------------------------------
def test_evidence(world):
    w = world
    eid = w['eid']
    for url, params in (
            (f'/evidence/{eid}', {}),
            (f'/evidence/{eid}', {'include': 'context'}),
            (f'/identities/{BEAM}/evidence', {}),
            (f'/identities/{BEAM}/evidence', {'include': 'context'}),
            ('/evidence', {}),
            (f'/evidence/{eid}/attachments', {})):
        anon = get(w, url, **params)
        assert anon, url
        assert_no_people(w, anon, f'{url} {params}')
    record = get(w, f'/evidence/{eid}')
    assert record['summary'] and record['verification']['state'] == \
        'reviewed'
    # the organization of a performer stays; the person goes
    assert record['performed_by'][0]['organization'] == (
        'Pruefstelle Muster GmbH')
    assert record['performed_by'][0]['accreditation']['id'] == (
        LAB['accreditation']['id'])
    assert 'by' in record['verification'] \
        and 'user_id' not in record['verification']['by']
    # signed in: the recorder, the performers and the reviewer
    signed = get(w, f'/evidence/{eid}', headers=w['user'])
    assert signed['recorded_by_username'] == MARKERS['recorder']
    assert signed['performed_by'][0]['name'] == MARKERS['performer']
    assert signed['verification']['by']['user_id'] == w['rid']
    listed = get(w, f'/identities/{BEAM}/evidence', headers=w['user'])
    assert listed[0]['recorded_by_username'] == MARKERS['recorder']
    assert get(w, f'/evidence/{eid}/attachments', headers=w['user'])[
        0]['uploaded_by_user_id'] == w['cid']
    # the passport's evidence follows the same rule
    inline = get(w, f'/identities/{BEAM}/compose', include='evidence')
    assert inline['evidence']
    assert_no_people(w, inline['evidence'], 'passport evidence')


def test_properties_and_timeline(world):
    w = world
    for url in (f'/identities/{BEAM}/properties',
                f'/snapshots/{SNAP}/properties',
                f'/identities/{BEAM}/timeline'):
        assert_no_people(w, get(w, url), url)
        assert get(w, url, headers=w['user'])
    events = get(w, f'/identities/{BEAM}/timeline')['events']
    assert events


# LINEAGE, GRAPH, CHILDREN ---------------------------------------------------------
def test_lineage_graph_and_children(world):
    w = world
    graph = get(w, f'/identities/{PANEL}/provenance')
    assert {n['identity_id'] for n in graph['nodes']
            if n['kind'] == 'identity'} >= {PANEL, CUT, CUT2}
    assert_no_people(w, graph, 'provenance')
    children = get(w, f'/identities/{PANEL}/children')
    assert [row['_id'] for row in children] == [CUT]
    assert_no_people(w, children, 'children')
    assert children[0]['is_reserved'] is True
    assert 'reserved' not in children[0]
    signed = get(w, f'/identities/{PANEL}/children', headers=w['user'])
    assert signed[0]['reserved'] == w['reserver']['id']
    assert signed[0]['reserved_by_username'] == MARKERS['reserver']


# WHAT AN ANONYMOUS CALLER CANNOT REACH ----------------------------------------------
def test_history_queues_and_accounts_need_an_account(world):
    w = world
    api = w['api']
    for url in (f'/identities/{BEAM}/changes',
                '/evidence/pending', '/snapshots/pending', '/snapshots',
                '/users/me', '/users'):
        assert api.get(url).status_code in (401, 404, 405, 422), url
    # as-of reads (old values may name people) are for members
    assert api.get(f'/identities/{BEAM}', params={
        'as_of': '2999-01-01T00:00:00Z'}).status_code in (401, 403)
    assert api.get(f'/evidence/{w["eid"]}', params={
        'as_of': '2999-01-01T00:00:00Z'}).status_code in (401, 403)
    # a dataset carries members only for its moderator
    for url in ('/datasets', '/datasets/dbu_zirkus'):
        body = api.get(url)
        if body.status_code == 200:
            assert_no_people(w, body.json(), url)


LISTS = ('/identities', '/identities/count', '/identities/stats',
         '/identities/meta/datasets', '/identities/map')


def test_the_lists_answer_an_anonymous_caller_with_public_pieces_only(world):
    """8.118 Q8: list, count, stats, meta and map for an anonymous caller:
    the public tier, no people; the status filters cannot widen it."""
    w = world
    api, db = w['api'], w['db']
    public = {i['_id'] for i in db['component_identities'].find(
        {'is_public': True})}
    private = {i['_id'] for i in db['component_identities'].find(
        {'is_public': {'$ne': True}, 'current_snapshot_id': {'$ne': None}})}
    assert public and private
    wide = {'circulation': 'all', 'status': 'any', 'include_withdrawn': 'true'}
    rows = get(w, '/identities', size=0, **wide)
    ids = {r['_id'] for r in rows}
    assert BEAM in ids and ids <= public and not ids & private
    assert all(r['status'] == 'published' for r in rows)
    assert_no_people(w, rows, '/identities')
    beam = next(r for r in rows if r['_id'] == BEAM)
    assert beam['is_reserved'] is True and 'reserved' not in beam
    assert 'reserved_by_username' not in beam
    # a signed-in caller sees more, and the people
    signed = get(w, '/identities', headers=w['admin'], size=0, **wide)
    assert ids < {r['_id'] for r in signed}
    assert next(r for r in signed if r['_id'] == BEAM)['reserved'] ==         w['reserver']['id']
    # the rest of the family: the same set, no people
    assert get(w, '/identities/count', **wide)['count'] == len(ids)
    stats = get(w, '/identities/stats', **wide)
    assert stats['total'] == len(ids)
    # where the pieces are, and how many pieces the states stand for
    assert sum(i['count'] for i in stats['byCirculation']) == len(ids)
    assert {i['label'] for i in stats['byCirculation']} <= {
        'in_place', 'deinstalled', 'exited'}
    assert stats['pieces'] >= len(ids)
    # `reserved` here is a count of true / false, not a user id
    assert {i['label'] for i in stats['reserved']} <= {'true', 'false'}
    assert_no_people(w, {k: v for k, v in stats.items() if k != 'reserved'},
                     '/identities/stats')
    datasets = get(w, '/identities/meta/datasets', circulation='all')
    assert datasets and set(datasets) <= {
        i['dataset'] for i in db['component_identities'].find(
            {'_id': {'$in': sorted(public)}})}
    # a state filter does not reach unpublished or private pieces
    for status in ('pending', 'draft', 'rejected', 'withdrawn'):
        got = get(w, '/identities', size=0, status=status)
        assert {r['_id'] for r in got} <= ids, status
        assert all(r['status'] == 'published' for r in got), status
    # its own representation and its own cache rule
    first = api.get('/identities', params={'size': 0})
    assert first.headers['cache-control'] == 'public, max-age=3600'
    assert 'authorization' in first.headers['vary'].lower()
    again = api.get('/identities', params={'size': 0},
                    headers={'If-None-Match': first.headers['etag']})
    assert again.status_code == 304
    other = api.get('/identities', params={'size': 0}, headers=w['user'])
    assert other.headers['etag'] != first.headers['etag']
    assert other.headers['cache-control'] == 'private, max-age=3600'


def test_the_map_cache_keeps_the_public_points_for_an_anonymous_caller(world):
    w = world
    db = w['db']
    private = db['component_identities'].find_one(
        {'is_public': {'$ne': True}, 'current_snapshot_id': {'$ne': None}})
    point = {'x': 0.0, 'y': 0.0, 'name': 'p', 'in_place': False,
             'dataset': 'dbu_zirkus', 'material': 'm', 'shape_class': 'Linear'}
    db['component_map_cache'].insert_one({
        '_id': 'radial_signature:umap:active:published',
        'basis': 'radial_signature', 'method': 'umap', 'total': 2,
        'displayed': 2, 'computed_at': '2026-10-01T00:00:00Z',
        'points': [{**point, 'id': BEAM}, {**point, 'id': private['_id']}]})
    anonymous = get(w, '/identities/map')
    assert [p['id'] for p in anonymous['points']] == [BEAM]
    assert anonymous['displayed'] == anonymous['total'] == 1
    # what the map colours by travels with the point
    assert anonymous['points'][0]['dataset'] == 'dbu_zirkus'
    assert anonymous['points'][0]['shape_class'] == 'Linear'
    assert len(get(w, '/identities/map', headers=w['admin'])['points']) == 2
    # anything but the cached default scope needs source=live: not offered
    assert w['api'].get('/identities/map', params={
        'dataset': 'dbu_zirkus'}).status_code == 400


def test_the_search_field_takes_a_name_a_number_or_an_id(world):
    w = world
    rows = get(w, '/identities', size=0, circulation='all')
    beam = next(r for r in rows if r['_id'] == BEAM)
    name = beam['name']
    assert name
    number = beam['catalog_number']
    for q in (name, name.upper(), name[1:4], str(number), f'#{number}',
              BEAM, BEAM[:8], BEAM[:8].upper()):
        got = {r['_id'] for r in get(w, '/identities', size=0, q=q,
                                     circulation='all')}
        assert BEAM in got, q
    assert get(w, '/identities', size=0, q='no such piece zzz') == []
    assert get(w, '/identities/count', q='no such piece zzz')['count'] == 0
    assert get(w, '/identities/stats', q='no such piece zzz')['total'] == 0
    # regular expression characters are text
    assert get(w, '/identities', size=0, q='.*') == []
    # the search narrows the other filters, it does not replace them
    assert get(w, '/identities', size=0, q=name, circulation='all',
               dataset='nowhere') == []


def test_the_list_family_sets_the_viewer_cache_headers(world):
    """The five list routes carry the cache rule of their tier and vary by the
    caller, as the single-piece routes do."""
    w = world
    api, db = w['api'], w['db']
    private = db['component_identities'].find_one(
        {'is_public': {'$ne': True}, 'current_snapshot_id': {'$ne': None}})
    db['component_map_cache'].replace_one(
        {'_id': 'radial_signature:umap:active:published'},
        {'_id': 'radial_signature:umap:active:published',
         'basis': 'radial_signature', 'method': 'umap', 'total': 1,
         'displayed': 1, 'points': [{'id': BEAM, 'x': 0.0, 'y': 0.0}]},
        upsert=True)
    for url, params in (('/identities', {'size': 0}),
                        ('/identities/count', {}),
                        ('/identities/stats', {}),
                        ('/identities/meta/datasets', {}),
                        ('/identities/map', {})):
        anonymous = api.get(url, params=params)
        assert anonymous.status_code == 200, url
        assert anonymous.headers['cache-control'] == 'public, max-age=3600', url
        vary = {v.strip().lower() for v in anonymous.headers['vary'].split(',')}
        assert 'authorization' in vary, url
        signed = api.get(url, params=params, headers=w['user'])
        assert signed.status_code == 200, url
        assert signed.headers['cache-control'] == 'private, max-age=3600', url
        assert 'authorization' in {
            v.strip().lower() for v in signed.headers['vary'].split(',')}, url
    assert private is not None


def test_a_list_row_says_whether_its_state_has_a_preview(world):
    """No request for an image that is not there: `has_preview` on the list
    rows (and the reserved list), absent on other routes' rows."""
    import os
    w = world
    api = w['api']
    preview_dir = api.app.snapshot_preview_dir
    os.makedirs(preview_dir, exist_ok=True)
    snapshot_id = w['db']['component_identities'].find_one(
        {'_id': BEAM})['current_snapshot_id']
    path = os.path.join(preview_dir, f'{snapshot_id}.webp')
    rows = get(w, '/identities', size=0, circulation='all')
    assert all(r['has_preview'] is False for r in rows)
    with open(path, 'wb') as handle:
        handle.write(b'RIFF')
    try:
        rows = get(w, '/identities', size=0, circulation='all')
        by_id = {r['_id']: r['has_preview'] for r in rows}
        assert by_id[BEAM] is True
        assert [k for k, v in by_id.items() if v] == [BEAM]
        # the other shapes of a list say nothing
        children = get(w, f'/identities/{PANEL}/children')
        assert all(r['has_preview'] is None for r in children)
        # the reserved list, as the owner reads it
        reserved = get(w, f"/identities/reserved/{w['reserver']['id']}",
                       headers=w['admin'])
        assert all(r['has_preview'] is not None
                   for r in reserved['components'])
    finally:
        os.remove(path)


def test_files_metadata_and_photos(world):
    w = world
    assert_no_people(w, get(w, f'/snapshots/{SNAP}/photos'), 'photos')
    listing = get(w, f'/evidence/{w["eid"]}/attachments')
    assert listing and 'uploaded_by_user_id' not in listing[0]
    assert listing[0]['sha256'] and listing[0]['name'] is None


# CACHES: A 304 NEVER HANDS ONE TIER'S BODY TO ANOTHER --------------------------------
def test_a_304_does_not_cross_tiers(world):
    w = world
    api = w['api']
    for url, params in ((f'/snapshots/{SNAP}', {}),
                        (f'/identities/{BEAM}/compose', {}),
                        (f'/identities/{BEAM}/compose',
                         {'include': 'evidence'}),
                        (f'/evidence/{w["eid"]}', {})):
        tiers = {'anonymous': {}, 'signed in': w['user'],
                 'member': w['m'], 'admin': w['admin']}
        etags = {}
        for name, headers in tiers.items():
            response = api.get(url, params=params, headers=headers)
            assert response.status_code == 200, (url, name)
            etags[name] = response.headers['etag']
        # the anonymous representation never shares an ETag with a signed-in
        # one (the snapshot body is the same for every signed-in tier)
        for name in ('signed in', 'member', 'admin'):
            assert etags['anonymous'] != etags[name], (url, params, name)
        for name, headers in tiers.items():
            same = api.get(url, params=params, headers={
                **headers, 'If-None-Match': etags[name]})
            assert same.status_code == 304, (url, params, name)
            assert 'authorization' in same.headers['vary'].lower()
            for other, theirs in etags.items():
                if theirs == etags[name]:
                    continue
                crossed = api.get(url, params=params, headers={
                    **headers, 'If-None-Match': theirs})
                assert crossed.status_code == 200, (url, name, other)
        # what a signed-in caller got must not reach a visitor after
        # sign-out: the body of the 200 has no people
        crossed = api.get(url, params=params, headers={
            'If-None-Match': etags['signed in']})
        assert crossed.status_code == 200
        assert_no_people(w, crossed.json(), f'{url} after sign-out')


def test_responses_vary_by_the_caller(world):
    w = world
    api = w['api']
    origin = {'Origin': 'http://localhost:3000'}
    for url, params in (
            (f'/identities/{BEAM}', {'expand': 'none'}),
            (f'/identities/{BEAM}/compose', {}),
            (f'/identities/{BEAM}/compose', {'include': 'evidence'}),
            (f'/identities/{PANEL}/children', {}),
            (f'/identities/{PANEL}/provenance', {}),
            (f'/snapshots/{SNAP}', {}),
            (f'/evidence/{w["eid"]}', {}),
            (f'/evidence/{w["eid"]}', {'include': 'context'})):
        for headers in ({}, w['user']):
            response = api.get(url, params=params,
                               headers={**origin, **headers})
            assert response.status_code == 200, url
            vary = {v.strip().lower()
                    for v in response.headers['vary'].split(',')}
            assert vary == {'authorization', 'origin'}, (url, vary)
    # a public answer is public in the cache, and varies
    anonymous = api.get(f'/identities/{BEAM}/compose')
    assert anonymous.headers['cache-control'] == 'public, max-age=3600'
    signed = api.get(f'/identities/{BEAM}/compose', headers=w['user'])
    assert signed.headers['cache-control'] == 'private, max-age=3600'


# THE RESERVATION AS A STATUS, ON EVERY IDENTITY-SHAPED ANSWER --------------------------
def test_is_reserved_on_every_identity_answer(world):
    w = world
    api = w['api']
    # PATCH answers with the identity: the beam is reserved
    patched = api.patch(f'/identities/{BEAM}', json={'trade_name': 'B 3'},
                        headers=w['m'])
    assert patched.status_code == 200, patched.text
    assert patched.json()['is_reserved'] is True
    assert patched.json()['reserved'] == w['reserver']['id']
    # reserve and release keep their fields and add the status
    reserve = api.post(f'/identities/{CUT2}/reserve', headers=w['user'])
    assert reserve.status_code == 200, reserve.text
    assert reserve.json()['is_reserved'] is True
    assert reserve.json()['reserved_by'] and reserve.json()['message']
    again = api.post(f'/identities/{CUT2}/reserve', headers=w['user'])
    assert again.json()['is_reserved'] is True
    assert get(w, f'/identities/{CUT2}')['is_reserved'] is True
    release = api.delete(f'/identities/{CUT2}/reserve', headers=w['user'])
    assert release.status_code == 200, release.text
    assert release.json()['is_reserved'] is False
    assert release.json()['message']
    nothing = api.delete(f'/identities/{CUT2}/reserve', headers=w['user'])
    assert nothing.json()['is_reserved'] is False
    assert get(w, f'/identities/{CUT2}')['is_reserved'] is False
    # lists and rows
    row = get(w, f'/identities/{PANEL}/children')[0]
    assert row['is_reserved'] is True
    listed = get(w, '/identities', headers=w['user'],
                 expand='shallow', size=100)
    flags = {r['_id']: r['is_reserved'] for r in listed}
    assert flags[BEAM] is True and flags[CUT2] is False


def test_the_map_total_counts_only_what_the_caller_may_see(world):
    """Decision 8.125 d: the cached payload's ``total`` counts the hidden
    pieces too; a caller gets the number of points they may see."""
    w = world
    db = w['db']
    private = db['component_identities'].find_one(
        {'is_public': {'$ne': True}, 'current_snapshot_id': {'$ne': None}})
    assert private is not None
    point = {'x': 0.0, 'y': 0.0, 'name': 'p', 'in_place': False,
             'dataset': 'dbu_zirkus', 'material': 'm', 'shape_class': 'Linear'}
    db['component_map_cache'].replace_one(
        {'_id': 'radial_signature:umap:active:published'},
        {'_id': 'radial_signature:umap:active:published',
         'basis': 'radial_signature', 'method': 'umap',
         'total': 99, 'displayed': 2,
         'points': [{**point, 'id': BEAM}, {**point, 'id': private['_id']}]},
        upsert=True)
    anonymous = get(w, '/identities/map')
    assert [p['id'] for p in anonymous['points']] == [BEAM]
    assert anonymous['displayed'] == anonymous['total'] == 1   # not 99
    signed_in = get(w, '/identities/map', headers=w['user'])
    assert signed_in['total'] == signed_in['displayed'] == len(signed_in['points'])
    assert signed_in['total'] < 99
    # an admin sees everything: the cached number stands
    admin = get(w, '/identities/map', headers=w['admin'])
    assert admin['total'] == 99 and len(admin['points']) == 2
