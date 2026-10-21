"""The sign-in without a password (decision 8.168 f), outside Rhino: PKCE and
the URLs, the loopback listener on real sockets, one sign-in from the browser
to the tokens, the stored sign-in (DPAPI mocked off Windows, the real one on
Windows), and the order of the ways to sign in."""

from __future__ import annotations

import ast
import base64
import hashlib
import http.client
import json
import os
import re
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from csc_gh import signin

REPO = Path(__file__).resolve().parents[2]


class Answer:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError('no json')
        return self._body


def fake_protect(data):
    return b'P:' + data[::-1]


def fake_unprotect(blob):
    assert blob.startswith(b'P:'), 'not ours'
    return blob[2:][::-1]


# ADDRESSES, PKCE, URLS -----------------------------------------------------------------
@pytest.mark.parametrize('typed, key', [
    ('https://api.2ndchances.build', 'https://api.2ndchances.build'),
    ('HTTPS://API.2ndchances.Build/', 'https://api.2ndchances.build'),
    ('https://api.2ndchances.build:443/', 'https://api.2ndchances.build'),
    ('http://localhost:8010/', 'http://localhost:8010'),
    ('http://LOCALHOST:80', 'http://localhost'),
    ('https://example.org/api/', 'https://example.org/api'),
    ('http://[::1]:8010', 'http://[::1]:8010')])
def test_a_server_address_is_one_key(typed, key):
    assert signin.normalise_server(typed) == key


def test_the_challenge_is_the_s256_of_the_verifier():
    # the example of RFC 7636, appendix B
    verifier = 'dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'
    assert signin.challenge_of(verifier) == 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM'
    fresh = signin.new_verifier()
    assert 43 <= len(fresh) <= 128 and re.fullmatch(r'[A-Za-z0-9_-]+', fresh)
    assert signin.new_verifier() != fresh and signin.new_state() != signin.new_state()
    digest = base64.urlsafe_b64encode(hashlib.sha256(fresh.encode()).digest()).decode().rstrip('=')
    assert signin.challenge_of(fresh) == digest and '=' not in digest


def test_the_authorize_url_asks_for_gh_client_with_pkce_and_a_loopback_redirect():
    url = signin.authorize_url('https://api.example.org/', 'CHAL', 'STATE', 54321, 'WORKSTATION-7')
    parts = urlsplit(url)
    assert f'{parts.scheme}://{parts.netloc}{parts.path}' == 'https://api.example.org/authorize'
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert query == {
        'response_type': 'code', 'client_id': 'csc-grasshopper', 'redirect_uri': 'http://127.0.0.1:54321/callback',
        'scope': 'gh:client', 'state': 'STATE', 'code_challenge': 'CHAL', 'code_challenge_method': 'S256',
        'computer': 'WORKSTATION-7'}
    assert 'computer' not in parse_qs(urlsplit(signin.authorize_url('https://a.b', 'C', 'S', 1)).query)


@pytest.mark.parametrize('raw, shown', [('WORKSTATION-7', 'WORKSTATION-7'), ('<b>PC</b> & "x"', 'bPC/b x'),
                                        ('x' * 200, 'x' * 60), ('a\tb\x00c', 'abc'), ('', ''), (None, None)])
def test_the_computer_name_is_short_plain_text(raw, shown):
    if raw is None:                                 # this computer's own name
        result = signin.computer_name()
        assert len(result) <= 60 and '<' not in result
    else:
        assert signin.computer_name(raw) == shown


def test_the_callback_needs_this_state_and_a_code():
    assert signin.check_callback({'state': 's', 'code': 'abc'}, 's') == 'abc'
    for query, text in (({'state': 'other', 'code': 'abc'}, 'state differs'), ({'code': 'abc'}, 'state differs'),
                        ({'state': 's', 'error': 'access_denied'}, 'denied'),
                        ({'state': 's', 'error': 'server_error'}, 'server_error'), ({'state': 's'}, 'no code')):
        with pytest.raises(signin.SignInError, match=text):
            signin.check_callback(query, 's')


def test_the_forms_of_the_token_endpoint():
    assert signin.code_form('C', 'V', 4000) == {
        'grant_type': 'authorization_code', 'code': 'C', 'redirect_uri': 'http://127.0.0.1:4000/callback',
        'client_id': 'csc-grasshopper', 'code_verifier': 'V'}
    assert signin.refresh_form('R') == {'grant_type': 'refresh_token', 'refresh_token': 'R',
                                        'client_id': 'csc-grasshopper'}
    assert signin.revoke_form('R') == {'token': 'R', 'client_id': 'csc-grasshopper', 'client_secret': ''}


