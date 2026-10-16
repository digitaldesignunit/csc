"""What a failing GitHub call leaves in the log (decision 8.144 h): the label,
the class of the error and the status --- never the URL (the ``ref`` in it is
the channel the client typed; a download URL is pre-signed), the response body
or a traceback."""

from __future__ import annotations

import logging

import httpx
import pytest

from apps.catalog.api import ghinterface

CHANNEL = 'typed-by-the-client-channel'
SIGNED = ('https://objects.githubusercontent.com/asset?X-Amz-Signature='
          'deadbeefdeadbeef&X-Amz-Credential=AKIAEXAMPLE')
BODY = 'github-error-body-with-details'


def failure(url, status=502):
    request = httpx.Request('GET', url)
    response = httpx.Response(status, request=request, text=BODY)
    return httpx.HTTPStatusError(f'Server error for url {url}', request=request,
                                 response=response)


def leaked(text):
    return [s for s in (CHANNEL, 'X-Amz-Signature', 'deadbeef', 'AKIAEXAMPLE', BODY,
                        'Traceback', 'objects.githubusercontent.com') if s in text]


@pytest.fixture(autouse=True)
def repo(env):
    env(GITHUB_REPO_URL='https://github.com/example/csc')


def test_the_helper_names_the_class_and_the_status_only():
    text = ghinterface._failure_text(failure(SIGNED, 502))
    assert text == 'HTTPStatusError (status 502)'
    assert ghinterface._failure_text(httpx.ConnectError('boom ' + CHANNEL)) == 'ConnectError'
    assert ghinterface._failure_text(ValueError(CHANNEL)) == 'ValueError'


def test_a_listing_error_with_the_clients_channel_leaves_no_channel_in_the_log(
        api, auth_headers, monkeypatch, caplog):
    async def listing(client, api_base, token, path, ref):
        raise failure(f'https://api.github.com/repos/example/csc/contents/x?ref={ref}')
    monkeypatch.setattr(ghinterface, '_list_repo_dir_cached', listing)
    with caplog.at_level(logging.INFO, logger='csc'):
        response = api.get('/ghinterface/src_names', params={'channel': CHANNEL},
                           headers=auth_headers('user'))
    assert response.status_code >= 500
    assert 'list_src_names GitHub: HTTPStatusError (status 502)' in caplog.text
    assert leaked(caplog.text) == []
    assert all(r.exc_info is None for r in caplog.records if r.name.startswith('csc'))


def test_a_download_error_logs_neither_the_signed_url_nor_the_body(
        api, auth_headers, monkeypatch, caplog):
    async def release(_service):
        return {'assets': [], 'tag_name': 'v1'}
    monkeypatch.setattr(ghinterface, '_release_of_this_backend', release)
    monkeypatch.setattr(ghinterface.GitHubService, 'get_release_asset_download_url',
                        lambda self, info, prefix: SIGNED)

    async def filename(self, info, prefix):
        return 'csc-gh-interface-1.zip'
    monkeypatch.setattr(ghinterface.GitHubService, 'get_asset_filename', filename)

    class Stream:
        async def __aenter__(self):
            raise failure(SIGNED, 403)

        async def __aexit__(self, *args):
            return False
    monkeypatch.setattr(httpx.AsyncClient, 'stream', lambda self, *a, **k: Stream())
    with caplog.at_level(logging.INFO, logger='csc'):
        with pytest.raises(httpx.HTTPStatusError):
            api.get('/ghinterface/download', headers=auth_headers('user'))
    assert 'GitHub download failed: HTTPStatusError (status 403)' in caplog.text
    assert leaked(caplog.text) == []
