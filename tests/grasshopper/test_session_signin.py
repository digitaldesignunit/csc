"""The Session component signs in without a password (decision 8.168 f) and
renews itself: the order of the ways to sign in, SignIn from the button to the
stored sign-in, SignOut, the refresh token that rotates, the 401 that renews
once (refresh token or the connected password) and never loops."""

from __future__ import annotations

import base64
import http.client
import inspect
import io
import itertools
import json
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from csc_gh import signin

import compstub

_COUNTER = itertools.count()
SERVER = 'http://localhost:8010'
NO_SIGN_IN = 'Press SignIn (Windows) or connect Username and Password'


class Response:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}

    def json(self):
        return self._body


def jwt(exp=None, sub='u'):
    def part(data):
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip('=')
    return '.'.join([part({'alg': 'none'}), part({'exp': exp or int(time.time()) + 3600, 'sub': sub,
                                                'jti': next(_COUNTER)}), 'sig'])


def tokens(refresh='csc_dev_NEW'):
    return Response(200, {'access_token': jwt(), 'refresh_token': refresh, 'expires_in': 3600})


class FakeHttp:
    """Answers by (method, end of URL); a list is used up in order, its last
    answer stays. An exception is raised."""

    def __init__(self, script=None):
        self.script = {k: (list(v) if isinstance(v, list) else [v]) for k, v in (script or {}).items()}
        self.log = []

    def request(self, method, url, **kwargs):
        self.log.append((method, url, kwargs))
        for (m, tail), answers in self.script.items():
            if m == method and urlsplit(url).path == tail:
                answer = answers.pop(0) if len(answers) > 1 else answers[0]
                if isinstance(answer, Exception):
                    raise answer
                return answer
        return Response(200, {})

    def calls(self, method, tail):
        return [c for c in self.log if c[0] == method and urlsplit(c[1]).path == tail]


def fake_protect(data):
    return b'P:' + data[::-1]


def fake_unprotect(blob):
    assert blob.startswith(b'P:')
    return blob[2:][::-1]


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    store = str(tmp_path / 'signin.json')
    monkeypatch.setattr(signin, 'store_path', lambda *a, **k: store)
    monkeypatch.setattr(signin, 'dpapi_protect', fake_protect)
    monkeypatch.setattr(signin, 'dpapi_unprotect', fake_unprotect)
    module = compstub.load_component('Session')
    module.ns['is_windows'] = lambda: True
    module.store = store
    return module


def make(ctx, script=None, windows=True):
    ctx.ns['is_windows'] = lambda: windows
    obj = compstub.instance(ctx, 'Session')
    core = ctx.ns['_AuthCore'](SERVER, disable_cache=True)
    core._http = FakeHttp(script)
    ctx.sticky['CSC_AuthCore'] = core
    return obj, core


def run(obj, username=None, password=None, sign_in=False, sign_out=False, server=None):
    return obj.RunScript(username, password, sign_in, sign_out, False, False, server)[0]


def stored(ctx, refresh='csc_dev_OLD', server=SERVER):
    signin.save_entry(ctx.store, server, refresh, fake_protect, computer='PC-1')


# THE ORDER -----------------------------------------------------------------------------------
def test_connected_username_and_password_win_over_a_stored_sign_in(ctx):
    obj, core = make(ctx, {('POST', '/auth/token'): Response(200, {'access_token': jwt()})})
    stored(ctx)
    status = run(obj, 'ada', 'secret')
    assert core.is_valid() and core.get_username() == 'ada'
    assert core._http.calls('POST', '/auth/token') and not core._http.calls('POST', '/token')
    assert signin.load_entry(ctx.store, SERVER, fake_unprotect) == 'csc_dev_OLD'       # untouched
    assert any('Server: ' + SERVER in line for line in status)


def test_nothing_connected_and_nothing_stored_says_what_to_press(ctx):
    obj, core = make(ctx)
    assert run(obj) == [NO_SIGN_IN]
    assert core._http.log == [] and compstub.messages(obj)['error'] == []
    assert run(obj, 'ada', None) == ['Please provide password']
    assert run(obj, None, 'secret') == ['Please provide username/email']


def test_on_a_mac_sign_in_says_it_is_windows_only_and_does_nothing(ctx):
    obj, core = make(ctx, windows=False)
    stored(ctx)                                   # a stored entry is no use off Windows
    for pressed in (True, False):
        status = run(obj, sign_in=pressed)
        assert status == [signin.WINDOWS_ONLY_TEXT] and 'Windows only' in status[0]
    assert core._http.log == [] and 'CSC_SignInFlow' not in ctx.sticky
    assert compstub.messages(obj)['warning'] == [signin.WINDOWS_ONLY_TEXT]