def test_the_client_id_and_the_scope_are_the_ones_of_the_server():
    text = (REPO / 'src' / 'backend' / 'apps' / 'catalog' / 'oauth_server.py').read_text(encoding='utf-8')
    assert re.search(r"^GH_CLIENT_ID = '%s'$" % signin.CLIENT_ID, text, re.M)
    assert signin.SCOPE == 'gh:client'
    access = (REPO / 'src' / 'backend' / 'apps' / 'catalog' / 'access_tokens.py').read_text(encoding='utf-8')
    assert "SCOPE_GH = '%s'" % signin.SCOPE in access


# THE ANSWERS OF /token ----------------------------------------------------------------------
def test_a_good_answer_is_a_token_set():
    tokens = signin.parse_token_answer(Answer(200, {
        'access_token': 'JWT', 'refresh_token': 'csc_dev_x', 'expires_in': 3600, 'token_type': 'Bearer'}))
    assert (tokens.access_token, tokens.refresh_token, tokens.expires_in) == ('JWT', 'csc_dev_x', 3600)
    assert signin.parse_token_answer(Answer(200, {'access_token': 'a', 'refresh_token': 'b'})).expires_in == 3600


def test_the_bad_answers_have_sentences_and_invalid_grant_is_dead():
    with pytest.raises(signin.SignInError) as dead:
        signin.parse_token_answer(Answer(400, {'error': 'invalid_grant'}))
    assert dead.value.dead is True and 'press SignIn again' in str(dead.value)
    for response, text in ((Answer(429, {}), 'wait a moment'), (Answer(500, None), 'status 500'),
                           (Answer(400, {'error': 'invalid_request', 'error_description': 'bad verifier'}), 'bad verifier'),
                           (Answer(200, {'access_token': 'a'}), 'did not give a token')):
        with pytest.raises(signin.SignInError, match=text) as error:
            signin.parse_token_answer(response)
        assert error.value.dead is False


def test_exchange_refresh_and_revoke_post_to_the_right_urls():
    seen = []

    def post(url, data, headers, timeout):
        seen.append((url, data, headers, timeout))
        return Answer(200, {'access_token': 'a', 'refresh_token': 'b', 'expires_in': 3600})
    headers = {'X-CSC-Client': 'gh-userobjects/0.6.3.0'}
    signin.exchange_code(post, 'https://s.example/', 'C', 'V', 4000, headers)
    signin.refresh_access(post, 'https://s.example', 'R', headers)
    assert signin.revoke_refresh(post, 'https://s.example', 'R', headers) is True
    assert [s[0] for s in seen] == ['https://s.example/token', 'https://s.example/token', 'https://s.example/revoke']
    for _, _, sent, _ in seen:
        assert sent['Content-Type'] == 'application/x-www-form-urlencoded'
        assert sent['X-CSC-Client'] == 'gh-userobjects/0.6.3.0'
    assert seen[0][1]['code'] == 'C' and seen[1][1]['refresh_token'] == 'R' and seen[2][1]['token'] == 'R'
    assert signin.revoke_refresh(lambda *a: Answer(503), 'https://s', 'R') is False


# THE ORDER ------------------------------------------------------------------------------------------
@pytest.mark.parametrize('username, password, stored, windows, chosen', [
    ('ada', 'secret', True, True, 'password'), ('ada', 'secret', False, True, 'password'),
    ('ada', 'secret', True, False, 'password'), ('ada', 'secret', False, False, 'password'),
    (None, None, True, True, 'stored'), ('', '  ', True, True, 'stored'), ('ada', None, True, True, 'stored'),
    (None, 'secret', True, True, 'stored'), (None, None, False, True, 'none'),
    (None, None, True, False, 'none'), (None, None, False, False, 'none')])
def test_password_wins_then_the_stored_sign_in_then_nothing(username, password, stored, windows, chosen):
    assert signin.choose_sign_in(username, password, stored, windows) == chosen


def test_the_status_without_a_sign_in():
    assert signin.none_text(True) == 'Press SignIn (Windows) or connect Username and Password'
    assert 'Windows only' in signin.none_text(False)


