"""The Grasshopper client library (``csc_gh.signin``) against the real routes of
the backend (decision 8.168 f): one sign-in from the button to the tokens over a
real loopback socket, with the TestClient as the server and a stand-in browser
that presses Allow on the consent routes. The two sides are written apart; this
is where they meet."""

from __future__ import annotations

import http.client
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

LIB = Path(__file__).resolve().parents[2] / 'grasshopper_lib'
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from csc_gh import signin  # noqa: E402

from oauth_helpers import bearer, mcp_post, reset_address_counters  # noqa: E402

SERVER = 'http://localhost'          # the TestClient does not look at the host
HEADERS = {'X-CSC-Client': 'gh-userobjects/0.6.3.0'}


@pytest.fixture(autouse=True)
def fresh_counters():
    reset_address_counters()
    yield
    reset_address_counters()


@pytest.fixture
def member(make_user, login):
    user = make_user('memberuser', role='user')
    return {**user, 'headers': bearer(login('memberuser').json()['access_token'])}


@pytest.fixture
def wire(api):
    def post(url, data, headers, timeout):
        return api.post(urlsplit(url).path, data=data, headers=headers)
    return post


def allow_in_browser(api, user, allow=True, log=None):
    """A browser that was shown the address: /authorize, the consent page's
    two routes, then the redirect to the listener."""
    def open_it(url):
        parts = urlsplit(url)
        first = api.get(parts.path + '?' + parts.query, follow_redirects=False)
        assert first.status_code == 302, first.text
        rid = parse_qs(urlsplit(first.headers['location']).query)['request'][0]
        view = api.get(f'/oauth/requests/{rid}', headers=user['headers']).json()
        if log is not None:
            log.append(view)
        decision = api.post(f'/oauth/requests/{rid}/decision', json={'allow': allow},
                            headers=user['headers']).json()['redirect_to']
        target = urlsplit(decision)

        def call():
            connection = http.client.HTTPConnection('127.0.0.1', target.port, timeout=5)
            connection.putrequest('GET', target.path + '?' + target.query, skip_host=True)
            connection.putheader('Host', '127.0.0.1:%d' % target.port)
            connection.endheaders()
            connection.getresponse().read()
            connection.close()
        threading.Thread(target=call, daemon=True).start()
    return open_it


def finish(flow):
    deadline = time.time() + 10
    while flow.state not in ('done', 'failed') and time.time() < deadline:
        time.sleep(0.02)
    assert flow.state in ('done', 'failed'), flow.state


def test_the_client_library_signs_in_through_the_real_server_and_renews(api, member, wire):
    views = []
    flow = signin.SignInFlow(SERVER, wire, allow_in_browser(api, member, log=views), computer='WORKSTATION-7',
                             headers=HEADERS)
    flow.start()
    finish(flow)
    assert flow.state == 'done', flow.error
    assert views[0]['scope'] == 'gh:client' and views[0]['computer'] == 'WORKSTATION-7' and views[0]['can_allow']
    tokens = flow.tokens
    # the access token is the normal JWT and works on the routes the components use
    assert api.get('/users/me', headers=bearer(tokens.access_token)).json()['username'] == 'memberuser'
    assert tokens.refresh_token.startswith('csc_dev_') and tokens.expires_in == 3600
    assert mcp_post(api, tokens.access_token, 'tools/list').status_code == 401
    rows = api.get('/auth/access-tokens', headers=member['headers']).json()
    assert [r['name'] for r in rows] == ['Grasshopper on WORKSTATION-7']
    # the refresh token rotates and the old one is dead
    again = signin.refresh_access(wire, SERVER, tokens.refresh_token, HEADERS)
    assert again.refresh_token != tokens.refresh_token
    assert api.get('/users/me', headers=bearer(again.access_token)).status_code == 200
    # sign out revokes it on the server
    assert signin.revoke_refresh(wire, SERVER, again.refresh_token, HEADERS) is True
    with pytest.raises(signin.SignInError) as dead:
        signin.refresh_access(wire, SERVER, again.refresh_token, HEADERS)
    assert dead.value.dead is True


def test_a_reused_refresh_token_ends_the_sign_in_and_the_library_calls_it_dead(api, member, wire):
    flow = signin.SignInFlow(SERVER, wire, allow_in_browser(api, member), computer='PC', headers=HEADERS)
    flow.start()
    finish(flow)
    first = flow.tokens
    second = signin.refresh_access(wire, SERVER, first.refresh_token, HEADERS)
    with pytest.raises(signin.SignInError) as reused:
        signin.refresh_access(wire, SERVER, first.refresh_token, HEADERS)
    assert reused.value.dead is True
    with pytest.raises(signin.SignInError) as ended:
        signin.refresh_access(wire, SERVER, second.refresh_token, HEADERS)
    assert ended.value.dead is True


def test_a_denial_in_the_browser_reaches_the_flow_as_denied(api, member, wire):
    flow = signin.SignInFlow(SERVER, wire, allow_in_browser(api, member, allow=False), computer='PC', headers=HEADERS)
    flow.start()
    finish(flow)
    assert flow.state == 'failed' and 'denied' in flow.error and flow.tokens is None
    assert api.get('/auth/access-tokens', headers=member['headers']).json() == []


def test_the_authorize_address_of_the_library_is_accepted_by_the_server(api):
    verifier = signin.new_verifier()
    url = signin.authorize_url(SERVER, signin.challenge_of(verifier), signin.new_state(), 54321, 'PC')
    parts = urlsplit(url)
    response = api.get(parts.path + '?' + parts.query, follow_redirects=False)
    assert response.status_code == 302 and '/oauth/consent?request=' in response.headers['location']