def test_the_password_path_still_works_on_a_mac(ctx):
    obj, core = make(ctx, {('POST', '/auth/token'): Response(200, {'access_token': jwt()})}, windows=False)
    run(obj, 'ada', 'secret')
    assert core.is_valid() and core._http.calls('POST', '/auth/token')


# THE STORED SIGN-IN -------------------------------------------------------------------------------
def test_a_stored_sign_in_signs_in_and_the_new_refresh_token_replaces_the_old(ctx):
    obj, core = make(ctx, {('POST', '/token'): tokens('csc_dev_NEW'),
                           ('GET', '/users/me'): Response(200, {'username': 'ada'})})
    stored(ctx, 'csc_dev_OLD')
    status = run(obj)
    (call,) = core._http.calls('POST', '/token')
    assert call[2]['data'] == {'grant_type': 'refresh_token', 'refresh_token': 'csc_dev_OLD',
                               'client_id': 'csc-grasshopper'}
    assert call[2]['headers']['X-CSC-Client'] == 'gh-userobjects/0.6.3.0'
    assert core.is_valid() and core.get_username() == 'ada'
    assert signin.load_entry(ctx.store, SERVER, fake_unprotect) == 'csc_dev_NEW'
    assert any('Signed in as ada (stored sign-in' in line for line in status)
    # the next solution does nothing new
    core._http.log.clear()
    run(obj)
    assert not core._http.calls('POST', '/token')


def test_a_dead_stored_sign_in_is_deleted_and_the_status_says_to_press_sign_in(ctx):
    obj, core = make(ctx, {('POST', '/token'): Response(400, {'error': 'invalid_grant'})})
    stored(ctx)
    status = run(obj)
    assert 'press SignIn again' in ' '.join(status) and not core.is_valid()
    assert signin.load_entry(ctx.store, SERVER, fake_unprotect) is None
    assert 'press SignIn again' in compstub.messages(obj)['error'][0]
    assert run(obj) == [NO_SIGN_IN]


def test_an_unreachable_server_keeps_the_stored_sign_in(ctx):
    import requests
    obj, core = make(ctx, {('POST', '/token'): requests.exceptions.ConnectionError('down')})
    stored(ctx)
    status = run(obj)
    assert 'Cannot reach the server' in ' '.join(status) and 'kept' in ' '.join(status)
    assert signin.load_entry(ctx.store, SERVER, fake_unprotect) == 'csc_dev_OLD'
    assert compstub.messages(obj)['error'] == [] and len(compstub.messages(obj)['warning']) == 1


def test_a_426_answer_shows_the_update_hint(ctx):
    obj, core = make(ctx, {('POST', '/token'): Response(426, {'detail': 'gh-userobjects 0.6.2.0 is older'})})
    stored(ctx)
    status = run(obj)
    assert any('CSC_Update' in line for line in status) and 'CSC_Update' in compstub.messages(obj)['error'][0]
    assert signin.load_entry(ctx.store, SERVER, fake_unprotect) == 'csc_dev_OLD'


def test_each_server_has_its_own_stored_sign_in(ctx):
    obj, core = make(ctx, {('POST', '/token'): tokens('csc_dev_A2'),
                           ('GET', '/users/me'): Response(200, {'username': 'ada'})})
    stored(ctx, 'csc_dev_A', SERVER)
    stored(ctx, 'csc_dev_B', 'https://api.example.org')
    run(obj)
    assert signin.load_entry(ctx.store, SERVER, fake_unprotect) == 'csc_dev_A2'
    assert signin.load_entry(ctx.store, 'https://api.example.org', fake_unprotect) == 'csc_dev_B'
    # another server: signed out in memory, and nothing stored for it
    status = run(obj, server='https://third.example')
    assert not core.is_valid() and status[-1] == NO_SIGN_IN
    assert any('Server changed' in line for line in status)


