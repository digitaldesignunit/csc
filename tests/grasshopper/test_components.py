"""The script components run outside Grasshopper (compstub): builders, Add
components over a fake Session core, and the Session itself."""

from __future__ import annotations

import base64
import inspect
import json
import os
import types

import pytest

import compstub
from csc_gh import build as b
from csc_gh import upload as up
from test_upload import FakeCore, Response

UUID_A = '11111111-1111-4111-8111-111111111111'
UUID_B = '22222222-2222-4222-8222-222222222222'


def run(name, *args, **kwargs):
    """Load a component, run it, return ``(result, instance, module)``."""
    module = compstub.load_component(name, sticky=kwargs.pop('sticky', None))
    obj = compstub.instance(module, name)
    return obj.RunScript(*args, **kwargs), obj, module


# BUILDERS --------------------------------------------------------------------
def test_actor_component():
    result, obj, _ = run('Actor', None, None, 'Ada', 'Lab GmbH', None, None,
                         None, 'operator')
    assert json.loads(result) == b.actor(name='Ada', organization='Lab GmbH',
                                         role='operator')
    assert compstub.messages(obj)['error'] == []
    bad, obj, _ = run('Actor', 'user', None, None, None, None, None, None,
                      None)
    assert bad == '' and 'UserID' in compstub.messages(obj)['error'][0]


def test_origin_component_takes_a_location_vector():
    place = types.SimpleNamespace(X=49.8, Y=8.6)
    result, obj, _ = run('Origin', 'deinstallation', '2024-05', None, 'Hall',
                         None, place, 'Hall 3', '1974', None, None, None,
                         [json.dumps(b.actor(name='Ada'))], 'n', 'Axis B/3', False)
    block = json.loads(result)
    assert block['place']['location'] == {'lat': 49.8, 'lon': 8.6}
    assert block['at_precision'] == 'month'
    assert block['performed_by'][0]['name'] == 'Ada'
    assert block['position_in_work'] == 'Axis B/3'
    # the position is optional (8.100 d) and an empty text is none
    result, _, _ = run('Origin', 'deinstallation', None, None, None, None,
                       None, 'Hall 3', None, None, None, None, [], None, '', False)
    assert 'position_in_work' not in json.loads(result)
    bad, obj, _ = run('Origin', 'offcut', None, None, None, None, None,
                      'A hall', None, None, None, None, [], None, None, False)
    assert bad == '' and compstub.messages(obj)['error']


def test_origin_component_plans_a_deinstallation():
    """Planned: the piece is still in place (8.104); At is then optional."""
    result, obj, _ = run('Origin', 'deinstallation', None, None, 'Hall', None,
                         None, 'Hall 3', None, None, None, None, [], None,
                         None, True)
    block = json.loads(result)
    assert block['planned'] is True and 'at' not in block
    assert compstub.messages(obj)['error'] == []
    # a planned date is a date
    result, _, _ = run('Origin', 'demolition', '2027-03', None, None, None,
                       None, None, None, None, None, None, [], None, None,
                       True)
    assert json.loads(result)['at_precision'] == 'month'
    # not planned: the key stays out of the block
    result, _, _ = run('Origin', 'deinstallation', None, None, None, None,
                       None, None, None, None, None, None, [], None, None,
                       False)
    assert 'planned' not in json.loads(result)
    # only a deinstallation or a demolition can be planned
    bad, obj, _ = run('Origin', 'offcut', None, None, None, None, None, None,
                      None, None, None, None, [], None, None, True)
    assert bad == '' and 'Planned' in compstub.messages(obj)['error'][0]


