"""recreate_common.py: where files may go, which database may be touched, how the import signs in."""

from __future__ import annotations

import pytest


def test_defaults_are_the_local_rehearsal_under_dot_dev(common):
    for path in (common.DEFAULT_DATA, common.DEFAULT_OUT, common.DEFAULT_ASSETS):
        assert common.DOT_DEV in path.parents
    assert common.DEFAULT_MONGO_URI.startswith('mongodb://127.0.0.1:')
    assert common.DEFAULT_SERVER.startswith('http://127.0.0.1:')


def test_output_goes_outside_the_repository_or_into_dot_dev_only(common, tmp_path):
    assert common.out_dir(tmp_path / 'out').is_dir()                          # elsewhere: fine
    assert common.out_dir(common.DEFAULT_OUT, create=False) == common.DEFAULT_OUT.resolve()
    for forbidden in (common.REPO, common.REPO / 'scripts', common.REPO / 'tests' / 'data',
                      common.REPO / 'src' / 'backend'):
        with pytest.raises(SystemExit) as stop:
            common.out_dir(forbidden, create=False)
        assert 'refusing to write inside the repository' in str(stop.value)


@pytest.mark.parametrize('uri', ['mongodb://127.0.0.1:27791', 'mongodb://localhost/csc',
                                 'mongodb://user@127.0.0.1:1/x', 'mongodb://[::1]:27017'])
def test_a_local_database_is_accepted(common, uri):
    assert common.require_local(uri) == uri


@pytest.mark.parametrize('uri', ['mongodb://db.example.org:27017', 'mongodb+srv://cluster.example.net/csc',
                                 'mongodb://10.0.0.5:27017', 'mongodb://localhost.example.org/x',
                                 'mongodb://127.0.0.1.example.org/x', 'csc'])
def test_any_other_host_is_refused(common, uri):
    with pytest.raises(SystemExit) as stop:
        common.require_local(uri)
    assert 'only runs against a database on this machine' in str(stop.value)


class FakePost:
    def __init__(self, status=200, token='tok-1'):
        self.status, self.token, self.calls = status, token, []

    def __call__(self, url, data=None, headers=None, timeout=None):
        self.calls.append({'url': url, 'data': dict(data), 'headers': headers})
        outer = self

        class Response:
            status_code = outer.status

            def json(self):
                return {'access_token': outer.token}
        return Response()


def test_a_token_in_the_environment_is_used_as_it_is(common):
    post = FakePost()
    token, renew = common.get_token('http://x', None, environ={'CSC_IMPORT_TOKEN': ' abc \n'}, post=post)
    assert token == 'abc' and renew is None and post.calls == []


def test_the_password_is_asked_and_exchanged_at_the_token_route(common):
    post, asked = FakePost(), []
    token, renew = common.get_token('http://x/', 'someone', environ={}, post=post,
                                    ask=lambda prompt: asked.append(prompt) or 'the-password')
    assert token == 'tok-1' and len(asked) == 1 and 'someone' in asked[0]
    assert 'the-password' not in asked[0]                                # the prompt never holds it
    call = post.calls[0]
    assert call['url'] == 'http://x/auth/token'
    assert call['data'] == {'username': 'someone', 'password': 'the-password'}
    assert call['headers']['X-CSC-Client'].startswith('catalog-import/')
    # a run that outlives the token signs in again with the same password, without asking again
    post.token = 'tok-2'
    assert renew() == 'tok-2' and len(asked) == 1 and len(post.calls) == 2


def test_a_failed_sign_in_stops_without_the_reason_or_the_password(common):
    with pytest.raises(SystemExit) as stop:
        common.get_token('http://x', 'someone', environ={}, post=FakePost(status=401),
                         ask=lambda _p: 'secret-value')
    assert 'sign-in failed (401)' in str(stop.value) and 'secret-value' not in str(stop.value)


def test_no_token_and_no_username_is_an_error(common):
    with pytest.raises(SystemExit) as stop:
        common.get_token('http://x', None, environ={})
    assert 'CSC_IMPORT_TOKEN' in str(stop.value) and '--username' in str(stop.value)


# MORE WAYS TO NAME A REMOTE DATABASE (review note) --------------------------------------
@pytest.mark.parametrize('uri', [
    'mongodb://localhost:27017,remote.example:27017/x',
    'mongodb://127.0.0.1:27017,127.0.0.1:27018,db.example.org/x',
    'mongodb://user:pw@localhost,remote.example/x',
    'mongodb+srv://localhost/x',
    'mongodb+srv://cluster.example.net/csc',
    'http://127.0.0.1:27017',
    'mongodb://localhost@remote.example/x'])
def test_srv_and_multi_host_uris_are_refused(common, uri):
    with pytest.raises(SystemExit) as stop:
        common.require_local(uri)
    assert 'refusing' in str(stop.value) and 'on this machine' in str(stop.value)