# THE LISTENER ----------------------------------------------------------------------------------------------
def get(port, path, host=None, method='GET'):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    connection.putheader('Host', host or f'127.0.0.1:{port}')
    connection.endheaders()
    response = connection.getresponse()
    body = response.read().decode('utf-8')
    connection.close()
    return response.status, body, response


def test_the_listener_takes_one_good_callback_then_closes():
    listener = signin.CallbackListener('STATE', timeout=30)
    port = listener.start()
    assert listener._server.server_address[0] == '127.0.0.1' and port > 0
    status, body, response = get(port, '/callback?code=THECODE&state=STATE')
    assert status == 200 and 'Signed in, you can close this tab' in body
    assert '<script' not in body.lower() and 'src=' not in body.lower()
    assert response.getheader('Cache-Control') == 'no-store'
    assert response.getheader('Referrer-Policy') == 'no-referrer'
    assert listener.wait(5) == ('code', 'THECODE')
    listener._thread.join(5)
    with pytest.raises(OSError):
        get(port, '/callback?code=SECOND&state=STATE')                  # closed after the first
    assert listener.wait(1) == ('code', 'THECODE')


def test_the_listener_ignores_everything_that_is_not_the_one_callback():
    listener = signin.CallbackListener('STATE', timeout=30)
    port = listener.start()
    try:
        assert get(port, '/callback?code=X&state=OTHER')[0] == 400
        assert get(port, '/callback?code=X')[0] == 400
        assert get(port, '/other?code=X&state=STATE')[0] == 404
        assert get(port, '/callback?code=X&state=STATE', host='evil.example')[0] == 400    # DNS rebinding
        assert get(port, '/callback?code=X&state=STATE', host='127.0.0.1:1')[0] == 400
        assert get(port, '/callback', method='POST')[0] == 405
        assert listener.wait(0.2) is None                                # still waiting, nothing accepted
        assert get(port, '/callback?code=GOOD&state=STATE')[0] == 200
        assert listener.wait(5) == ('code', 'GOOD')
    finally:
        listener.close()


def test_a_denial_ends_the_listener_with_the_reason_and_the_page_says_not_signed_in():
    listener = signin.CallbackListener('STATE', timeout=30)
    port = listener.start()
    status, body, _ = get(port, '/callback?error=access_denied&state=STATE')
    assert status == 200 and 'not completed' in body
    kind, text = listener.wait(5)
    assert kind == 'error' and 'denied' in text


def test_the_listener_gives_up_after_its_time():
    listener = signin.CallbackListener('STATE', timeout=0.5)
    port = listener.start()
    assert listener.wait(10) == ('timeout', None)
    listener._thread.join(5)
    with pytest.raises(OSError):
        get(port, '/callback?code=X&state=STATE')


def test_a_listener_can_be_closed_and_each_one_has_its_own_port():
    one, two = signin.CallbackListener('A', timeout=30), signin.CallbackListener('B', timeout=30)
    ports = {one.start(), two.start()}
    assert len(ports) == 2
    one.close()
    two.close()
    assert one.wait(1) == ('timeout', None)


# ONE SIGN-IN, FROM THE BROWSER TO THE TOKENS ---------------------------------------------------------------------
class Browser:
    """Opens the address like a browser that was allowed: it calls the
    redirect URI with the state and a code."""

    def __init__(self, code='CODE-1', deny=False, state=None, fail=False):
        self.code, self.deny, self.state, self.fail, self.opened = code, deny, state, fail, []

    def __call__(self, url):
        if self.fail:
            raise OSError('no browser')
        self.opened.append(url)
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        redirect = urlsplit(query['redirect_uri'])
        state = self.state or query['state']
        tail = ('error=access_denied' if self.deny else f'code={self.code}') + f'&state={state}'
        threading.Thread(target=get, args=(redirect.port, f'{redirect.path}?{tail}'), daemon=True).start()


def run_flow(post, browser, **kw):
    done = threading.Event()
    flow = signin.SignInFlow('https://s.example', post, browser, on_done=done.set, computer='PC-1',
                             headers={'X-CSC-Client': 'gh-userobjects/0.6.3.0'}, timeout=kw.pop('timeout', 30), **kw)
    flow.start()
    assert done.wait(10), flow.state
    return flow


