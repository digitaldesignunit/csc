"""
The read-only MCP layer (decisions 8.165, 8.168): the endpoint behind the access
tokens, the ten tools on a migrated catalog (what the owner of the token sees on
the website, nothing private for anyone else, every non-public record marked, no
e-mail address or account id), the maintenance flag and the limits.
"""

from __future__ import annotations

import json
import re
import uuid

import pytest

from apps.catalog import access_tokens as tk
from apps.catalog import mcp_server
from apps.catalog.component_map import cache_doc_id
from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from oauth_helpers import (
    bearer,
    connect,
    mcp_post,
    reset_address_counters,
    tool,
    tool_result,
)
from support import iid, seed_05_catalog, sid

TOOLS = {'search_components', 'get_component', 'list_versions', 'get_version',
         'get_evidence', 'list_datasets', 'get_dataset', 'get_timeline',
         'similar_components', 'catalog_overview'}
WEB = 'http://localhost:3000'
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')


@pytest.fixture(autouse=True)
def fresh_counters():
    reset_address_counters()
    yield
    reset_address_counters()


@pytest.fixture
def world(api, db, make_user, login):
    """The migrated test catalog and an administrator with a PAT."""
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    from apps.catalog.geometry_runner import derive_and_store_sync
    from apps.catalog.geometry_stages import Env
    identities = {i['_id']: i for i in db['component_identities'].find({})}
    for snap in list(db['component_snapshots'].find({})):
        derive_and_store_sync(
            db['component_snapshots'], snap, identities[snap['identity_id']],
            Env(), None, ['frame', 'shape_class'], force=True)
    admin = make_user('adminuser', role='admin')
    jwt = login('adminuser').json()['access_token']
    pat = api.post('/auth/access-tokens', json={'name': 'mcp'}, headers=bearer(jwt)).json()['token']
    return {'api': api, 'db': db, 'admin_jwt': bearer(jwt), 'admin': pat, 'admin_id': admin['id']}


def pat_for(api, headers, name='p'):
    made = api.post('/auth/access-tokens', json={'name': name}, headers=headers)
    assert made.status_code == 201, made.text
    return made.json()['token']


@pytest.fixture
def plain(world, env, api, make_user, login):
    """An account with no dataset role, allowed to hold a token by the setting."""
    env(CSC_PAT_ROLES='admin,user')
    make_user('plainuser', role='user')
    jwt = bearer(login('plainuser').json()['access_token'])
    return {'jwt': jwt, 'pat': pat_for(api, jwt)}


@pytest.fixture
def dataset_member(world, env, api, member_headers):
    env(CSC_PAT_ROLES='admin,user')
    headers, user_id = member_headers({'dbu_zirkus': ['contributor']})
    return {'jwt': headers, 'pat': pat_for(api, headers), 'id': user_id}


def ids_of(rows):
    return sorted(r['id'] if 'id' in r else r['_id'] for r in rows)


# THE ENDPOINT -----------------------------------------------------------------------
def test_initialize_names_the_server_and_tells_the_model_what_it_is_for(api, world):
    response = mcp_post(api, world['admin'], 'initialize', {
        'protocolVersion': '2025-06-18', 'capabilities': {},
        'clientInfo': {'name': 'test', 'version': '1'}})
    assert response.status_code == 200, response.text
    result = response.json()['result']
    assert result['serverInfo']['name'] == 'Catalog of Second Chances'
    assert 'These tools only read' in result['instructions']


def test_exactly_these_ten_tools_exist_and_each_explains_itself(api, world):
    listed = mcp_post(api, world['admin'], 'tools/list').json()['result']['tools']
    assert {t['name'] for t in listed} == TOOLS
    for entry in listed:
        assert len(entry['description']) > 60, entry['name']
        assert entry['inputSchema']['type'] == 'object'
        for name, prop in entry['inputSchema'].get('properties', {}).items():
            assert prop.get('description'), (entry['name'], name)
    forbidden = ('user', 'invitation', 'token', 'create', 'update', 'delete', 'write')
    assert not [t['name'] for t in listed if any(w in t['name'] for w in forbidden if w != 'user')]
    assert 'users' not in ' '.join(t['name'] for t in listed)


def test_a_personal_access_token_and_a_connection_both_reach_the_tools(api, world):
    assert mcp_post(api, world['admin'], 'tools/list').status_code == 200
    c = connect(api, world['admin_jwt'])
    assert mcp_post(api, c['access'], 'tools/list').status_code == 200


def test_only_tokens_that_pass_get_in_with_one_answer(api, db, world):
    bodies = []
    for headers in ({}, {'Authorization': 'Basic abc'}, bearer('csc_pat_' + 'A' * 43), bearer('nonsense'),
                    world['admin_jwt']):
        response = api.post('/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
                            headers={'Accept': 'application/json, text/event-stream', **headers})
        assert response.status_code == 401, headers
        assert 'resource_metadata=' in response.headers['www-authenticate']
        bodies.append(response.json())
    assert all(b == bodies[0] for b in bodies)
    device = tk.new_token('device')
    db['access_tokens'].insert_one({
        '_id': 'dev1', 'kind': 'device', 'owner_user_id': world['admin_id'], 'scopes': ['gh:client'],
        'name': 'd', 'token_sha256': tk.token_hash(device), 'short_id': tk.short_id_of(device),
        'created': tk.stamp(tk.now()), 'expires': tk.expires_at(30), 'last_used': None, 'revoked': None})
    assert mcp_post(api, device, 'tools/list').status_code == 401


def test_a_revoked_pat_stops_at_once(api, world):
    row = api.get('/auth/access-tokens', headers=world['admin_jwt']).json()[0]
    assert mcp_post(api, world['admin'], 'tools/list').status_code == 200
    api.delete(f'/auth/access-tokens/{row["id"]}', headers=world['admin_jwt'])
    assert mcp_post(api, world['admin'], 'tools/list').status_code == 401


def test_the_limit_is_per_token_with_a_429_and_a_retry_after(api, world, monkeypatch):
    monkeypatch.setattr(tk, 'REQUESTS_PER_MINUTE', 3)
    other = pat_for(api, world['admin_jwt'], 'other')
    assert [mcp_post(api, world['admin'], 'tools/list').status_code for _ in range(3)] == [200] * 3
    limited = mcp_post(api, world['admin'], 'tools/list')
    assert limited.status_code == 429 and int(limited.headers['retry-after']) >= 1
    assert mcp_post(api, other, 'tools/list').status_code == 200


def test_under_the_maintenance_flag_the_tools_still_answer(api, world, read_only_flag):
    read_only_flag.on()
    answer = tool(api, world['admin'], 'search_components')
    assert answer['total'] == 3


def test_the_tools_call_the_catalog_even_when_the_client_header_is_enforced(api, app, world):
    app.state.min_client_versions = {'web': (0, 6, 0, 0)}
    try:
        none = {'X-CSC-Client': ''}
        response = mcp_post(api, world['admin'], 'tools/call',
                            {'name': 'search_components', 'arguments': {}}, headers=none)
        assert response.status_code == 200 and not response.json()['result']['isError']
        # a header that merely says mcp is no exemption for the REST API
        assert api.get('/identities', headers={**world['admin_jwt'], 'X-CSC-Client': 'mcp/1'}).status_code == 426
    finally:
        app.state.min_client_versions = {}