def test_metadata_components_and_capture_component():
    origin = json.dumps(b.origin('surplus', '2020'))
    result, _, _ = run('IdentityMetadata', 'IfcBeam', 'concrete', None, None,
                       '2001', origin, True, None, None, None)
    meta = json.loads(result)
    assert meta['original_function'] == 'IfcBeam' and meta['is_public']
    assert meta['origin']['kind'] == 'surplus'
    assert meta['manufactured_precision'] == 'year'          # from the date
    # ManufacturedPrecision is an input now (8.100 d): it overrides the date
    result, obj, _ = run('IdentityMetadata', 'IfcBeam', None, None, None,
                         '2001-05', None, None, None, None, 'unknown')
    assert json.loads(result)['manufactured_precision'] == 'unknown'
    bad, obj, _ = run('IdentityMetadata', 'IfcBeam', None, None, None,
                      '2001', None, None, None, None, 'soon')
    assert bad == '' and 'ManufacturedPrecision' in \
        compstub.messages(obj)['error'][0]
    colour = types.SimpleNamespace(R=1, G=2, B=3)
    where = types.SimpleNamespace(X=1.0, Y=2.0)
    result, _, _ = run('SnapshotMetadata', 'Lintel', True, 2, colour, where,
                       'n', '2024-05-03', None, None, None)
    assert json.loads(result) == b.snapshot_metadata(
        'Lintel', True, 2, [1, 2, 3], 1.0, 2.0, 'n', '2024-05-03')
    # EffectiveFromPrecision is an input now (8.100 d); the message of a
    # bad value names the port, not the older label of the library
    result, _, _ = run('SnapshotMetadata', 'Lintel', None, None, None, None,
                       None, '2024-05-03', None, None, 'month')
    assert json.loads(result)['effective_from_precision'] == 'month'
    bad, obj, _ = run('SnapshotMetadata', 'Lintel', None, None, None, None,
                      None, '2024-05-03', None, None, 'soon')
    error = compstub.messages(obj)['error'][0]
    assert bad == '' and 'EffectiveFromPrecision' in error
    assert 'EffectivePrecision' not in error.replace(
        'EffectiveFromPrecision', '')
    points = [types.SimpleNamespace(X=0, Y=0, Z=0),
              types.SimpleNamespace(X=1, Y=2, Z=3)]
    result, obj, _ = run('Capture', 'lidar', None, None, None, None,
                         'gripper plane', None, points, ['a', 'b'],
                         ['rig', 'component'], ['effector|e.ply'])
    block = json.loads(result)
    assert [m['role'] for m in block['markers']] == ['rig', 'component']
    assert block['fixtures'] == [{'label': 'effector', 'file': 'e.ply'}]
    bad, obj, _ = run('Capture', None, None, None, None, None, None, None,
                      points, ['only one'], None, None)
    assert bad == '' and 'MarkerLabel' in compstub.messages(obj)['error'][0]


# ADD COMPONENTS --------------------------------------------------------------
def _identity_request(tmp_path, module, files=True):
    mesh = b.inline_mesh([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]])
    snapshot = b.snapshot_body(None, b.geometry_body([mesh]))
    body = b.identity_body(UUID_A, 'ds', json.dumps(
        b.identity_metadata('IfcBeam', 'concrete')), snapshot)
    text_json = json.dumps(body, sort_keys=True)
    root = tmp_path / 'staging'
    compstub.patch_library(module, 'staging_root', lambda: str(root))
    if files:
        tmp = root / '_tmp'
        (tmp / 'meshes' / '0').mkdir(parents=True)
        (tmp / 'meshes' / '0' / 'detailed.ply').write_bytes(b'ply-d0')
        (tmp / 'meshes' / '0' / 'reduced.ply').write_bytes(b'ply-r0')
        up.commit_staging(str(tmp), b.staging_key(text_json),
                          b.manifest({0: ['detailed', 'reduced']}),
                          str(root))
    return text_json


CREATED = {'identity': {'_id': UUID_A, 'catalog_number': 7},
           'snapshot': {'_id': UUID_B, 'status': 'draft', 'version': 0}}


def _core(answers=None):
    base = {
        ('POST', '/identities'): Response(201, CREATED),
        ('POST', '/component_id_transmission/consume'):
            Response(200, {'consumed': True}),
        ('GET', '/identities/%s/compose' % UUID_A): Response(200, {
            'identity': CREATED['identity'],
            'snapshots': [{'_id': UUID_B, 'status': 'draft'}]}),
    }
    base.update(answers or {})
    return FakeCore(base)


def _run_add_identity(tmp_path, core, run_=True, files=True):
    module = compstub.load_component(
        'AddComponentIdentity', sticky={'CSC_AuthCore': core})
    core.is_valid = lambda: True
    obj = compstub.instance(module, 'AddComponentIdentity')
    request = _identity_request(tmp_path, module, files)
    tree = obj.RunScript(request, run_)
    return tree, obj, request


