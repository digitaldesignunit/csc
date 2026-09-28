"""/version and the GH interface release that belongs to this backend."""

import httpx

from csc_version import CSC_VERSION, release_tag


def test_version_is_public(api):
    response = api.get('/version')
    assert response.status_code == 200
    assert response.json() == {'version': CSC_VERSION, 'tag': release_tag()}


def test_missing_release_is_a_clear_404(api, auth_headers, monkeypatch):
    from services.github_service import GitHubService

    async def not_found(self, tag):
        request = httpx.Request('GET', f'https://api.github.com/x/{tag}')
        raise httpx.HTTPStatusError(
            'not found', request=request,
            response=httpx.Response(404, request=request))

    monkeypatch.setattr(GitHubService, 'get_release_by_tag', not_found)
    headers = auth_headers('user')
    for path in ('/ghinterface/version', '/ghinterface/download'):
        response = api.get(path, headers=headers)
        assert response.status_code == 404, (path, response.text)
        assert release_tag() in response.json()['detail']


def test_version_lists_only_the_gh_interface_asset(api, auth_headers, monkeypatch):
    from services.github_service import GitHubService

    async def release(self, tag):
        return {'tag_name': tag, 'name': tag, 'assets': [
            {'name': f'csc-frontend-{CSC_VERSION}.zip'},
            {'name': f'csc-gh-interface-{CSC_VERSION}.zip'},
        ]}

    monkeypatch.setattr(GitHubService, 'get_release_by_tag', release)
    body = api.get('/ghinterface/version', headers=auth_headers('user')).json()
    assert body['tag_name'] == release_tag()
    assert [a['name'] for a in body['assets']] == [
        f'csc-gh-interface-{CSC_VERSION}.zip']