# SIGN IN WITH THE BROWSER ----------------------------------------------------------------------------
def browser(ctx, code='THE-CODE', deny=False, hold=None):
    """A stand-in for the browser: it calls the redirect URI of the address it
    is given, as a browser does after the user pressed Allow."""
    seen = []

    def open_it(url):
        seen.append(url)
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        redirect = urlsplit(query['redirect_uri'])
        tail = ('error=access_denied' if deny else 'code=' + code) + '&state=' + query['state']

        def call():
            if hold is not None:
                hold.wait(10)
            c = http.client.HTTPConnection('127.0.0.1', redirect.port, timeout=5)
            c.putrequest('GET', redirect.path + '?' + tail, skip_host=True)
            c.putheader('Host', '127.0.0.1:%d' % redirect.port)
            c.endheaders()
            c.getresponse().read()
            c.close()
        threading.Thread(target=call, daemon=True).start()
    ctx.ns['open_browser'] = open_it
    return seen


def wait_for(flow, states=('done', 'failed')):
    deadline = time.time() + 10
    while flow.state not in states and time.time() < deadline:
        time.sleep(0.02)
    assert flow.state in states, flow.state


def test_sign_in_opens_the_browser_waits_and_then_signs_in_and_stores_the_refresh_token(ctx):
    hold = threading.Event()
    seen = browser(ctx, hold=hold)
    obj, core = make(ctx, {('POST', '/token'): tokens('csc_dev_FIRST'),
                           ('GET', '/users/me'): Response(200, {'username': 'ada'})})
    status = run(obj, sign_in=True)
    assert len(seen) == 1 and 'Browser opened' in status[0] and not core.is_valid()
    query = {k: v[0] for k, v in parse_qs(urlsplit(seen[0]).query).items()}
    assert urlsplit(seen[0]).path == '/authorize'
    assert query['client_id'] == 'csc-grasshopper' and query['scope'] == 'gh:client'
    assert urlsplit(query['redirect_uri']).hostname == '127.0.0.1' and query['code_challenge_method'] == 'S256'
    flow = ctx.sticky['CSC_SignInFlow']
    # solutions while the browser has not answered: waiting, no second browser
    waiting = run(obj, sign_in=True)
    assert 'Waiting for the browser' in waiting[0] and len(seen) == 1
    hold.set()
    wait_for(flow, ('done',))
    final = run(obj)
    assert core.is_valid() and core.get_username() == 'ada'
    assert 'Signed in as ada (the sign-in renews itself)' in final[0]
    assert 'CSC_SignInFlow' not in ctx.sticky
    assert signin.load_entry(ctx.store, SERVER, fake_unprotect) == 'csc_dev_FIRST'
    (post,) = core._http.calls('POST', '/token')
    assert post[2]['data']['code'] == 'THE-CODE' and post[2]['data']['grant_type'] == 'authorization_code'
    assert signin.challenge_of(post[2]['data']['code_verifier']) == query['code_challenge']


def test_the_flow_asks_grasshopper_to_solve_the_component_again(ctx):
    scheduled = []

    class Document:
        def ScheduleSolution(self, delay, callback):
            scheduled.append((delay, callback))

    obj, core = make(ctx, {('POST', '/token'): tokens(), ('GET', '/users/me'): Response(200, {'username': 'a'})})
    obj.Component.OnPingDocument = lambda: Document()
    obj.Component.expired = []
    obj.Component.ExpireSolution = lambda flag: obj.Component.expired.append(flag)
    browser(ctx)
    run(obj, sign_in=True)
    wait_for(ctx.sticky['CSC_SignInFlow'], ('done',))
    deadline = time.time() + 5
    while not scheduled and time.time() < deadline:
        time.sleep(0.02)
    assert len(scheduled) == 1
    scheduled[0][1](None)                          # Grasshopper runs it between solutions
    assert obj.Component.expired == [False]


def test_a_denial_in_the_browser_is_an_error_and_the_next_solution_starts_clean(ctx):
    browser(ctx, deny=True)
    obj, core = make(ctx)
    run(obj, sign_in=True)
    wait_for(ctx.sticky['CSC_SignInFlow'], ('failed',))
    status = run(obj)
    assert 'denied' in ' '.join(status) and 'denied' in compstub.messages(obj)['error'][0]
    assert 'CSC_SignInFlow' not in ctx.sticky and not core.is_valid()
    assert signin.load_entry(ctx.store, SERVER, fake_unprotect) is None
    assert run(obj) == [NO_SIGN_IN]


def test_a_code_the_server_refuses_leaves_nothing_stored(ctx):
    browser(ctx)
    obj, core = make(ctx, {('POST', '/token'): Response(400, {'error': 'invalid_grant'})})
    run(obj, sign_in=True)
    wait_for(ctx.sticky['CSC_SignInFlow'], ('failed',))
    status = run(obj)
    assert 'press SignIn again' in ' '.join(status) and not signin.has_entry(ctx.store, SERVER)