def test_add_identity_creates_uploads_and_consumes_and_stays_a_draft(
        tmp_path):
    core = _core()
    tree, obj, request = _run_add_identity(tmp_path, core)
    calls = [(c[0], c[1]) for c in core.calls]
    assert calls == [
        ('POST', '/identities'),
        ('POST', '/component_id_transmission/consume'),
        ('PUT', '/snapshots/%s/meshes/0/detailed' % UUID_B),
        ('PUT', '/snapshots/%s/meshes/0/reduced' % UUID_B),
        ('GET', '/identities/%s/compose' % UUID_A)]
    assert core.calls[0][2] == json.loads(request)        # the body as made
    passport = json.loads(tree.values[0])
    assert passport['snapshots'][0]['status'] == 'draft'
    assert compstub.messages(obj)['error'] == []
    assert 'draft' in obj.Component.Message


def test_add_identity_has_no_submit_or_publish_input_and_never_calls_them(
        tmp_path):
    """Everything from Grasshopper is a draft (8.127; 8.120: nobody
    publishes directly)."""
    core = _core()
    tree, _, _ = _run_add_identity(tmp_path, core)
    assert not any(c[1].endswith(('/submit', '/publish')) for c in core.calls)
    assert json.loads(tree.values[0])['snapshots'] is not None
    module = compstub.load_component('AddComponentIdentity')
    names = module.CSC_AddComponentIdentity.RunScript.__code__.co_varnames
    assert 'Submit' not in names and 'Publish' not in names


def test_add_identity_without_run_only_checks(tmp_path):
    core = _core()
    tree, obj, _ = _run_add_identity(tmp_path, core, run_=False)
    assert core.calls == [] and tree.DataCount == 0
    assert obj.Component.Message == 'Run is False'
    # the staged files are told as a remark, the state is one short text
    assert compstub.messages(obj)['error'] == []


def test_add_identity_tells_about_a_failed_upload_and_keeps_the_draft(
        tmp_path):
    core = _core({('PUT', '/snapshots/%s/meshes/0/reduced' % UUID_B):
                    Response(400, {'detail': 'bad ply'})})
    tree, obj, _ = _run_add_identity(tmp_path, core)
    assert not any(c[1].endswith('/submit') for c in core.calls)
    warnings = compstub.messages(obj)['warning']
    assert any('bad ply' in w for w in warnings)
    assert any('a draft' in w for w in warnings)
    assert tree.DataCount == 1        # the draft is still reported


@pytest.mark.parametrize('status, fragment', [
    (409, 'already exists'), (403, 'contributor'), (401, 'sign in')])
def test_add_identity_answers_to_refusals(tmp_path, status, fragment):
    core = _core({('POST', '/identities'): Response(status, {})})
    tree, obj, _ = _run_add_identity(tmp_path, core)
    assert tree.DataCount == 0
    assert fragment in compstub.messages(obj)['error'][0]
    assert [c[0] for c in core.calls] == ['POST']


def test_add_identity_shows_the_servers_reasons(tmp_path):
    core = _core({('POST', '/identities'): Response(422, {'detail': [
        {'loc': ['body', 'snapshot', 'name'], 'msg': 'too long'}]})})
    tree, obj, _ = _run_add_identity(tmp_path, core)
    assert 'snapshot.name: too long' in compstub.messages(obj)['error'][0]


def test_add_identity_refuses_a_0_5_request(tmp_path):
    module = compstub.load_component('AddComponentIdentity', sticky={
        'CSC_AuthCore': _core()})
    module.sticky['CSC_AuthCore'].is_valid = lambda: True
    obj = compstub.instance(module, 'AddComponentIdentity')
    old = json.dumps({'_id': UUID_A, 'type': 'panel', 'material': 'corian',
                      'dataset': 'x', 'geometry': {}})
    tree = obj.RunScript(old, True)
    assert tree.DataCount == 0
    assert "'type'" in compstub.messages(obj)['error'][0]
    assert module.sticky['CSC_AuthCore'].calls == []


def test_a_426_names_the_fix(tmp_path):
    module = compstub.load_component('Session')
    core = module.ns['_AuthCore']('localhost:8010', disable_cache=True)
    core.set_access_token(_token(), 'u')
    sent = []

    class Http:
        def request(self, method, url, **kwargs):
            sent.append((method, url, kwargs))
            return Response(426, {'detail': 'gh-userobjects 0.5.1.0 is older '
                                  'than the minimum 0.6.0.0: update the '
                                  'Grasshopper UserObjects via CSC_Update'})
    core._http = Http()
    with pytest.raises(module.CSCClientOutdated) as caught:
        core.authorized_get('/identities')
    assert 'CSC_Update' in str(caught.value)
    assert str(caught.value).startswith('Server refused this client (426)')
    # a Add component shows it instead of a bare status
    add = compstub.load_component('AddComponentIdentity',
                                  sticky={'CSC_AuthCore': core})
    obj = compstub.instance(add, 'AddComponentIdentity')
    request = _identity_request(tmp_path, add)
    tree = obj.RunScript(request, True)
    assert tree.DataCount == 0
    assert 'CSC_Update' in compstub.messages(obj)['error'][0]