def test_the_tools_write_nothing(api, db, world):
    names = ('component_identities', 'component_snapshots', 'component_evidence', 'datasets',
             'change_log', 'users', 'invitations')
    before = {n: sorted(map(repr, db[n].find({}))) for n in names}
    for name, args in (('search_components', {}), ('get_component', {'component_id': iid('beam')}),
                       ('list_versions', {'component_id': iid('beam')}),
                       ('get_version', {'version_id': sid('beam', 1)}),
                       ('get_evidence', {'component_id': iid('beam')}), ('list_datasets', {}),
                       ('get_dataset', {'dataset_id': 'dbu_zirkus'}),
                       ('get_timeline', {'component_id': iid('beam')})):
        tool_result(api, world['admin'], name, **args)
    assert {n: sorted(map(repr, db[n].find({}))) for n in names} == before


# SEARCH --------------------------------------------------------------------------------
def test_search_gives_short_rows_with_marks_and_links(api, world):
    answer = tool(api, world['admin'], 'search_components')
    assert answer['total'] == 3 and answer['page'] == 1
    rows = {r['name']: r for r in answer['results']}
    assert set(rows) == {'beam', 'cut2', 'feld'}
    beam = rows['beam']
    assert beam['id'] == iid('beam') and beam['original_function'] == 'IfcBeam'
    assert beam['dataset'] == 'dbu_zirkus' and beam['status'] == 'published'
    assert beam['visibility'] == 'private' and beam['in_circulation'] is True
    assert beam['web_link'] == f'{WEB}/components/{iid("beam")}'
    assert len(beam['bbx_mm']) == 3 and beam['version'] == 1
    assert 'geometry' not in beam and 'origin' not in beam


def test_search_filters_pages_and_caps_the_page_size(api, world):
    admin = world['admin']
    assert [r['name'] for r in tool(api, admin, 'search_components', original_function='IfcBeam')['results']] == ['beam']
    assert tool(api, admin, 'search_components', query='feld')['total'] == 1
    assert tool(api, admin, 'search_components', dataset='dbu_zirkus')['total'] == 1
    assert tool(api, admin, 'search_components', circulation='all')['total'] == 6
    first = tool(api, admin, 'search_components', size=2, page=1)
    second = tool(api, admin, 'search_components', size=2, page=2)
    assert first['total'] == second['total'] == 3
    assert len(first['results']) == 2 and len(second['results']) == 1
    assert not set(ids_of(first['results'])) & set(ids_of(second['results']))
    assert tool(api, admin, 'search_components', size=1000)['size'] == 25
    assert tool(api, admin, 'search_components', page=0, size=0)['page'] == 1


# SEARCH BY SIZE AND SORTING (8.169, 8.173) -----------------------------------------------
SIZES = {'beam': [3000, 200, 100], 'cut2': [500, 1000, 300], 'feld': [500, 500, 500]}


def _sized(db):
    for name, bbx in SIZES.items():
        db['component_snapshots'].update_many({'name': name}, {'$set': {'bbx': bbx}})


def _names(answer):
    return [r['name'] for r in answer['results']]


def test_search_by_size_gives_the_deviation_or_the_waste(api, db, world):
    _sized(db)
    admin = world['admin']
    about = tool(api, admin, 'search_components', fit_mode='about',
                 size_mm=[300, 1000, 540], tolerance='10%')
    # cut2 is 500 x 1000 x 300 turned: 8 % off on the 500 side only, feld is out
    assert _names(about) == ['cut2'] and about['total'] == 1
    assert about['results'][0]['fit'] == {'mode': 'about', 'deviation_percent': 7.41}
    assert (about['sort'], about['order']) == ('match', 'asc')
    held = tool(api, admin, 'search_components', fit_mode='can_hold',
                size_mm=[400, 300, 200])
    # feld 500^3 (waste 125 - 24 dm3), cut2 (150 - 24 dm3), beam is too thin
    assert _names(held) == ['feld', 'cut2']
    assert held['results'][0]['fit'] == {
        'mode': 'can_hold', 'waste_m3': 0.1, 'waste_percent': 81}
    assert held['results'][1]['fit'] == {
        'mode': 'can_hold', 'waste_m3': 0.13, 'waste_percent': 84}
    assert held['total'] == 2
    plain = tool(api, admin, 'search_components')
    assert all('fit' not in r for r in plain['results'])


def test_search_sorts_by_the_keys_in_both_directions(api, db, world):
    _sized(db)
    admin = world['admin']

    def order(**args):
        return _names(tool(api, admin, 'search_components', **args))

    assert order(sort='volume') == ['beam', 'feld', 'cut2']
    assert order(sort='volume', order='desc') == ['cut2', 'feld', 'beam']
    assert order(sort='catalog_number', order='desc') == order(sort='catalog_number')[::-1]
    assert sorted(order(sort='date')) == sorted(order(sort='created'))
    assert tool(api, admin, 'search_components', fit_mode='can_hold',
                size_mm=[1, 1, 1], sort='volume', order='desc')['sort'] == 'volume'


def test_the_waste_of_a_batch_is_per_piece():
    row = {'fit': {'mode': 'can_hold', 'waste_mm3': 12_400_000, 'waste_percent': 41.2},
           'quantity': 4}
    assert mcp_server.fit_of(row) == {
        'mode': 'can_hold', 'waste_m3': 0.012, 'waste_percent': 41, 'per_piece': True}
    assert 'per_piece' not in mcp_server.fit_of({**row, 'quantity': 1})
    assert 'per_piece' not in mcp_server.fit_of(
        {'fit': {'mode': 'about', 'deviation': 0.1}, 'quantity': 4})


def test_the_waste_reads_in_m3_with_two_digits_and_in_per_cent():
    def waste(mm3, percent):
        return mcp_server.fit_of({'fit': {'mode': 'can_hold', 'waste_mm3': mm3,
                                          'waste_percent': percent}})
    assert waste(1_700_000, 0.4) == {'mode': 'can_hold', 'waste_m3': 0.0017, 'waste_percent': 0.4}
    assert waste(120_000_000, 41.4) == {'mode': 'can_hold', 'waste_m3': 0.12, 'waste_percent': 41}
    # 100 only when the waste is all of it (8.169)
    assert waste(1_500_000_000, 99.6) == {'mode': 'can_hold', 'waste_m3': 1.5, 'waste_percent': 99}
    assert waste(1_500_000_000, 99.97)['waste_percent'] == 99
    assert waste(1_500_000_000, 99.4)['waste_percent'] == 99
    assert waste(1_500_000_000, 100)['waste_percent'] == 100
    assert waste(1_700_000, 0.4)['waste_percent'] == 0.4
    assert waste(0, 0) == {'mode': 'can_hold', 'waste_m3': 0.0, 'waste_percent': 0.0}
    assert 'waste_dm3' not in waste(120_000_000, 41.4)


def test_the_asked_size_is_sent_as_plain_decimals():
    assert mcp_server.size_text([1200, 600.5, 0.0001]) == '1200,600.5,0.0001'
    assert mcp_server.size_text([100000, 1234.56789, 0.5]) == '100000,1234.56789,0.5'
    assert mcp_server.size_text([1e5, 3.0, 2]) == '100000,3,2'
    assert 'e' not in mcp_server.size_text([1e-5, 99999.99999, 1e5])