def test_connected_username_and_password_stop_a_sign_in_button_from_opening_the_browser(ctx):
    seen = browser(ctx)
    obj, core = make(ctx, {('POST', '/auth/token'): Response(200, {'access_token': jwt()})})
    run(obj, 'ada', 'secret', sign_in=True)
    assert seen == [] and 'CSC_SignInFlow' not in ctx.sticky and core.is_valid()


def test_a_browser_that_cannot_be_opened_says_where_to_go(ctx):
    def broken(url):
        raise OSError('no browser')
    ctx.ns['open_browser'] = broken
    obj, core = make(ctx)
    status = run(obj, sign_in=True)
    run(obj)                                         # the failed flow is reported by the next solution
    ctx.sticky.pop('CSC_SignInFlow', None)
    assert 'Browser opened' in status[0] and 'http://localhost:8010/authorize' in status[0]


def test_a_sign_in_of_another_server_is_cancelled_when_the_server_changes(ctx):
    browser(ctx, hold=threading.Event())
    obj, core = make(ctx)
    run(obj, sign_in=True)
    flow = ctx.sticky['CSC_SignInFlow']
    run(obj, server='https://other.example')
    assert 'CSC_SignInFlow' not in ctx.sticky
    assert flow._listener.wait(2) == ('timeout', None)


# SIGN OUT ------------------------------------------------------------------------------------------------
def test_sign_out_revokes_on_the_server_deletes_the_stored_sign_in_and_signs_out(ctx):
    obj, core = make(ctx, {('POST', '/token'): tokens('csc_dev_LIVE'), ('GET', '/users/me'): Response(200, {'username': 'a'}),
                           ('POST', '/revoke'): Response(200, {})})
    stored(ctx)
    run(obj)
    status = run(obj, sign_out=True)
    assert status == ['Signed out.']
    (call,) = core._http.calls('POST', '/revoke')
    assert call[2]['data'] == {'token': 'csc_dev_LIVE', 'client_id': 'csc-grasshopper', 'client_secret': ''}
    assert not signin.has_entry(ctx.store, SERVER) and not core.is_valid()
    assert core._refresh is None and core._credentials is None
    assert run(obj) == [NO_SIGN_IN]


def test_sign_out_without_a_session_uses_the_stored_entry_and_survives_a_dead_server(ctx):
    import requests
    obj, core = make(ctx, {('POST', '/revoke'): requests.exceptions.ConnectionError('down')})
    stored(ctx, 'csc_dev_ONLY')
    status = run(obj, sign_out=True)
    assert status[0].startswith('Signed out.') and 'Settings' in status[0]
    assert not signin.has_entry(ctx.store, SERVER)
    again = run(obj, sign_out=True)
    assert again == ['Signed out.']


def test_sign_out_forgets_the_connected_password_of_this_session_too(ctx):
    obj, core = make(ctx, {('POST', '/auth/token'): Response(200, {'access_token': jwt()})})
    run(obj, 'ada', 'secret')
    assert core._credentials == ('ada', 'secret')
    run(obj, 'ada', 'secret', sign_out=True)
    assert core._credentials is None and not core.is_valid()


# RENEWING ------------------------------------------------------------------------------------------------------
def signed_in(ctx, script, refresh='csc_dev_R0', **kw):
    obj, core = make(ctx, script)
    core.set_access_token(jwt(), 'ada')
    core._refresh = refresh
    return obj, core


def test_an_expired_token_is_renewed_through_the_refresh_token_before_the_call(ctx):
    obj, core = signed_in(ctx, {('POST', '/token'): tokens('csc_dev_R1'), ('GET', '/identities'): Response(200, [])})
    core.set_access_token(jwt(exp=int(time.time()) - 5), 'ada')
    assert not core.is_valid()
    assert core.authorized_get('/identities').status_code == 200
    assert [c[1].rsplit('/', 1)[-1] for c in core._http.log] == ['token', 'identities']
    assert core._refresh == 'csc_dev_R1'


def test_a_401_renews_once_and_repeats_the_call_once(ctx):
    obj, core = signed_in(ctx, {('GET', '/identities'): [Response(401, {}), Response(200, ['ok'])],
                                ('POST', '/token'): tokens('csc_dev_R1')})
    stored(ctx, 'csc_dev_R0')
    answer = core.authorized_get('/identities')
    assert answer.status_code == 200 and answer.json() == ['ok']
    assert len(core._http.calls('GET', '/identities')) == 2 and len(core._http.calls('POST', '/token')) == 1
    assert signin.load_entry(ctx.store, SERVER, fake_unprotect) == 'csc_dev_R1'     # every rotation is stored
    second = core._http.calls('GET', '/identities')[1][2]['headers']['Authorization']
    first = core._http.calls('GET', '/identities')[0][2]['headers']['Authorization']
    assert first != second