def _snapshot_request(tmp_path, module, supersedes=None):
    mesh = b.inline_mesh([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]])
    snapshot = b.snapshot_body(json.dumps(b.snapshot_metadata('N')),
                               b.geometry_body([mesh]))
    text_json = json.dumps(b.snapshot_envelope(UUID_A, snapshot, supersedes),
                           sort_keys=True)
    compstub.patch_library(module, 'staging_root',
                           lambda: str(tmp_path / 'staging'))
    return text_json


def _run_add_snapshot(tmp_path, core, request_supersedes=None, override=None,
                      **flags):
    module = compstub.load_component('AddComponentSnapshot',
                                     sticky={'CSC_AuthCore': core})
    core.is_valid = lambda: True
    obj = compstub.instance(module, 'AddComponentSnapshot')
    request = _snapshot_request(tmp_path, module, request_supersedes)
    tree = obj.RunScript(request, override, flags.get('run', True))
    return tree, obj, request


def _snapshot_core(path):
    return FakeCore({
        ('POST', path): Response(201, {'_id': UUID_B, 'status': 'draft',
                                       'version': 3}),
        ('GET', '/identities/%s/compose' % UUID_A): Response(200, {
            'identity': {'_id': UUID_A},
            'snapshots': [{'_id': UUID_B, 'status': 'draft'}]}),
    })


def test_add_snapshot_posts_a_new_state_and_reads_the_bare_answer(tmp_path):
    core = _snapshot_core('/identities/%s/snapshots' % UUID_A)
    tree, obj, request = _run_add_snapshot(tmp_path, core)
    assert [(c[0], c[1]) for c in core.calls][:1] == [
        ('POST', '/identities/%s/snapshots' % UUID_A)]
    assert not any(c[1].endswith('/submit') for c in core.calls)
    # the body is the snapshot alone, no identity and no id (extra='forbid')
    assert core.calls[0][2] == json.loads(request)['snapshot']
    assert 'identity_id' not in core.calls[0][2]
    assert json.loads(tree.values[0])['snapshots'][0]['status'] == 'draft'
    assert compstub.messages(obj)['error'] == []


def test_add_snapshot_with_supersedes_posts_a_correction(tmp_path):
    other = '44444444-4444-4444-8444-444444444444'
    for from_request, override in ((other, None), (None, other)):
        core = _snapshot_core('/snapshots/%s/supersede' % other)
        tree, obj, _ = _run_add_snapshot(tmp_path, core, from_request,
                                         override)
        assert core.calls[0][:2] == ('POST', '/snapshots/%s/supersede' % other)
        assert tree.DataCount == 1
    bad = _snapshot_core('/x')
    tree, obj, _ = _run_add_snapshot(tmp_path, bad, None, 'nope')
    assert bad.calls == [] and 'valid snapshot UUID' in \
        compstub.messages(obj)['error'][0]


def test_add_snapshot_has_no_submit_input_and_leaves_a_draft(tmp_path):
    core = _snapshot_core('/identities/%s/snapshots' % UUID_A)
    _run_add_snapshot(tmp_path, core)
    assert not any(c[1].endswith(('/submit', '/publish')) for c in core.calls)
    module = compstub.load_component('AddComponentSnapshot')
    names = module.CSC_AddComponentSnapshot.RunScript.__code__.co_varnames
    assert 'Submit' not in names and 'Publish' not in names