def test_a_size_with_many_digits_reaches_the_search_whole(api, db, world):
    _sized(db)
    db['component_snapshots'].update_many({'name': 'feld'}, {'$set': {'bbx': [500.123456, 500, 500]}})
    answer = tool(api, world['admin'], 'search_components', fit_mode='about',
                  size_mm=[500, 500.123456, 500], tolerance='0mm')
    assert _names(answer) == ['feld']


def test_search_refuses_what_it_cannot_answer_in_words(api, world):
    admin = world['admin']
    for args, words in (
            ({'fit_mode': 'about'}, 'size_mm'),
            ({'size_mm': [1, 2, 3]}, 'fit_mode'),
            ({'fit_mode': 'about', 'size_mm': [1, 2]}, 'three numbers'),
            ({'fit_mode': 'near', 'size_mm': [1, 2, 3]}, 'fit_mode'),
            ({'sort': 'match'}, 'needs fit_mode'),
            ({'sort': 'size'}, 'sort is one of'),
            ({'order': 'up'}, 'asc or desc'),
            ({'fit_mode': 'can_hold', 'size_mm': [1, 2, 3], 'tolerance': '5%'}, 'no fit_tol'),
            ({'fit_mode': 'about', 'size_mm': [1, 2, 3], 'tolerance': 'x'}, 'fit_tol'),
            ({'fit_mode': 'about', 'size_mm': [1, 2, 0]}, 'above 0')):
        is_error, text = tool_result(api, admin, 'search_components', **args)
        assert is_error and words in text, (args, text)


# SEARCH BY PLACE (8.170, 8.173) -------------------------------------------------------
DARMSTADT = {'lat': 49.8728, 'lon': 8.6512}
FRANKFURT = {'lat': 50.1109, 'lon': 8.6821}        # about 26.5 km from Darmstadt
BERLIN = {'lat': 52.52, 'lon': 13.405}


def _placed(db, current, origin=None):
    """Set the stored points of pieces by name: ``current`` and ``origin`` map a
    name to a {lat, lon}."""
    from apps.catalog.geo import point_of
    for field, places in (('geo_current', current), ('geo_origin', origin or {})):
        for name, place in places.items():
            snapshot = db['component_snapshots'].find_one({'name': name})
            db['component_identities'].update_one(
                {'_id': snapshot['identity_id']}, {'$set': {field: point_of(place)}})


def test_search_by_place_gives_the_distance_in_km_nearest_first(api, db, world):
    _placed(db, {'beam': DARMSTADT, 'feld': FRANKFURT, 'cut2': BERLIN})
    admin = world['admin']
    near = {'near_lat': 49.87, 'near_lon': 8.65}
    answer = tool(api, admin, 'search_components', **near)
    assert _names(answer) == ['beam', 'feld', 'cut2'] and answer['total'] == 3
    assert answer['sort'] == 'distance'
    assert answer['near'] == {'lat': 49.87, 'lon': 8.65, 'layer': 'current', 'radius_km': None}
    km = [r['distance_km'] for r in answer['results']]
    assert km[0] < 0.5 and 26 < km[1] < 27.5 and 440 < km[2] < 450
    assert all('distance_m' not in r for r in answer['results'])
    within = tool(api, admin, 'search_components', **near, radius_km=30)
    assert _names(within) == ['beam', 'feld'] and within['total'] == 2
    assert 'near' not in tool(api, admin, 'search_components')
    assert all('distance_km' not in r for r in tool(api, admin, 'search_components')['results'])


def test_search_by_place_on_the_origin_layer_and_with_a_size_search(api, db, world):
    _sized(db)
    _placed(db, {'beam': DARMSTADT, 'feld': FRANKFURT, 'cut2': BERLIN}, {'cut2': DARMSTADT})
    admin = world['admin']
    origin = tool(api, admin, 'search_components', near_lat=49.87, near_lon=8.65,
                  near_layer='origin')
    assert _names(origin) == ['cut2'] and origin['near']['layer'] == 'origin'
    held = tool(api, admin, 'search_components', fit_mode='can_hold', size_mm=[400, 300, 200],
                near_lat=49.87, near_lon=8.65)
    # the size search filters (beam is too thin), the place sorts: Frankfurt, Berlin
    assert _names(held) == ['feld', 'cut2'] and held['sort'] == 'distance'
    assert 'fit' in held['results'][0] and 'distance_km' in held['results'][0]
    by_match = tool(api, admin, 'search_components', fit_mode='can_hold', size_mm=[400, 300, 200],
                    near_lat=49.87, near_lon=8.65, sort='match')
    assert by_match['sort'] == 'match' and _names(by_match) == ['feld', 'cut2']
    far_first = tool(api, admin, 'search_components', near_lat=49.87, near_lon=8.65,
                     sort='distance', order='desc')
    assert _names(far_first) == ['cut2', 'feld', 'beam']


def test_search_by_place_refuses_what_it_cannot_answer_in_words(api, world):
    admin = world['admin']
    for args, words in (
            ({'near_lat': 49.8}, 'both or neither'),
            ({'near_lon': 8.6}, 'both or neither'),
            ({'near_lat': 91, 'near_lon': 8}, 'latitude'),
            ({'near_lat': 49, 'near_lon': 181}, 'longitude'),
            ({'near_lat': 49, 'near_lon': 8, 'radius_km': 0}, 'above 0'),
            ({'near_lat': 49, 'near_lon': 8, 'near_layer': 'sky'}, 'current or origin'),
            ({'radius_km': 5}, 'need near_lat'),
            ({'near_layer': 'origin'}, 'need near_lat'),
            ({'sort': 'distance'}, 'needs near_lat')):
        is_error, text = tool_result(api, admin, 'search_components', **args)
        assert is_error and words in text, (args, text)


def test_the_place_search_is_described_to_the_model(api, world):
    tools = mcp_post(api, world['admin'], 'tools/list').json()['result']['tools']
    search = next(t for t in tools if t['name'] == 'search_components')
    properties = search['inputSchema']['properties']
    for name in ('near_lat', 'near_lon', 'near_layer', 'radius_km'):
        assert name in properties, name
    assert 'distance_km' in properties['near_lat']['description']
    assert 'origin' in properties['near_layer']['description']
    assert 'distance' in properties['sort']['description']
    assert 'distance_km' in search['description']
    assert not any(t['name'] == 'find_near' for t in tools)


def test_the_distance_reads_in_km_with_a_fitting_precision():
    assert mcp_server.distance_km(None) is None
    assert mcp_server.distance_km(0) == 0
    assert mcp_server.distance_km(1234.5) == 1.23
    assert mcp_server.distance_km(26_500) == 26.5
    assert mcp_server.distance_km(123_456) == 123.5


def test_the_query_description_says_what_q_matches(api, world):
    tools = mcp_post(api, world['admin'], 'tools/list').json()['result']['tools']
    search = next(t for t in tools if t['name'] == 'search_components')
    query = search['inputSchema']['properties']['query']['description']
    assert 'name' in query and 'catalog number' in query
    assert 'does not match materials, functions or places' in query
    assert 'matches names, materials' not in query


