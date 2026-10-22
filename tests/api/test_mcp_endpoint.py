"""
The read-only MCP layer (decisions 8.165, 8.168): the endpoint behind the access
tokens, the nine tools on a migrated catalog (what the owner of the token sees on
the website, nothing private for anyone else, every non-public record marked, no
e-mail address or account id), the maintenance flag and the limits.
"""

from __future__ import annotations

import json
import re

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
         'similar_components'}
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


def test_exactly_these_nine_tools_exist_and_each_explains_itself(api, world):
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
    assert held['results'][0]['fit'] == {'mode': 'can_hold', 'waste_dm3': 101.0}
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
    row = {'fit': {'mode': 'can_hold', 'waste_mm3': 12_400_000}, 'quantity': 4}
    assert mcp_server.fit_of(row) == {'mode': 'can_hold', 'waste_dm3': 12.4, 'per_piece': True}
    assert 'per_piece' not in mcp_server.fit_of({**row, 'quantity': 1})
    assert 'per_piece' not in mcp_server.fit_of(
        {'fit': {'mode': 'about', 'deviation': 0.1}, 'quantity': 4})


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
                               'reinforcements': 0, 'note': 'Geometry is not sent; open the web link to see it.'}
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


# SIMILAR COMPONENTS ----------------------------------------------------------------------------
def put_map(db, method='umap', points=None):
    db['component_map_cache'].insert_one({
        '_id': cache_doc_id('radial_signature', method), 'basis': 'radial_signature', 'method': method,
        'basis_label': 'Radial signature', 'total': len(points), 'displayed': len(points),
        'computed_at': '2026-10-20T00:00:00Z', 'points': points})


def point(name, x, y):
    return {'id': iid(name), 'x': x, 'y': y, 'name': name, 'original_function': 'IfcBeam',
            'catalog_number': 1, 'in_place': False, 'color': None, 'dataset': 'ddu', 'material': 'concrete',
            'shape_class': 'planar'}


def test_similar_components_are_the_nearest_on_the_map_with_their_distance(api, db, world):
    put_map(db, points=[point('beam', 0.0, 0.0), point('cut2', 3.0, 4.0), point('feld', 1.0, 0.0),
                        point('panel', 10.0, 0.0), point('stone', -2.0, 0.0)])
    answer = tool(api, world['admin'], 'similar_components', component_id=iid('beam'), count=3)
    assert [s['name'] for s in answer['similar']] == ['feld', 'stone', 'cut2']
    assert [s['distance'] for s in answer['similar']] == [1.0, 2.0, 5.0]
    assert answer['layout'] == 'umap' and answer['basis'] == 'Radial signature'
    assert answer['similar'][0]['web_link'] == f'{WEB}/components/{iid("feld")}'
    assert tool(api, world['admin'], 'similar_components', component_id=iid('beam'), count=1000)['similar'].__len__() == 4


def test_similar_components_say_when_there_is_nothing_to_compare(api, db, world):
    put_map(db, points=[point('beam', 0.0, 0.0)])
    is_error, text = tool_result(api, world['admin'], 'similar_components', component_id=iid('feld'))
    assert is_error and 'not on the similarity map' in text
    assert tool_result(api, world['admin'], 'similar_components', component_id=iid('beam'), method='tsne')[0]
    is_error, text = tool_result(api, world['admin'], 'similar_components', component_id=iid('beam'), method='pca')
    assert is_error                                       # no pca layout cached


def test_the_map_only_holds_what_the_account_may_see(api, db, world, plain):
    put_map(db, points=[point('beam', 0.0, 0.0), point('cut2', 1.0, 0.0), point('feld', 2.0, 0.0)])
    admin = tool(api, world['admin'], 'similar_components', component_id=iid('cut2'))
    assert iid('beam') in str(admin)
    for_plain = tool_result(api, plain['pat'], 'similar_components', component_id=iid('cut2'))
    assert iid('beam') not in str(for_plain)