# ADD EVIDENCE ----------------------------------------------------------------
def test_add_evidence_posts_the_bulk(tmp_path):
    record = b.reinforcement_layout_record(
        UUID_A, [{'spec': 'BSt III', 'diameter_mm': 8,
                  'points': [[0, 0, 0], [1, 0, 0]]}], 'drawing')
    core = FakeCore({('POST', '/evidence/bulk'): Response(201, {'records': [
        {'_id': 'e1', 'status': 'draft'}, {'_id': 'e2', 'status': 'draft'}]})})
    core.is_valid = lambda: True
    module = compstub.load_component('AddEvidence',
                                     sticky={'CSC_AuthCore': core})
    obj = compstub.instance(module, 'AddEvidence')
    tree = obj.RunScript([UUID_B], [json.dumps(record), json.dumps(record)],
                         True)
    call = core.calls[0]
    assert call[:2] == ('POST', '/evidence/bulk')
    assert [r['identity_id'] for r in call[2]['records']] == [UUID_B, UUID_B]
    assert 'submit' not in call[2]                    # drafts (8.127)
    assert [json.loads(v)['_id'] for v in tree.values] == ['e1', 'e2']
    # without Run nothing is sent
    core.calls.clear()
    tree = obj.RunScript([UUID_B], [json.dumps(record)], False)
    assert core.calls == [] and obj.Component.Message == 'Run is False'


def test_add_evidence_shows_what_is_wrong():
    core = FakeCore({('POST', '/evidence/bulk'): Response(422, {'detail': {
        'message': 'Not valid', 'errors': [
            {'path': 'records[0].payload.bars[0].diameter_mm',
             'message': 'must be above 0'}]}})})
    core.is_valid = lambda: True
    module = compstub.load_component('AddEvidence',
                                     sticky={'CSC_AuthCore': core})
    obj = compstub.instance(module, 'AddEvidence')
    record = b.reinforcement_layout_record(
        UUID_A, [{'diameter_mm': 8, 'points': [[0, 0, 0], [1, 0, 0]]}],
        'exposed')
    tree = obj.RunScript([UUID_B], [json.dumps(record)], True)
    assert tree.DataCount == 0
    error = compstub.messages(obj)['error'][0]
    assert 'must be above 0' in error and 'records[0]' in error
    # a missing id is a warning, not a request
    core.calls.clear()
    obj.RunScript([], [json.dumps(record)], True)
    assert core.calls == []
    assert 'IdentityID' in compstub.messages(obj)['warning'][0]


# SESSION ---------------------------------------------------------------------
def _token(exp=4102444800):
    def part(data):
        return base64.urlsafe_b64encode(
            json.dumps(data).encode()).decode().rstrip('=')
    return '.'.join([part({'alg': 'none'}), part({'exp': exp, 'sub': 'u'}),
                     'sig'])


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    return compstub.load_component('Session')


def test_server_addresses(session):
    f = session.server_url
    assert f('') == f(None) == 'https://api.2ndchances.build'
    assert f('localhost:8010') == 'http://localhost:8010'
    assert f(' 127.0.0.1:8000/ ') == 'http://127.0.0.1:8000'
    assert f('[::1]') == 'http://[::1]'
    assert f('[::1]:8010') == 'http://[::1]:8010'
    assert f('[::1]:8010/') == 'http://[::1]:8010'
    assert f('[2001:db8::1]:8010') == 'https://[2001:db8::1]:8010'
    assert f('LOCALHOST:8010') == 'http://LOCALHOST:8010'
    assert f('api.example.org') == 'https://api.example.org'
    assert f('https://api.example.org/') == 'https://api.example.org'
    assert f('http://host:1/x/') == 'http://host:1/x'


def test_the_session_core_sends_over_one_connection(session):
    core = session.ns['_AuthCore']('localhost:8010', disable_cache=True)
    assert core.base_url == 'http://localhost:8010'
    assert core.CLIENT == 'gh-userobjects/0.6.0.0'
    core.set_access_token(_token(), 'ada')
    seen = []

    class Http:
        def request(self, method, url, **kwargs):
            seen.append((method, url, kwargs))
            return Response(200, {})
    core._http = Http()
    core.authorized_get('/identities', params={'expand': 'none'})
    core.authorized_post('/identities', json_body={'a': 1})
    core.authorized_put('/snapshots/s/meshes/0/reduced',
                        files={'mesh_file': ('r.ply', b'x', 'a/b')})
    assert [s[:2] for s in seen] == [
        ('GET', 'http://localhost:8010/identities'),
        ('POST', 'http://localhost:8010/identities'),
        ('PUT', 'http://localhost:8010/snapshots/s/meshes/0/reduced')]
    for _, _, kwargs in seen:
        assert kwargs['headers']['X-CSC-Client'] == 'gh-userobjects/0.6.0.0'
        assert kwargs['headers']['Authorization'].startswith('Bearer ')
    assert seen[0][2]['params'] == {'expand': 'none'}
    assert seen[1][2]['json'] == {'a': 1} and 'files' not in seen[1][2]
    assert 'files' in seen[2][2] and 'json' not in seen[2][2]
    assert seen[2][2]['timeout'] == 300
    # no bare requests call is left in the component or its libraries
    text = (compstub.SRC / 'DDU_CSC_Session.py').read_text(encoding='utf-8')
    assert 'requests.get(' not in text and 'requests.post(' not in text
    assert 'requests.put(' not in text