def test_a_version_that_is_not_published_is_marked_and_found_by_status_any(api, db, world):
    db['component_snapshots'].update_one({'_id': sid('feld', 1)}, {'$set': {'status': 'pending'}})
    default = tool(api, world['admin'], 'search_components')
    assert 'feld' not in [r['name'] for r in default['results']]
    anything = tool(api, world['admin'], 'search_components', status='any')
    feld = next(r for r in anything['results'] if r['name'] == 'feld')
    assert feld['status'] == 'pending' and feld['visibility'] == 'private'


@pytest.mark.parametrize('who', ['admin', 'plain', 'member'])
def test_what_the_tool_finds_is_what_the_website_shows_that_account(api, world, plain, dataset_member, who):
    token, jwt = {'admin': (world['admin'], world['admin_jwt']),
                  'plain': (plain['pat'], plain['jwt']),
                  'member': (dataset_member['pat'], dataset_member['jwt'])}[who]
    for params in ({}, {'circulation': 'all'}, {'status': 'any', 'circulation': 'all'}):
        web = api.get('/identities', params=params, headers=jwt).json()
        mcp = tool(api, token, 'search_components', **params, size=25)
        assert ids_of(mcp['results']) == ids_of(web), (who, params)
        assert mcp['total'] == api.get('/identities/count', params=params, headers=jwt).json()['count']
    datasets = api.get('/datasets', headers=jwt).json()
    assert sorted(d['id'] for d in tool(api, token, 'list_datasets')['datasets']) == sorted(d['_id'] for d in datasets)


def test_nothing_private_reaches_an_account_without_a_role_in_the_dataset(api, world, plain):
    found = tool(api, plain['pat'], 'search_components', circulation='all', status='any')
    assert iid('beam') not in str(found)
    is_error, text = tool_result(api, plain['pat'], 'get_component', component_id=iid('beam'))
    assert is_error and text.endswith('Not found, or not visible to you.')
    for name, args in (('list_versions', {'component_id': iid('beam')}),
                       ('get_version', {'version_id': sid('beam', 1)}),
                       ('get_evidence', {'component_id': iid('beam')}),
                       ('get_timeline', {'component_id': iid('beam')}),
                       ('get_dataset', {'dataset_id': 'dbu_zirkus'})):
        is_error, text = tool_result(api, plain['pat'], name, **args)
        assert is_error and text.endswith('Not found, or not visible to you.'), (name, text)
    assert 'dbu_zirkus' not in str(tool(api, plain['pat'], 'list_datasets'))


def test_a_dataset_member_sees_the_members_only_components_marked_private(api, world, dataset_member):
    found = tool(api, dataset_member['pat'], 'search_components')
    beam = next(r for r in found['results'] if r['name'] == 'beam')
    assert beam['visibility'] == 'private'
    assert tool(api, dataset_member['pat'], 'get_component', component_id=iid('beam'))['visibility'] == 'private'


# ONE COMPONENT --------------------------------------------------------------------------
def test_get_component_is_short_with_a_geometry_summary_and_its_links(api, world):
    answer = tool(api, world['admin'], 'get_component', component_id=iid('beam'))
    assert answer['id'] == iid('beam') and answer['name'] == 'beam'
    assert answer['original_function'] == 'IfcBeam' and answer['material'] == 'concrete'
    assert answer['visibility'] == 'private' and answer['in_circulation'] is True
    assert answer['origin']['kind'] == 'deinstallation'
    assert answer['origin']['place'] == 'TU Darmstadt Lichtwiese Campus'
    assert answer['properties']['rebar_diameter']['unit'] == 'mm'
    assert 'confidence' in answer['properties']['rebar_diameter']
    current = answer['current_version']
    assert current['version'] == 1 and current['status'] == 'published' and current['id'] == sid('beam', 1)
    assert current['geometry']['meshes'] == 1 and current['geometry']['mesh_vertices'] == 4
    assert 'Geometry is not sent' in current['geometry']['note']
    assert answer['version_count'] == 2
    assert answer['web_link'] == f'{WEB}/components/{iid("beam")}'
    text = json.dumps(answer)
    assert '"vertices"' not in text and '"faces"' not in text


def test_an_unknown_component_is_not_found_not_an_error_of_ours(api, world):
    for missing in ('not-an-id', iid('beam')[:-1] + '0'):
        is_error, text = tool_result(api, world['admin'], 'get_component', component_id=missing)
        assert is_error and text.endswith('Not found, or not visible to you.') or 'not valid' in text, text


def test_list_versions_and_get_version(api, world):
    versions = tool(api, world['admin'], 'list_versions', component_id=iid('beam'))
    assert [v['version'] for v in versions['versions']] == [0, 1]
    assert [v['is_current'] for v in versions['versions']] == [False, True]
    assert versions['versions'][1]['web_link'] == f'{WEB}/components/{iid("beam")}?snapshot={sid("beam", 1)}'
    one = tool(api, world['admin'], 'get_version', version_id=sid('beam', 1))
    assert one['id'] == sid('beam', 1) and one['component_id'] == iid('beam') and one['status'] == 'published'
    assert one['geometry'] == {'meshes': 1, 'mesh_vertices': 4, 'mesh_faces': 4, 'point_clouds': 0, 'proxies': 0,
                               'note': 'Geometry is not sent; open the web link to see it.'}
    assert 'planescore' in one['descriptors'] and one['web_link'].endswith(f'?snapshot={sid("beam", 1)}')
    assert '"vertices"' not in json.dumps(one)


# EVIDENCE -----------------------------------------------------------------------------------
def test_evidence_is_listed_short_and_one_record_comes_in_full(api, world):
    listed = tool(api, world['admin'], 'get_evidence', component_id=iid('beam'))
    assert listed['total'] >= 1 and listed['web_link'] == f'{WEB}/components/{iid("beam")}'
    row = listed['evidence'][0]
    assert row['method'] and row['source_tier'] and row['observed_at'] and 'summary' in row
    assert 'payload' not in row
    full = tool(api, world['admin'], 'get_evidence', evidence_id=row['id'])
    assert full['record']['payload'] is not None and full['record']['_id'] == row['id']
    assert tool(api, world['admin'], 'get_evidence', component_id=iid('beam'), size=1)['size'] == 1
    assert tool_result(api, world['admin'], 'get_evidence')[0] is True
    nothing = tool_result(api, world['admin'], 'get_evidence', evidence_id='nothing')[1]
    assert nothing.endswith('Not found, or not visible to you.')