def test_a_sign_in_from_the_button_to_the_tokens():
    posts = []

    def post(url, data, headers, timeout):
        posts.append((url, data, headers))
        return Answer(200, {'access_token': 'JWT', 'refresh_token': 'csc_dev_new', 'expires_in': 3600})
    browser = Browser()
    flow = run_flow(post, browser)
    assert flow.state == 'done' and flow.error is None
    assert (flow.tokens.access_token, flow.tokens.refresh_token) == ('JWT', 'csc_dev_new')
    url = urlsplit(browser.opened[0])
    query = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert url.path == '/authorize' and query['computer'] == 'PC-1' and query['scope'] == 'gh:client'
    (call,) = posts
    assert call[0] == 'https://s.example/token' and call[1]['code'] == 'CODE-1'
    assert signin.challenge_of(call[1]['code_verifier']) == query['code_challenge']        # the verifier of this flow
    assert call[1]['redirect_uri'] == query['redirect_uri'] and call[2]['X-CSC-Client'].startswith('gh-userobjects/')
    assert flow.seconds_left() == 0


def test_a_wrong_state_never_reaches_the_token_endpoint():
    posts = []
    flow = None
    done = threading.Event()
    flow = signin.SignInFlow('https://s.example', lambda *a: posts.append(a), Browser(state='forged'),
                             on_done=done.set, computer='PC', timeout=1)
    flow.start()
    assert done.wait(10)
    assert flow.state == 'failed' and 'No answer' in flow.error and posts == []        # the forged call was ignored


def test_a_denial_a_dead_code_a_network_error_and_a_missing_browser_fail_with_sentences():
    flow = run_flow(lambda *a: Answer(500), Browser(deny=True))
    assert flow.state == 'failed' and 'denied' in flow.error and flow.tokens is None
    flow = run_flow(lambda *a: Answer(400, {'error': 'invalid_grant'}), Browser())
    assert flow.state == 'failed' and 'press SignIn again' in flow.error

    def broken(*args):
        raise ConnectionError('offline')
    flow = run_flow(broken, Browser())
    assert flow.state == 'failed' and 'offline' in flow.error
    flow = run_flow(lambda *a: Answer(200, {}), Browser(fail=True))
    assert flow.state == 'failed' and 'could not be opened' in flow.error and 'http' in flow.error


def test_a_flow_that_nobody_answers_expires_and_a_cancel_stops_it():
    done = threading.Event()
    flow = signin.SignInFlow('https://s.example', lambda *a: None, lambda url: None, on_done=done.set,
                             computer='PC', timeout=0.6)
    flow.start()
    assert flow.state == 'waiting' and flow.seconds_left() >= 0
    assert done.wait(10) and flow.state == 'failed' and 'No answer' in flow.error
    again = signin.SignInFlow('https://s.example', lambda *a: None, lambda url: None, computer='PC', timeout=30)
    again.start()
    again.cancel()
    again._listener._thread.join(5)
    assert again._listener.wait(1) == ('timeout', None)


# THE STORED SIGN-IN -------------------------------------------------------------------------------------------------
def test_the_storage_round_trip_per_server(tmp_path):
    path = str(tmp_path / 'DDU_CSC' / 'signin.json')
    assert signin.load_entry(path, 'https://a.example', fake_unprotect) is None
    signin.save_entry(path, 'https://a.example/', 'csc_dev_AAA', fake_protect, computer='PC-1')
    signin.save_entry(path, 'http://localhost:8010', 'csc_dev_BBB', fake_protect)
    assert signin.load_entry(path, 'HTTPS://A.example', fake_unprotect) == 'csc_dev_AAA'
    assert signin.load_entry(path, 'http://localhost:8010/', fake_unprotect) == 'csc_dev_BBB'
    assert signin.load_entry(path, 'https://other.example', fake_unprotect) is None
    assert signin.has_entry(path, 'https://a.example') and not signin.has_entry(path, 'https://other.example')
    # a renewed token replaces the old one; the other server is untouched
    signin.save_entry(path, 'https://a.example', 'csc_dev_CCC', fake_protect)
    assert signin.load_entry(path, 'https://a.example', fake_unprotect) == 'csc_dev_CCC'
    assert signin.load_entry(path, 'http://localhost:8010', fake_unprotect) == 'csc_dev_BBB'
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    assert data['version'] == 1 and set(data['entries']) == {'https://a.example', 'http://localhost:8010'}
    assert data['entries']['http://localhost:8010']['saved'].endswith('Z')