def test_a_401_that_stays_a_401_is_given_back_after_one_try_without_a_loop(ctx):
    obj, core = signed_in(ctx, {('GET', '/identities'): Response(401, {}), ('POST', '/token'): tokens()})
    answer = core.authorized_get('/identities')
    assert answer.status_code == 401
    assert len(core._http.calls('GET', '/identities')) == 2 and len(core._http.calls('POST', '/token')) == 1


def test_a_dead_refresh_token_ends_the_stored_sign_in_and_gives_back_the_401(ctx):
    obj, core = signed_in(ctx, {('GET', '/identities'): Response(401, {}),
                                ('POST', '/token'): Response(400, {'error': 'invalid_grant'})})
    stored(ctx, 'csc_dev_R0')
    assert core.authorized_get('/identities').status_code == 401
    assert core._refresh is None and not signin.has_entry(ctx.store, SERVER)
    assert len(core._http.calls('GET', '/identities')) == 1                 # nothing to repeat with


def test_a_password_sign_in_signs_in_again_once_when_a_call_answers_401(ctx):
    obj, core = make(ctx, {('POST', '/auth/token'): [Response(200, {'access_token': jwt(sub='first')}),
                                                      Response(200, {'access_token': jwt(sub='second')})],
                           ('GET', '/identities'): [Response(401, {}), Response(200, ['ok'])]})
    run(obj, 'ada', 'secret')
    answer = core.authorized_get('/identities')
    assert answer.status_code == 200 and answer.json() == ['ok']
    logins = core._http.calls('POST', '/auth/token')
    assert len(logins) == 2 and logins[1][2]['data'] == {'username': 'ada', 'password': 'secret'}
    assert len(core._http.calls('GET', '/identities')) == 2
    assert core.get_username() == 'ada'


def test_a_password_sign_in_renews_an_expired_token_before_the_call(ctx):
    obj, core = make(ctx, {('POST', '/auth/token'): Response(200, {'access_token': jwt()}),
                           ('GET', '/identities'): Response(200, [])})
    run(obj, 'ada', 'secret')
    core.set_access_token(jwt(exp=int(time.time()) - 5))
    assert core.authorized_get('/identities').status_code == 200
    assert len(core._http.calls('POST', '/auth/token')) == 2


def test_a_password_that_no_longer_works_gives_back_the_401_without_a_loop(ctx):
    obj, core = make(ctx, {('POST', '/auth/token'): [Response(200, {'access_token': jwt()}), Response(401, {})],
                           ('GET', '/identities'): Response(401, {})})
    run(obj, 'ada', 'secret')
    assert core.authorized_get('/identities').status_code == 401
    assert len(core._http.calls('POST', '/auth/token')) == 2 and len(core._http.calls('GET', '/identities')) == 1


def test_with_nothing_to_renew_with_an_expired_token_is_still_the_old_error(ctx):
    obj, core = make(ctx)
    core.set_access_token(jwt(exp=int(time.time()) - 5), 'ada')
    with pytest.raises(RuntimeError, match='sign in again'):
        core.authorized_get('/identities')


def test_an_uploaded_file_is_read_from_its_start_when_the_call_is_repeated(ctx):
    class Http(FakeHttp):
        def request(self, method, url, **kwargs):
            handle = (kwargs.get('files') or {}).get('mesh_file', (None, None))[1]
            if handle is not None:
                self.log.append((method, url, dict(kwargs, position=handle.tell())))
                handle.read()                                          # a real send consumes it
                return self.script_answer(url)
            return super().request(method, url, **kwargs)

        def script_answer(self, url):
            self.sent = getattr(self, 'sent', 0) + 1
            return Response(401, {}) if self.sent == 1 else Response(200, {})
    obj, core = signed_in(ctx, {('POST', '/token'): tokens()})
    core._http = Http({('POST', '/token'): tokens()})
    handle = io.BytesIO(b'ply-data')
    answer = core.authorized_put('/snapshots/s/meshes/0/reduced', files={'mesh_file': ('r.ply', handle, 'a/b')})
    puts = [c for c in core._http.log if c[0] == 'PUT']
    assert answer.status_code == 200 and [p[2]['position'] for p in puts] == [0, 0]