def test_no_e_mail_address_and_no_account_id_in_any_answer(api, db, world):
    # an evidence record that names a person with an address, as an admin may see it on the website
    record = db['component_evidence'].find_one({'identity_id': iid('beam')})
    db['component_evidence'].update_one({'_id': record['_id']}, {'$set': {
        'performed_by': [{'kind': 'person', 'name': 'A. Tester', 'email': 'tester@lab.example',
                          'user_id': 'u-ddu', 'role': 'operator'}],
        'notes': 'Call tester@lab.example for the cores.'}})
    web = world['api'].get(f'/identities/{iid("beam")}/evidence', headers=world['admin_jwt']).text
    assert 'lab.example' in web                       # the website shows an admin the address
    answers = []
    for name, args in (('search_components', {'circulation': 'all', 'status': 'any'}),
                       ('get_component', {'component_id': iid('beam')}),
                       ('list_versions', {'component_id': iid('beam')}),
                       ('get_version', {'version_id': sid('beam', 1)}),
                       ('get_evidence', {'component_id': iid('beam')}),
                       ('get_evidence', {'evidence_id': record['_id']}),
                       ('list_datasets', {}), ('get_dataset', {'dataset_id': 'dbu_zirkus'}),
                       ('get_timeline', {'component_id': iid('beam')})):
        answers.append((name, json.dumps(tool(api, world['admin'], name, **args))))
    for name, text in answers:
        assert not EMAIL.search(text), (name, EMAIL.search(text).group(0))
        assert 'lab.example' not in text and 'user_id' not in text and 'u-ddu' not in text, name
    assert 'A. Tester' in dict(answers)['get_evidence']      # the name a page shows stays


def test_clean_drops_what_names_an_account_or_an_address():
    messy = {'email': 'a@b.example', 'owner_user_id': 'u1', 'user_id': 'u2', 'etag': 'x',
             'keep': 'call me at me@x.example, thanks', 'nested': [{'recorded_by_user_id': 'u3', 'name': 'N'}],
             'contact_email': 'c@d.example'}
    assert mcp_server.clean(messy) == {'keep': 'call me at [address removed], thanks', 'nested': [{'name': 'N'}]}


def test_an_answer_is_cut_to_a_size_and_says_so():
    big = {'rows': [{'text': 'x' * 2000} for _ in range(40)]}
    cut = mcp_server.limited(big)
    assert len(json.dumps(cut)) <= mcp_server.TEXT_MAX + 2000 and 'truncated' in cut
    small = {'rows': [1, 2, 3]}
    assert mcp_server.limited(small) == {'rows': [1, 2, 3]}


# DATASETS AND TIMELINE ----------------------------------------------------------------------
def test_datasets_are_listed_with_visibility_and_counts(api, world):
    listed = tool(api, world['admin'], 'list_datasets')['datasets']
    zirkus = next(d for d in listed if d['id'] == 'dbu_zirkus')
    assert zirkus['name'] == 'ZirKuS' and zirkus['visibility'] == 'members'
    assert zirkus['web_link'] == f'{WEB}/components?dataset=dbu_zirkus'
    assert 'components' in zirkus and 'members' in zirkus
    one = tool(api, world['admin'], 'get_dataset', dataset_id='dbu_zirkus')
    assert one['id'] == 'dbu_zirkus' and one['visibility'] == 'members' and one['reviewed'] is True


def test_the_timeline_lists_events_in_order(api, world):
    answer = tool(api, world['admin'], 'get_timeline', component_id=iid('beam'))
    kinds = [e['kind'] for e in answer['events']]
    assert kinds and all(isinstance(e['at'], str) for e in answer['events'])
    assert answer['web_link'] == f'{WEB}/components/{iid("beam")}'
    assert set(answer['events'][0]) == {'kind', 'at', 'precision', 'section', 'cycle', 'planned', 'detail'}


# SIMILAR COMPONENTS (8.174) --------------------------------------------------------------------
def put_matrix(db, vectors, basis='radial_signature'):
    """A stored similarity matrix of the test catalog: one row per name, the
    vectors taken as the standardised ones (mean 0, standard deviation 1)."""
    import numpy as np
    from apps.catalog import similarity as sim
    names = list(vectors)
    z = np.asarray([vectors[n] for n in names], dtype=np.float32)
    dim = z.shape[1]
    matrix = sim.FeatureMatrix(basis, [iid(n) for n in names], z, np.zeros(dim), np.ones(dim),
                               '2026-10-20T00:00:00Z', build_id=uuid.uuid4().hex)
    db['component_map_cache'].replace_one(
        {'_id': sim.knn_doc_id(basis)}, sim.matrix_to_doc(matrix, '2026-10-20T00:00:00Z'), upsert=True)


NEAR_BEAM = {'beam': [0.0, 0.0], 'feld': [1.0, 0.0], 'stone': [-2.0, 0.0], 'cut2': [3.0, 4.0], 'panel': [10.0, 0.0]}


def test_similar_components_are_the_nearest_in_descriptor_space_with_their_distance(api, db, world):
    put_matrix(db, NEAR_BEAM)
    answer = tool(api, world['admin'], 'similar_components', component_id=iid('beam'), count=3, circulation='all')
    assert [s['name'] for s in answer['similar']] == ['feld', 'stone', 'cut2']
    assert [s['descriptor_distance'] for s in answer['similar']] == [1.0, 2.0, 5.0]
    assert answer['basis'] == 'radial_signature' and answer['matrix_built'] == '2026-10-20T00:00:00Z'
    assert 'standardised' in answer['distance_unit'] and 'not metres' in answer['distance_unit']
    assert answer['similar'][0]['web_link'] == f'{WEB}/components/{iid("feld")}'
    assert all('distance_km' not in s and 'fit' not in s for s in answer['similar'])
    # the piece itself is never one of its neighbours; the rows are the short rows of the search
    everyone = tool(api, world['admin'], 'similar_components', component_id=iid('beam'), count=1000, circulation='all')['similar']
    assert iid('beam') not in str(everyone)
    assert {'id', 'catalog_number', 'original_function', 'material', 'dataset', 'visibility'} <= set(everyone[0])


def test_the_filters_apply_before_the_ranking(api, db, world):
    _sized(db)
    put_matrix(db, NEAR_BEAM)
    admin = world['admin']
    # feld and stone are nearer, but only cut2 is in this dataset: it is the nearest that passes
    ddu = tool(api, admin, 'similar_components', component_id=iid('beam'), count=1, dataset='ddu_aggregations')
    assert [s['name'] for s in ddu['similar']] == ['cut2'] and ddu['compared_with'] == 1
    # similar in shape and able to hold 400 x 300 x 200: beam (3000 x 200 x 100) is too thin, feld and cut2 pass
    held = tool(api, admin, 'similar_components', component_id=iid('beam'), count=5,
                fit_mode='can_hold', size_mm=[400, 300, 200])
    assert [s['name'] for s in held['similar']] == ['feld', 'cut2'] and held['compared_with'] == 2
    # a place search filters too: only the two pieces near Darmstadt
    _placed(db, {'feld': DARMSTADT, 'cut2': BERLIN, 'stone': DARMSTADT})
    near = tool(api, admin, 'similar_components', component_id=iid('beam'), count=5, circulation='all',
                near_lat=49.87, near_lon=8.65, radius_km=30)
    assert [s['name'] for s in near['similar']] == ['feld', 'stone']