def test_a_token_that_expired_is_refused_before_the_request(session):
    core = session.ns['_AuthCore']('localhost:8010', disable_cache=True)
    with pytest.raises(RuntimeError):
        core.authorized_get('/identities')
    core.set_access_token(_token(exp=1), 'u')
    with pytest.raises(RuntimeError):
        core.authorized_put('/x', files={'f': ('a', b'', 'b')})


def test_changing_the_server_drops_the_login(session):
    core = session.ns['_AuthCore']('localhost:8010', disable_cache=True)
    core.set_access_token(_token(), 'ada')
    assert core.is_valid() and core.get_username() == 'ada'
    assert core.set_base_url('localhost:8010') is False
    assert core.is_valid()
    assert core.set_base_url('https://example.org') is True
    assert core.base_url == 'https://example.org'
    assert not core.is_valid() and core.get_username() is None


def test_the_cache_is_purged_once_when_the_client_changes(session, tmp_path):
    cache_dir = tmp_path / 'cache'
    cache_class = session.ns['_ComponentCache']
    cache = cache_class(cache_dir=str(cache_dir))
    assert not hasattr(cache, 'designs_dir')
    assert not (cache_dir / 'designs').exists()
    stamp = cache_dir / 'client_release.txt'
    assert stamp.read_text() == 'gh-userobjects/0.6.0.0'
    cache.set_identity('i1', {'_id': 'i1', 'type': 'beam'})
    assert cache.get_identity('i1')[2] is True
    # same release: kept
    cache_class(cache_dir=str(cache_dir))
    assert cache.get_identity('i1')[2] is True
    # a cache written by 0.5: emptied once, then stamped
    stamp.write_text('gh-userobjects/0.5.1.0')
    cache_class(cache_dir=str(cache_dir))
    assert cache.get_identity('i1')[2] is False
    assert stamp.read_text() == 'gh-userobjects/0.6.0.0'
    # an old cache without any stamp is not trusted either
    cache.set_identity('i2', {'_id': 'i2'})
    stamp.unlink()
    cache_class(cache_dir=str(cache_dir))
    assert cache.get_identity('i2')[2] is False
    stats = cache.get_cache_stats()
    assert 'design_count' not in stats


def _login_component(session, answers):
    obj = compstub.instance(session, 'Session')
    log = []

    class Http:
        def request(self, method, url, **kwargs):
            log.append((method, url, kwargs))
            for (m, tail), response in answers.items():
                if m == method and url.endswith(tail):
                    return response
            return Response(200, {})

    def make_core():
        core = session.ns['_AuthCore']('http://localhost:8010')
        core._http = Http()
        return core
    return obj, log, make_core


def test_the_session_logs_in_to_the_server_it_is_given(session):
    obj, log, make_core = _login_component(session, {
        ('POST', '/auth/token'): Response(200, {'access_token': _token()}),
        ('GET', '/schema/create-identity'): Response(200, {'title': 'x'})})
    core = make_core()
    session.sticky['CSC_AuthCore'] = core
    (status,) = obj.RunScript('ada', 'secret', False, False, False,
                              'localhost:8011')
    assert core.base_url == 'http://localhost:8011'
    login = [entry for entry in log if entry[1].endswith('/auth/token')][0]
    assert login[1] == 'http://localhost:8011/auth/token'
    assert login[2]['data'] == {'username': 'ada', 'password': 'secret'}
    assert login[2]['headers']['X-CSC-Client'] == 'gh-userobjects/0.6.0.0'
    assert core.is_valid() and core.get_username() == 'ada'
    text = '\n'.join(status)
    assert 'Server changed to http://localhost:8011' in text
    assert 'Server: http://localhost:8011' in text
    assert 'Designs' not in text
    assert compstub.messages(obj)['error'] == []