# WHERE THINGS LIVE ------------------------------------------------------------------------------------------------
def test_no_token_reaches_an_output_a_message_or_the_document(ctx):
    browser(ctx)
    obj, core = make(ctx, {('POST', '/token'): tokens('csc_dev_SECRET'),
                           ('GET', '/users/me'): Response(200, {'username': 'ada'})})
    seen = [run(obj, sign_in=True)]
    wait_for(ctx.sticky['CSC_SignInFlow'], ('done',))
    seen.append(run(obj))
    seen.append(run(obj, sign_out=True))
    text = json.dumps(seen) + json.dumps(compstub.messages(obj))
    assert 'csc_dev_' not in text and 'SECRET' not in text and 'eyJ' not in text and core._token is None


def test_the_stored_file_never_holds_the_token_in_the_clear(ctx):
    obj, core = make(ctx, {('POST', '/token'): tokens('csc_dev_PLAINSECRET'), ('GET', '/users/me'): Response(200, {'username': 'a'})})
    stored(ctx)
    run(obj)
    text = open(ctx.store, encoding='utf-8').read()
    assert 'PLAINSECRET' not in text and 'csc_dev_' not in text


def test_a_store_that_cannot_be_written_deletes_the_stale_entry_and_says_so(ctx, monkeypatch):
    obj, core = make(ctx, {('POST', '/token'): tokens('csc_dev_NEW'), ('GET', '/users/me'): Response(200, {'username': 'a'})})
    stored(ctx)

    def broken(data):
        raise signin.SignInError('Windows could not protect the sign-in (error 5).')
    monkeypatch.setattr(signin, 'dpapi_protect', broken)
    run(obj)
    assert core.is_valid() and core.store_problem and 'error 5' in core.store_problem
    assert not signin.has_entry(ctx.store, SERVER)                        # the old token is dead: not kept


def test_a_core_left_by_an_older_release_keeps_its_sign_in(ctx):
    class Old:
        CLIENT = 'gh-userobjects/0.6.2.1'
        base_url = SERVER
        leeway = 30
        disable_cache = True
        _token = jwt()
        _exp = 4102444800
        _username = 'ada'
        _refresh = 'csc_dev_KEPT'
        _credentials = ('ada', 'secret')
    ctx.sticky['CSC_AuthCore'] = Old()
    core = compstub.instance(ctx, 'Session').get_auth_core_from_sticky()
    assert core.CLIENT == 'gh-userobjects/0.6.3.0' and core._refresh == 'csc_dev_KEPT'
    assert core._credentials == ('ada', 'secret') and core.is_valid()


def test_the_inputs_are_signin_and_signout_and_there_is_no_refresh(ctx):
    obj = compstub.instance(ctx, 'Session')
    names = list(inspect.signature(obj.RunScript).parameters)
    assert names == ['Username', 'Password', 'SignIn', 'SignOut', 'DisableCache', 'ClearCache', 'Server']
    obj.BeforeRunScript()
    text = ' '.join(p.Description for p in obj.InputParams[:7])
    assert 'Button: sign in with the browser' in obj.InputParams[2].Description
    assert 'Button: sign out' in obj.InputParams[3].Description
    assert 'Refresh' not in text and 'Server address' in obj.InputParams[6].Description


def test_a_changed_server_drops_the_session_but_not_the_stored_sign_in_of_the_old_one(ctx):
    obj, core = signed_in(ctx, {})
    core._credentials = ('ada', 'secret')
    stored(ctx, 'csc_dev_KEEP')
    assert core.set_base_url('https://other.example') is True
    assert core._refresh is None and core._credentials is None and not core.is_valid()
    assert signin.load_entry(ctx.store, SERVER, fake_unprotect) == 'csc_dev_KEEP'


def test_a_refresh_uses_the_token_another_rhino_stored_since(ctx):
    obj, core = signed_in(ctx, {('POST', '/token'): tokens('csc_dev_R2')}, refresh='csc_dev_R0')
    stored(ctx, 'csc_dev_R1')                         # the other Rhino rotated R0 to R1 and stored it
    core.set_access_token(jwt(exp=int(time.time()) - 5), 'ada')
    assert core.renew() is True
    (call,) = core._http.calls('POST', '/token')
    assert call[2]['data']['refresh_token'] == 'csc_dev_R1'
    assert signin.load_entry(ctx.store, SERVER, fake_unprotect) == 'csc_dev_R2'