def test_similar_components_refuse_in_words(api, db, world, plain):
    admin = world['admin']
    is_error, text = tool_result(api, admin, 'similar_components', component_id=iid('beam'))
    assert is_error and 'not been computed' in text                       # no matrix yet
    put_matrix(db, NEAR_BEAM)
    for args, words in (({'basis': 'tsne'}, 'basis is'),
                        ({'fit_mode': 'about'}, 'size_mm'),
                        ({'near_lat': 49.0}, 'both or neither')):
        is_error, text = tool_result(api, admin, 'similar_components', component_id=iid('beam'), **args)
        assert is_error and words in text, (args, text)
    # a piece the matrix does not have and whose version has no descriptor
    is_error, text = tool_result(api, admin, 'similar_components', component_id=iid('cut'))
    assert is_error and 'descriptor' in text
    is_error, text = tool_result(api, admin, 'similar_components', component_id='3f2c0c86-6b5b-4a6a-8b7e-0d9d3a2d6e11')
    assert is_error and 'Not found' in text


def _visible(api, pat, **args):
    """The pieces an account sees, as the search tool lists them (visibility is the list's)."""
    found = tool(api, pat, 'search_components', size=25, **args)
    return {r['id']: r for r in found['results']}, found['total']


def test_similar_components_never_show_what_the_account_may_not_see(api, db, world, plain, dataset_member):
    put_matrix(db, NEAR_BEAM)
    admin = tool(api, world['admin'], 'similar_components', component_id=iid('cut2'), circulation='all')
    assert iid('beam') in str(admin)
    for who in (plain, dataset_member):
        seen, _ = _visible(api, who['pat'], circulation='all', status='any')
        hidden = [iid(n) for n in NEAR_BEAM if iid(n) not in seen]
        assert hidden, 'the test needs a piece this account may not see'
        for name in NEAR_BEAM:
            piece = iid(name)
            if piece in hidden:
                is_error, text = tool_result(api, who['pat'], 'similar_components', component_id=piece)
                assert is_error and 'Not found' in text, name
            else:
                answer = tool(api, who['pat'], 'similar_components', component_id=piece, circulation='all',
                              status='any')
                assert {r['id'] for r in answer['similar']} <= set(seen) - {piece}
                assert not set(hidden) & {r['id'] for r in answer['similar']}
                assert answer['compared_with'] <= len(seen) - 1


def test_similar_components_are_described_in_standardised_units(api, world):
    tools = mcp_post(api, world['admin'], 'tools/list').json()['result']['tools']
    similar = next(t for t in tools if t['name'] == 'similar_components')
    assert 'standardised' in similar['description'] and 'not metres or millimetres' in similar['description']
    assert 'not on the similarity map' in similar['description']       # said as the contrast
    properties = similar['inputSchema']['properties']
    for name in ('basis', 'count', 'query', 'dataset', 'fit_mode', 'size_mm', 'near_lat', 'radius_km'):
        assert name in properties, name
    assert 'method' not in properties                      # the 2D map is nowhere in this tool


# THE OVERVIEW (8.173) --------------------------------------------------------------------------
def test_the_overview_counts_the_catalog_with_labels_ranges_and_coverage(api, db, world):
    _sized(db)
    _placed(db, {'beam': DARMSTADT, 'feld': FRANKFURT}, {'beam': BERLIN})
    answer = tool(api, world['admin'], 'catalog_overview')
    assert answer['total'] == 3 and answer['pieces'] >= 3
    assert sum(r['count'] for r in answer['by_dataset']) == 3
    assert {r['key'] for r in answer['by_dataset']} == {'dbu_zirkus', 'ddu_aggregations', 'schoenes_neues_feld'}
    for facet in ('by_material', 'by_original_function', 'by_shape_class', 'by_circulation'):
        assert sum(r['count'] for r in answer[facet]) == 3, facet
    assert all(r['label'] for r in answer['by_material'])         # materials come with their label
    assert 'Beam' in {r['label'] for r in answer['by_original_function']} or answer['by_original_function']
    # sides sorted largest, middle, smallest, in mm: beam 3000 x 200 x 100, cut2 1000 x 500 x 300, feld 500^3
    ranges = answer['side_ranges_mm']
    assert ranges['components_with_a_size'] == 3
    assert ranges['largest_side'] == {'min': 500, 'max': 3000}
    assert ranges['middle_side'] == {'min': 200, 'max': 500}
    assert ranges['smallest_side'] == {'min': 100, 'max': 500}
    assert answer['with_location'] == {'current': 2, 'origin': 1}
    # the administrator sees every piece; the private ones are counted as not public
    seen, total = _visible(api, world['admin'])
    private = sum(1 for r in seen.values() if r['visibility'] == 'private')
    assert total == 3 and answer['not_public'] == private
    assert f'{private} of the 3' in answer['note'] or private == 0


def test_the_overview_follows_the_filters_of_the_search(api, db, world):
    _sized(db)
    admin = world['admin']
    one = tool(api, admin, 'catalog_overview', dataset='ddu_aggregations')
    assert one['total'] == 1 and one['filters'] == {'dataset': 'ddu_aggregations', 'circulation': 'active',
                                                    'status': 'published'}
    assert one['side_ranges_mm']['largest_side'] == {'min': 1000, 'max': 1000}
    held = tool(api, admin, 'catalog_overview', fit_mode='can_hold', size_mm=[400, 300, 200])
    assert held['total'] == 2                                     # beam is too thin
    assert held['side_ranges_mm']['smallest_side'] == {'min': 300, 'max': 500}
    nothing = tool(api, admin, 'catalog_overview', query='no such piece zzz')
    assert nothing['total'] == 0 and nothing['side_ranges_mm']['largest_side'] is None
    assert nothing['with_location'] == {'current': 0, 'origin': 0}
    is_error, text = tool_result(api, admin, 'catalog_overview', fit_mode='about')
    assert is_error and 'size_mm' in text


def test_the_overview_counts_only_what_the_account_may_see(api, db, world, plain, dataset_member):
    _sized(db)
    for who in (plain, dataset_member):
        seen, total = _visible(api, who['pat'])
        overview = tool(api, who['pat'], 'catalog_overview')
        # the same pieces as the list, and the non-public ones named
        assert overview['total'] == total
        assert overview['not_public'] == sum(1 for r in seen.values() if r['visibility'] == 'private')
        assert sum(r['count'] for r in overview['by_dataset']) == total
        assert ('dbu_zirkus' in {r['key'] for r in overview['by_dataset']}) == (iid('beam') in seen)
    # a member of dbu_zirkus sees its beam, which is not public; the account without a role does not
    assert tool(api, dataset_member['pat'], 'catalog_overview', dataset='dbu_zirkus')['total'] == 1
    assert tool(api, plain['pat'], 'catalog_overview', dataset='dbu_zirkus')['total'] == 0
    only = tool(api, dataset_member['pat'], 'catalog_overview', dataset='dbu_zirkus')
    assert only['not_public'] == 1
    assert only['side_ranges_mm']['largest_side'] == {'min': 3000, 'max': 3000}
    # once it is public it counts as public
    db['component_identities'].update_one({'_id': iid('beam')}, {'$set': {'is_public': True}})
    assert tool(api, dataset_member['pat'], 'catalog_overview', dataset='dbu_zirkus')['not_public'] == 0


def test_the_overview_is_described_and_takes_the_search_filters(api, world):
    tools = mcp_post(api, world['admin'], 'tools/list').json()['result']['tools']
    overview = next(t for t in tools if t['name'] == 'catalog_overview')
    for word in ('millimetres', 'not public', 'origin location', 'material'):
        assert word in overview['description'], word
    search = next(t for t in tools if t['name'] == 'search_components')
    shared = ('query', 'original_function', 'material', 'dataset', 'shape_class', 'circulation', 'status',
              'include_withdrawn', 'has_evidence', 'fit_mode', 'size_mm', 'tolerance', 'near_lat', 'near_lon',
              'near_layer', 'radius_km')
    for name in shared:
        assert overview['inputSchema']['properties'][name] == search['inputSchema']['properties'][name], name


