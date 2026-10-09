"""The user object XML for copy and paste (plan P11 stage 3, decision 8.118):
an anonymous caller reads the release of this backend from GitHub, nothing
else; a signed-in caller keeps the server's XML directory."""

from __future__ import annotations

from apps.catalog.api import ghinterface

XML = b'<?xml version="1.0"?><Archive name="DDU_CSC_Sample"/>'


def _github(monkeypatch):
    seen = {'refs': [], 'paths': [], 'reads': 0}

    async def listing(client, api_base, token, path, ref):
        seen['refs'].append(ref)
        seen['paths'].append(path)
        return [{'type': 'file', 'name': 'DDU_CSC_Sample.xml',
                 'sha': 'sha-sample', 'path': f'{path}/DDU_CSC_Sample.xml'}]

    async def content(client, api_base, token, entry, ref):
        seen['reads'] += 1
        return XML

    monkeypatch.setattr(ghinterface, '_list_repo_dir_cached', listing)
    monkeypatch.setattr(ghinterface, '_get_repo_entry_content', content)
    monkeypatch.setenv('GITHUB_REPO_URL', 'https://github.com/example/csc')
    ghinterface._blob_xml_cache.clear()
    return seen


def test_an_anonymous_caller_gets_the_xml_of_the_release(api, monkeypatch):
    seen = _github(monkeypatch)
    got = api.get('/ghinterface/xml/DDU_CSC_Sample')
    assert got.status_code == 200, got.text
    assert got.content == XML
    assert got.headers['content-type'].startswith('text/xml')
    assert got.headers['cache-control'] == 'public, max-age=300'
    assert seen['refs'] == [ghinterface.default_update_ref()]
    assert seen['paths'] == ['grasshopper_userobjects_xml']
    assert api.get('/ghinterface/xml/DDU_CSC_Missing').status_code == 404


def test_an_anonymous_caller_cannot_choose_the_ref(api, monkeypatch):
    seen = _github(monkeypatch)
    got = api.get('/ghinterface/xml/DDU_CSC_Sample',
                  params={'channel': 'main', 'ref': 'main'})
    assert got.status_code == 200, got.text
    assert seen['refs'] == [ghinterface.default_update_ref()]


def test_the_file_is_read_once_per_blob_sha(api, monkeypatch):
    seen = _github(monkeypatch)
    assert api.get('/ghinterface/xml/DDU_CSC_Sample').status_code == 200
    assert api.get('/ghinterface/xml/DDU_CSC_Sample').status_code == 200
    assert seen['reads'] == 1


def test_a_bad_name_is_refused(api, monkeypatch):
    seen = _github(monkeypatch)
    for name in ('DDU_CSC_a..b', 'Sample', 'DDU_other', 'DDU_CSC_a%5Cb'):
        assert api.get(f'/ghinterface/xml/{name}').status_code == 400, name
    assert seen['refs'] == []                # nothing was asked of GitHub


def test_a_signed_in_caller_keeps_the_server_directory(api, auth_headers, monkeypatch, tmp_path):
    seen = _github(monkeypatch)
    (tmp_path / 'DDU_CSC_Local.xml').write_bytes(b'<local/>')
    api.app.gh_xml_cache_dir = str(tmp_path)
    got = api.get('/ghinterface/xml/DDU_CSC_Local', headers=auth_headers('user'))
    assert got.status_code == 200 and got.content == b'<local/>'
    missing = api.get('/ghinterface/xml/DDU_CSC_Sample', headers=auth_headers('user'))
    assert missing.status_code == 404
    assert seen['refs'] == []                # not read from GitHub


def test_the_download_still_needs_an_account(api):
    assert api.get('/ghinterface/download').status_code == 401