def test_the_session_shows_a_426_hint_at_login(session):
    obj, log, make_core = _login_component(session, {
        ('POST', '/auth/token'): Response(426, {'detail': 'gh-userobjects '
                                               '0.6.0.0 is older than the '
                                               'minimum 0.7.0.0'})})
    session.sticky['CSC_AuthCore'] = make_core()
    (status,) = obj.RunScript('ada', 'secret', False, False, False, None)
    assert any('CSC_Update' in line for line in status)
    assert 'CSC_Update' in compstub.messages(obj)['error'][0]


def test_login_failures_keep_their_messages(session):
    obj, log, make_core = _login_component(session, {
        ('POST', '/auth/token'): Response(401, {})})
    session.sticky['CSC_AuthCore'] = make_core()
    (status,) = obj.RunScript('ada', 'wrong', False, False, False, None)
    assert status == ['Invalid username or password']


def test_a_core_left_by_the_0_5_session_is_replaced(session):
    class Old:
        CLIENT = 'gh-userobjects/0.5.1.0'
        base_url = 'http://localhost:8010'
        leeway = 30
        disable_cache = True
        _token = _token()
        _exp = 4102444800
        _username = 'ada'
    session.sticky['CSC_AuthCore'] = Old()
    obj = compstub.instance(session, 'Session')
    core = obj.get_auth_core_from_sticky()
    assert core.CLIENT == 'gh-userobjects/0.6.0.0' and core.is_valid()
    assert core.base_url == 'http://localhost:8010'
    assert session.sticky['CSC_AuthCore'] is core
    assert hasattr(core, '_http') and hasattr(core, 'authorized_put')


# READ PATH WITHOUT GEOMETRY -------------------------------------------------
def _row(function, material, shape='linear', complexity=1, bbx=(400, 200, 50),
         dataset='ds', fragment=False):
    return {'identity': {'_id': UUID_A, 'original_function': function,
                         'material': material, 'dataset': dataset,
                         'material_class': '17 01 01'},
            'snapshots': [{'_id': UUID_B, 'shape_class': shape,
                           'complexity': complexity, 'bbx': list(bbx),
                           'fragment': fragment}]}


def _filter(**kwargs):
    rows = [_row('IfcBeam', 'concrete'),
            _row('IfcColumn', 'concrete', 'linear', 2, (900, 100, 100)),
            _row('IfcPlate', 'steel', 'planar', None, (300, 200, 10))]
    tree = compstub.FakeInputTree([[json.dumps(r) for r in rows]])
    module = compstub.load_component('FilterComponents')
    obj = compstub.instance(module, 'FilterComponents')
    args = dict(OriginalFunction=None, Material=None, Dataset=None,
                Complexity=None, Fragment=None, MinDimensionX=None,
                MaxDimensionX=None, MinDimensionY=None, MaxDimensionY=None,
                MinDimensionZ=None, MaxDimensionZ=None, ShapeClass=None,
                MaterialClass=None, ComponentPassport=tree)
    args.update(kwargs)
    description, filtered = obj.RunScript(**args)
    kept = [json.loads(v)['identity']['original_function']
            for v in filtered.values]
    return kept, description.values[0], obj


def test_filter_components_filters_on_the_0_6_fields():
    assert _filter()[0] == ['IfcBeam', 'IfcColumn', 'IfcPlate']
    kept, description, _ = _filter(OriginalFunction='IfcColumn')
    assert kept == ['IfcColumn'] and 'Original function: IfcColumn'         in description
    assert _filter(Material='steel')[0] == ['IfcPlate']
    assert _filter(ShapeClass='planar')[0] == ['IfcPlate']
    assert _filter(MaterialClass='17 01 01')[0] == [
        'IfcBeam', 'IfcColumn', 'IfcPlate']
    assert _filter(Complexity=2)[0] == ['IfcColumn']
    assert _filter(MinDimensionX=500)[0] == ['IfcColumn']
    assert _filter(MaxDimensionZ=60)[0] == ["IfcBeam", "IfcPlate"]
    kept, _, obj = _filter(OriginalFunction='IfcWall')
    assert kept == [] and compstub.messages(obj)['warning']


class ListCore:
    """What FetchFilteredComponents asks of the Session core."""

    def __init__(self, rows):
        self.rows = rows
        self.asked = []

    def is_valid(self):
        return True

    def cached_list_identities(self, params):
        self.asked.append(dict(params))
        return Response(200, self.rows)

    def passport_json_string(self, row):
        return json.dumps(row)