# 0.6.4.1: A SERVER A MODEL RECOGNIZES, SEARCH BY EVIDENCE METHOD (8.177) -----------------------------
def test_the_server_names_the_domain_in_english_and_german_and_has_a_home_and_an_icon(api, world):
    response = mcp_post(api, world['admin'], 'initialize', {
        'protocolVersion': '2025-06-18', 'capabilities': {},
        'clientInfo': {'name': 'test', 'version': '1'}})
    info = response.json()['result']['serverInfo']
    assert info['websiteUrl'] == WEB
    assert [i['src'] for i in info['icons']] == [f'{WEB}/favicon.ico']
    text = response.json()['result']['instructions']
    for word in ('reused and salvaged building components', 'Bauteile', 'Wiederverwendung', 'Bauteilboerse',
                 'Betonwaende', 'Traeger', 'Bewehrung', 'reinforcement', 'stone', 'timber', 'before a web search',
                 'has_evidence=reinforcement_layout'):
        assert word in text, word
    assert text.isascii()


def test_every_tool_has_a_title_and_says_it_only_reads_the_catalog(api, world):
    listed = mcp_post(api, world['admin'], 'tools/list').json()['result']['tools']
    assert {t['name'] for t in listed} == TOOLS
    for entry in listed:
        assert entry['title'] and entry['title'] != entry['name'], entry['name']
        hints = entry['annotations']
        assert hints['readOnlyHint'] is True and hints['openWorldHint'] is False, entry['name']
        assert hints['idempotentHint'] is True, entry['name']
    assert len({t['title'] for t in listed}) == len(listed)


def test_the_evidence_methods_are_named_for_the_model_from_the_vocabulary(api, world):
    from apps.catalog.vocab import EVIDENCE_METHODS
    listed = mcp_post(api, world['admin'], 'tools/list').json()['result']['tools']
    by_name = {t['name']: t for t in listed}
    for method in EVIDENCE_METHODS:
        assert method in by_name['get_evidence']['description'], method
        for name in ('search_components', 'catalog_overview', 'similar_components'):
            assert method in by_name[name]['inputSchema']['properties']['has_evidence']['description'], (name, method)
    assert 'reinforcement' in by_name['search_components']['inputSchema']['properties']['has_evidence']['description']


def _layout_for(db, name, status='pending', **changes):
    """A copy of the migrated reinforcement layout of the beam, for another piece."""
    doc = db['component_evidence'].find_one({'method': 'reinforcement_layout'})
    doc.update({'_id': str(uuid.uuid4()), 'identity_id': iid(name), 'status': status, **changes})
    doc['position'] = {**doc['position'], 'snapshot_id': sid(name)}
    db['component_evidence'].insert_one(doc)
    return doc['_id']


def test_has_evidence_lists_the_pieces_with_a_published_record_of_that_method(api, db, world):
    admin = world['admin']
    answer = tool(api, admin, 'search_components', has_evidence='reinforcement_layout')
    assert _names(answer) == ['beam'] and answer['total'] == 1
    assert _names(tool(api, admin, 'search_components', has_evidence='visual_inspection')) == ['feld']
    assert tool(api, admin, 'search_components', has_evidence='core_compression')['total'] == 0
    assert tool(api, admin, 'search_components')['total'] == 3             # no filter: as before


def test_a_piece_with_only_a_pending_layout_is_not_found_by_has_evidence(api, db, world):
    pending = _layout_for(db, 'feld', status='pending')
    admin = world['admin']
    assert _names(tool(api, admin, 'search_components', has_evidence='reinforcement_layout')) == ['beam']
    db['component_evidence'].update_one({'_id': pending}, {'$set': {'status': 'published'}})
    assert _names(tool(api, admin, 'search_components', has_evidence='reinforcement_layout',
                       sort='catalog_number')) == ['beam', 'feld']


def test_has_evidence_combines_with_the_other_filters(api, db, world):
    _sized(db)
    admin = world['admin']
    _layout_for(db, 'feld', status='published')
    assert tool(api, admin, 'search_components', has_evidence='reinforcement_layout', dataset='dbu_zirkus')['total'] == 1
    assert tool(api, admin, 'search_components', has_evidence='reinforcement_layout', dataset='ddu_aggregations')['total'] == 0
    both = tool(api, admin, 'search_components', has_evidence='reinforcement_layout', fit_mode='can_hold',
                size_mm=[400, 300, 200])
    assert _names(both) == ['feld']                                        # beam is too thin
    _placed(db, {'beam': DARMSTADT, 'feld': BERLIN})
    near = tool(api, admin, 'search_components', has_evidence='reinforcement_layout', near_lat=49.87, near_lon=8.65,
                radius_km=30)
    assert _names(near) == ['beam'] and near['total'] == 1


def test_has_evidence_follows_what_the_account_may_see(api, db, world, plain, dataset_member):
    assert tool(api, plain['pat'], 'search_components', has_evidence='reinforcement_layout')['total'] == 0
    assert _names(tool(api, dataset_member['pat'], 'search_components', has_evidence='reinforcement_layout')) == ['beam']


def test_has_evidence_refuses_an_unknown_method_in_words(api, world):
    is_error, text = tool_result(api, world['admin'], 'search_components', has_evidence='x_ray')
    assert is_error and 'has_evidence is one of' in text and 'reinforcement_layout' in text
    for name, args in (('catalog_overview', {}), ('similar_components', {'component_id': iid('beam')})):
        assert tool_result(api, world['admin'], name, has_evidence='x_ray', **args)[0] is True


def test_the_overview_and_the_similar_pieces_take_has_evidence(api, db, world):
    admin = world['admin']
    overview = tool(api, admin, 'catalog_overview', has_evidence='reinforcement_layout')
    assert overview['total'] == 1 and overview['filters']['evidence_method'] == 'reinforcement_layout'
    assert [r['key'] for r in overview['by_dataset']] == ['dbu_zirkus']
    assert tool(api, admin, 'catalog_overview')['total'] == 3
    put_matrix(db, NEAR_BEAM)
    # feld, stone and cut2 are nearer than panel, but only the pieces with a layout are ranked
    _layout_for(db, 'cut2', status='published')
    similar = tool(api, admin, 'similar_components', component_id=iid('feld'), count=5, circulation='all',
                   has_evidence='reinforcement_layout')
    assert [s['name'] for s in similar['similar']] == ['beam', 'cut2'] and similar['compared_with'] == 2
    unfiltered = tool(api, admin, 'similar_components', component_id=iid('feld'), count=5, circulation='all')
    assert len(unfiltered['similar']) > 2