def test_the_file_holds_no_token_in_the_clear(tmp_path):
    path = str(tmp_path / 'signin.json')
    signin.save_entry(path, 'https://a.example', 'csc_dev_SECRETSECRETSECRET', fake_protect)
    text = Path(path).read_text(encoding='utf-8')
    assert 'SECRETSECRET' not in text and 'csc_dev_' not in text


def test_delete_removes_only_that_entry(tmp_path):
    path = str(tmp_path / 'signin.json')
    signin.save_entry(path, 'https://a.example', 'csc_dev_A', fake_protect)
    signin.save_entry(path, 'https://b.example', 'csc_dev_B', fake_protect)
    assert signin.delete_entry(path, 'https://a.example/') is True
    assert signin.delete_entry(path, 'https://a.example') is False
    assert signin.load_entry(path, 'https://a.example', fake_unprotect) is None
    assert signin.load_entry(path, 'https://b.example', fake_unprotect) == 'csc_dev_B'
    assert signin.delete_entry(str(tmp_path / 'nothing.json'), 'https://a.example') is False


def test_a_broken_file_or_another_users_entry_is_no_entry(tmp_path):
    path = tmp_path / 'signin.json'
    path.write_text('{ not json', encoding='utf-8')
    assert signin.load_entry(str(path), 'https://a.example', fake_unprotect) is None
    assert signin.has_entry(str(path), 'https://a.example') is False
    signin.save_entry(str(path), 'https://a.example', 'csc_dev_A', fake_protect)       # replaces the broken file
    assert signin.load_entry(str(path), 'https://a.example', fake_unprotect) == 'csc_dev_A'

    def another_user(blob):
        raise signin.SignInError('Windows could not unprotect the sign-in (error 13).')
    assert signin.load_entry(str(path), 'https://a.example', another_user) is None
    path.write_text(json.dumps({'version': 1, 'entries': {'https://a.example': 'text'}}), encoding='utf-8')
    assert signin.load_entry(str(path), 'https://a.example', fake_unprotect) is None


def test_the_store_is_a_file_under_appdata_ddu_csc():
    path = signin.store_path({'APPDATA': r'C:\Users\x\AppData\Roaming'}, windows=True)
    assert path.endswith(os.path.join('DDU_CSC', 'signin.json')) and 'Roaming' in path
    assert 'Application Support' in signin.store_path({}, windows=False)


def test_a_write_leaves_no_temporary_file(tmp_path):
    path = str(tmp_path / 'signin.json')
    signin.save_entry(path, 'https://a.example', 'csc_dev_A', fake_protect)
    assert sorted(p.name for p in tmp_path.iterdir()) == ['signin.json']


@pytest.mark.skipif(os.name != 'nt', reason='DPAPI is Windows only')
def test_dpapi_round_trip_with_the_real_windows_api():
    secret = b'csc_dev_' + bytes(range(65, 91)) * 2
    blob = signin.dpapi_protect(secret)
    assert blob != secret and secret not in blob and len(blob) > len(secret)
    assert signin.dpapi_unprotect(blob) == secret
    assert signin.dpapi_unprotect(signin.dpapi_protect(b'')) == b''
    with pytest.raises(signin.SignInError):
        signin.dpapi_unprotect(blob[:-3] + b'\x00\x00\x00')
    with pytest.raises(signin.SignInError):
        signin.dpapi_unprotect(b'not a blob')


@pytest.mark.skipif(os.name != 'nt', reason='DPAPI is Windows only')
def test_the_real_dpapi_through_the_storage(tmp_path):
    path = str(tmp_path / 'signin.json')
    signin.save_entry(path, 'https://a.example', 'csc_dev_REAL', signin.dpapi_protect)
    assert 'REAL' not in Path(path).read_text(encoding='utf-8')
    assert signin.load_entry(path, 'https://a.example', signin.dpapi_unprotect) == 'csc_dev_REAL'


@pytest.mark.skipif(os.name == 'nt', reason='checks the refusal off Windows')
def test_dpapi_off_windows_says_so():
    with pytest.raises(signin.SignInError, match='Windows'):
        signin.dpapi_protect(b'x')


def test_the_module_is_python_3_9_and_standard_library_only():
    source = (REPO / 'grasshopper_lib' / 'csc_gh' / 'signin.py').read_text(encoding='utf-8')
    tree = ast.parse(source, feature_version=(3, 9))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split('.')[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or '').split('.')[0])
    import sys
    assert imported <= set(sys.stdlib_module_names), imported - set(sys.stdlib_module_names)
    assert all(ord(c) < 128 for c in source)