def test_fetch_filtered_sends_the_0_6_query():
    core = ListCore([_row('IfcBeam', 'concrete')])
    module = compstub.load_component('FetchFilteredComponents',
                                     sticky={'CSC_AuthCore': core})
    obj = compstub.instance(module, 'FetchFilteredComponents')
    description, data = obj.RunScript(
        'IfcBeam', 'concrete', 'ds', 2, False, 100.0, 0.0, None, None, None,
        None, 1, 'linear', '17 01 01', 'all')
    assert list(inspect.signature(obj.RunScript).parameters)[-3:] == [
        'ShapeClass', 'MaterialClass', 'Circulation']
    assert core.asked == [{
        'original_function': 'IfcBeam', 'material': 'concrete',
        'dataset': 'ds', 'shape_class': 'linear',
        'material_class': '17 01 01', 'circulation': 'all', 'complexity': 2,
        'fragment': 'false', 'reserved': 'true', 'bbx_min_x': 100.0,
        'expand': 'current_snapshot'}]
    assert 'comptype' not in core.asked[0]
    assert data.DataCount == 1
    text = description.values[0]
    assert 'Original function: IfcBeam' in text and 'X >= 100.00' in text
    assert 'Reserved by current user' in text
    # an empty list of filters is a plain list request
    core.asked.clear()
    obj.RunScript(None, None, None, None, None, None, None, None, None, None,
                  None, None, None, None, None)
    assert core.asked == [{'expand': 'current_snapshot'}]
    # a list for the original function takes its first item
    core.asked.clear()
    obj.RunScript(['IfcSlab', 'IfcBeam'], None, None, None, None, None, None,
                  None, None, None, None, None, None, None, None)
    assert core.asked[0]['original_function'] == 'IfcSlab'


def test_the_filter_components_name_the_new_inputs():
    for name, fragment in (('FetchFilteredComponents', 'OriginalFunction'),
                           ('FilterComponents', 'OriginalFunction')):
        text = (compstub.SRC / ('DDU_CSC_%s.py' % name)).read_text(
            encoding='utf-8')
        assert fragment in text and 'comptype' not in text
        assert "identity.get('type'" not in text and "'type'" not in text


def test_apply_frame_computes_a_missing_frame_from_the_passports_preview():
    """No frame in the passport (a design target): the frame comes from the
    preview geometry with the server's rules, and the column rule uses the
    original function of the identity or the input."""
    import numpy as np
    from csc_gh import read as csc_read
    corners = [[x, y, z] for x in (-500, 500) for y in (-50, 50)
               for z in (-60, 60)]
    faces = [[0, 1, 2], [1, 3, 2]]
    passport = {'identity': {'_id': UUID_A, 'original_function': 'IfcColumn'},
                'snapshots': [{'_id': UUID_B, 'geometry': {
                    'meshes': [{'vertices': corners, 'faces': faces}]}}]}
    module = compstub.load_component('ApplyFrame')
    obj = compstub.instance(module, 'ApplyFrame')
    text_json, plane = obj.RunScript(json.dumps(passport), None)
    placed = json.loads(text_json)
    placement = csc_read.placement_of(placed)
    assert placement is not None
    # a standing column: the placement moves its long axis (stored x) to z
    matrix = csc_read.placement_matrix(placement)
    assert np.allclose(matrix[:3, :3] @ [1, 0, 0], [0, 0, 1], atol=1e-9)         or np.allclose(matrix[:3, :3] @ [1, 0, 0], [0, 0, -1], atol=1e-9)
    assert any('computed locally' in m
               for m in compstub.messages(obj)['remark'])
    # the original function of the input overrides: a beam lies
    passport['identity']['original_function'] = 'IfcBeam'
    text_json, _ = obj.RunScript(json.dumps(passport), None)
    lying = csc_read.placement_matrix(csc_read.placement_of(
        json.loads(text_json)))
    # extents 1000 x 100 x 120: lying means the longest side stays on x and
    # the middle one (stored z) becomes y
    assert np.allclose(lying[:3, :3] @ [1, 0, 0], [1, 0, 0], atol=1e-9)
    assert np.allclose(lying[:3, :3] @ [0, 0, 1], [0, 1, 0], atol=1e-9)
    # the input overrides the identity: the same piece as a column stands
    column, _ = obj.RunScript(json.dumps(passport), 'IfcColumn')
    stood = csc_read.placement_matrix(csc_read.placement_of(
        json.loads(column)))
    assert abs(abs((stood[:3, :3] @ [1, 0, 0])[2]) - 1) < 1e-9