def test_a_superseded_layout_does_not_count_for_has_evidence(api, db, world):
    admin = world['admin']
    layout = db['component_evidence'].find_one({'identity_id': iid('beam'), 'method': 'reinforcement_layout'})
    # a correction replaces the layout: the old record stays published but is superseded
    db['component_evidence'].update_one({'_id': layout['_id']}, {'$set': {'superseded_by': str(uuid.uuid4())}})
    assert tool(api, admin, 'search_components', has_evidence='reinforcement_layout')['total'] == 0
    assert tool(api, admin, 'catalog_overview', has_evidence='reinforcement_layout')['total'] == 0
    put_matrix(db, NEAR_BEAM)
    assert tool(api, admin, 'similar_components', component_id=iid('feld'), count=5, circulation='all',
                has_evidence='reinforcement_layout')['similar'] == []
    # a current record next to the superseded one brings the piece back
    _layout_for(db, 'beam', status='published', superseded_by=None)
    assert _names(tool(api, admin, 'search_components', has_evidence='reinforcement_layout')) == ['beam']
    assert tool(api, admin, 'catalog_overview', has_evidence='reinforcement_layout')['total'] == 1


# 0.6.4.1: REINFORCEMENT IS EVIDENCE, NOT GEOMETRY (7.8) ---------------------------------------------
def test_the_geometry_summary_has_no_reinforcement_count_any_more():
    summary = mcp_server.geometry_summary({'meshes': [{'vertices': [[0, 0, 0]], 'faces': []}],
                                           'reinforcements': [{'spec': 'x'}]})
    assert 'reinforcements' not in summary and summary['meshes'] == 1


def test_a_version_reports_its_reinforcement_layouts_from_the_evidence(api, db, world):
    admin = world['admin']
    component = tool(api, admin, 'get_component', component_id=iid('beam'))
    layouts = component['current_version']['reinforcement_layouts']
    assert layouts['records'] == 1 and layouts['bars'] == 1
    assert 'get_evidence' in layouts['note'] and 'reinforcement_layout' in layouts['note']
    assert 'reinforcements' not in component['current_version']['geometry']
    assert 'Geometry is not sent' in component['current_version']['geometry']['note']
    now = tool(api, admin, 'get_version', version_id=sid('beam', 1))
    assert now['reinforcement_layouts']['records'] == 1 and now['reinforcement_layouts']['bars'] == 1
    assert 'reinforcements' not in now['geometry']
    # the layout names version 1: the version before it has none
    before = tool(api, admin, 'get_version', version_id=sid('beam', 0))
    assert before['reinforcement_layouts']['records'] == 0 and before['reinforcement_layouts']['bars'] == 0
    plain_piece = tool(api, admin, 'get_component', component_id=iid('feld'))
    assert plain_piece['current_version']['reinforcement_layouts']['records'] == 0


def test_a_pending_layout_is_not_counted_and_two_records_add_their_bars(api, db, world):
    admin = world['admin']
    pending = _layout_for(db, 'beam', status='pending')
    db['component_evidence'].update_one({'_id': pending}, {'$set': {'position.snapshot_id': sid('beam', 1)}})
    assert tool(api, admin, 'get_version', version_id=sid('beam', 1))['reinforcement_layouts']['records'] == 1
    db['component_evidence'].update_one({'_id': pending}, {'$set': {'status': 'published'}})
    counted = tool(api, admin, 'get_version', version_id=sid('beam', 1))['reinforcement_layouts']
    assert counted['records'] == 2 and counted['bars'] == 2


def test_the_layout_helper_counts_published_records_of_the_version_only():
    def record(snapshot, bars, status='published', method='reinforcement_layout'):
        return {'method': method, 'status': status, 'position': {'snapshot_id': snapshot},
                'payload': {'bars': [{}] * bars}}
    rows = [record('a', 3), record('a', 2), record('b', 7), record('a', 9, status='pending'),
            record('a', 5, method='visual_inspection'), {'method': 'reinforcement_layout', 'status': 'withdrawn'}]
    assert mcp_server.layouts_of_version(rows, 'a')['records'] == 2
    assert mcp_server.layouts_of_version(rows, 'a')['bars'] == 5
    assert mcp_server.layouts_of_version(rows, 'c')['records'] == 0
    assert mcp_server.layouts_of_version(None, 'a')['bars'] == 0


def test_a_layout_row_carries_a_summary_of_its_bars(api, db, world):
    admin = world['admin']
    layout = db['component_evidence'].find_one({'method': 'reinforcement_layout'})
    bars = [{'spec': 'BSt III', 'diameter_mm': 8, 'points': [[0, 0, 0], [1, 0, 0]]},
            {'spec': 'BSt III', 'diameter_mm': 12, 'cover_mm': 25, 'points': [[0, 0, 0], [1, 0, 0]]},
            {'spec': 'BSt I', 'diameter_mm': 8, 'cover_mm': 40, 'points': [[0, 0, 0], [1, 0, 0]]}]
    db['component_evidence'].update_one({'_id': layout['_id']}, {'$set': {'payload.bars': bars}})
    row = tool(api, admin, 'get_evidence', component_id=iid('beam'), method='reinforcement_layout')['evidence'][0]
    assert row['reinforcement'] == {'bars': 3, 'basis': 'drawing', 'specs': ['BSt I', 'BSt III'],
                                    'diameters_mm': [8.0, 12.0], 'cover_mm': {'min': 25, 'max': 40},
                                    'version_id': sid('beam', 1)}
    assert 'payload' not in row and 'points' not in json.dumps(row)
    full = tool(api, admin, 'get_evidence', evidence_id=row['id'])
    assert len(full['record']['payload']['bars']) == 3
    # the other methods have no such summary
    other = tool(api, admin, 'get_evidence', component_id=iid('feld'))['evidence']
    assert other and all('reinforcement' not in r for r in other)


def test_performed_by_shows_a_name_else_the_organization_never_null(api, db, world):
    layout = db['component_evidence'].find_one({'method': 'reinforcement_layout'})
    db['component_evidence'].update_one({'_id': layout['_id']}, {'$set': {'performed_by': [
        {'kind': 'person', 'name': 'Ada Example', 'organization': 'Example Institute'},
        {'kind': 'organization', 'organization': 'Example Laboratory'}]}})
    row = tool(api, world['admin'], 'get_evidence', component_id=iid('beam'))['evidence'][0]
    assert row['performed_by'] == ['Ada Example', 'Example Laboratory']
    assert None not in row['performed_by']


def test_performers_leaves_out_an_actor_with_neither_name_nor_organization():
    record = {'performed_by': [{'kind': 'user', 'user_id': 'abc'}, {'kind': 'person', 'name': 'Ada'}, 'x', None,
                               {'kind': 'organization', 'organization': 'Lab'}]}
    assert mcp_server.performers(record) == ['Ada', 'Lab']
    assert mcp_server.performers({}) == []


def test_no_address_or_account_id_leaks_through_the_layout_and_performer_fields(api, db, world):
    layout = db['component_evidence'].find_one({'method': 'reinforcement_layout'})
    db['component_evidence'].update_one({'_id': layout['_id']}, {'$set': {'performed_by': [
        {'kind': 'person', 'name': 'Ada ada@example.org', 'email': 'ada@example.org'}]}})
    text = json.dumps([tool(api, world['admin'], 'get_evidence', component_id=iid('beam')),
                       tool(api, world['admin'], 'get_component', component_id=iid('beam'))])
    assert not EMAIL.search(text)