def test_a_single_local_host_with_credentials_and_options_is_still_accepted(common):
    for uri in ('mongodb://u:p@localhost:27017/csc?authSource=admin', 'mongodb://127.0.0.1/csc'):
        assert common.require_local(uri) == uri


# THE ASSET COPY MUST BE UNDER .dev (review note) ----------------------------------------
def test_the_default_asset_copy_is_accepted(common):
    assert common.require_dot_dev(common.DEFAULT_ASSETS, '--assets') == common.DEFAULT_ASSETS.resolve()
    assert common.require_dot_dev(common.DOT_DEV / 'somewhere' / 'else') .parent.name == 'somewhere'


@pytest.mark.parametrize('where', ['tmp', 'repo', 'scripts', 'dotdev-parent', 'dotdev-escape'])
def test_any_other_asset_folder_is_refused_with_a_pointer_to_the_readme(common, tmp_path, where):
    path = {'tmp': tmp_path / 'assets', 'repo': common.REPO, 'scripts': common.REPO / 'scripts',
            'dotdev-parent': common.DOT_DEV.parent,
            'dotdev-escape': common.DOT_DEV / '..' / 'scripts'}[where]
    with pytest.raises(SystemExit) as stop:
        common.require_dot_dev(path, '--assets')
    message = str(stop.value)
    assert 'is not inside' in message and 'README' in message and '--sweep' in message


def test_derive_local_refuses_an_asset_folder_outside_dot_dev_before_it_connects(script_loader, tmp_path):
    pytest.importorskip('pymongo')
    derive = script_loader('derive_local')
    with pytest.raises(SystemExit) as stop:
        derive.main(['--assets', str(tmp_path / 'assets')])
    assert '--assets' in str(stop.value) and 'is not inside' in str(stop.value)


def test_derive_local_still_defaults_to_the_local_asset_copy(script_loader, common):
    pytest.importorskip('pymongo')
    derive = script_loader('derive_local')
    assert derive.common.DEFAULT_ASSETS == common.DEFAULT_ASSETS
    assert common.DEFAULT_ASSETS.relative_to(common.DOT_DEV)           # inside .dev


# THE API CLIENT: RETRIES (decision 8.157 f) ---------------------------------------------------------
class Wire:
    """A transport that answers from a script: a status code, an exception, or a (status, headers) pair."""

    def __init__(self, *script):
        self.script, self.calls = list(script), []

    def request(self, method, url, headers=None, timeout=None, **kw):
        self.calls.append((method, url))
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        status, headers = step if isinstance(step, tuple) else (step, {})

        class Response:
            status_code = status
            content = b'{}'
            text = '{}'

            def __init__(self):
                self.headers = headers

            def json(self):
                return {}
        return Response()


@pytest.fixture
def api_with(common):
    pytest.importorskip('requests')

    def build(*script, renew=None):
        waits = []
        api = common.Api('http://x/', 'tok', renew=renew, sleep=waits.append)
        api.http = Wire(*script)
        return api, waits
    return build


def test_a_503_is_tried_again_and_the_server_s_retry_after_is_honoured(api_with):
    api, waits = api_with((503, {'Retry-After': '7'}), 503, 200)
    assert api.request('GET', '/x').status_code == 200
    assert waits == [7.0, 2.0]                       # the header, then the growing default (1, 2, 4)
    assert api.calls == 3 and api.retried == 2


def test_a_connection_error_and_a_timeout_are_tried_again(api_with):
    import requests
    api, waits = api_with(requests.ConnectionError('reset'), requests.Timeout('slow'), 200)
    assert api.request('POST', '/x').status_code == 200
    assert waits == [1.0, 2.0] and api.calls == 3


def test_it_gives_up_after_three_retries(api_with):
    import requests
    api, waits = api_with(503, 503, 503, 503, 200)
    assert api.request('GET', '/x').status_code == 503           # the fourth 503 is the answer
    assert len(waits) == 3 and api.calls == 4
    api, waits = api_with(*[requests.ConnectionError('gone')] * 4)
    with pytest.raises(requests.ConnectionError):
        api.request('GET', '/x')
    assert len(waits) == 3 and api.calls == 4


@pytest.mark.parametrize('status', [500, 502, 504, 400, 404, 409, 422])
def test_any_other_error_fails_at_once(api_with, status):
    api, waits = api_with(status, 200)
    assert api.request('GET', '/x').status_code == status
    assert waits == [] and api.calls == 1
    with pytest.raises(RuntimeError, match=str(status)):
        api_with(status)[0].json('GET', '/x')


@pytest.mark.parametrize('header, wait', [('0', 0.0), ('3', 3.0), ('600', 60.0), ('soon', 1.0), (None, 1.0)])
def test_the_wait_is_bounded_and_falls_back_to_a_short_one(common, header, wait):
    assert common.retry_wait(0, header) == wait


def test_a_renewed_token_and_a_retry_work_together(api_with):
    api, waits = api_with(401, 503, 200, renew=lambda: 'tok-2')
    assert api.request('GET', '/x').status_code == 200
    assert api.token == 'tok-2' and waits == [1.0]
