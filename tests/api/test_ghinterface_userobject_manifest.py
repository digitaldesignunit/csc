"""The user objects as CSC_Update gets them (decision 8.155): a manifest with
the name, size and sha256 of every .ghuser of the channel and the version of
the channel; the two older routes stay as they are."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from apps.catalog.api.ghinterface import userobjects

FOLDER = Path(__file__).resolve().parents[2] / 'grasshopper_userobjects'


@pytest.fixture(autouse=True)
def repo(env):
    env(GITHUB_REPO_URL='https://github.com/example/csc')
    userobjects._digest_cache.clear()


def _files():
    return {p.stem: p.read_bytes() for p in sorted(FOLDER.glob('*.ghuser'))}


# THE BUILDER --------------------------------------------------------------------
def test_the_manifest_lists_name_size_and_sha256_sorted_by_name():
    files = {'DDU_CSC_B': b'bb', 'DDU_CSC_A': b'a'}
    manifest = userobjects.userobject_manifest(
        'v0.6.2.0', {n: userobjects.digest_of(d) for n, d in files.items()})
    assert manifest['ref'] == 'v0.6.2.0'
    assert manifest['version'] == '0.6.2.0'
    assert manifest['files'] == [
        {'name': 'DDU_CSC_A', 'size': 1, 'sha256': hashlib.sha256(b'a').hexdigest()},
        {'name': 'DDU_CSC_B', 'size': 2, 'sha256': hashlib.sha256(b'bb').hexdigest()},
    ]


@pytest.mark.parametrize('ref, version', [
    ('v0.6.2.0', '0.6.2.0'), ('v0.6.2.0-rc1', '0.6.2.0-rc1'), ('main', 'main'),
    ('feature/x', 'feature/x'), ('v1', 'v1'), ('version-2', 'version-2'),
])
def test_the_channel_version_is_the_release_version_of_a_tag_else_the_name(ref, version):
    assert userobjects.channel_version(ref) == version


def test_an_empty_channel_has_no_files():
    assert userobjects.userobject_manifest('main', {})['files'] == []


def test_the_digest_is_the_size_and_the_sha256():
    assert userobjects.digest_of(b'abc') == (3, hashlib.sha256(b'abc').hexdigest())


# THE ROUTE ----------------------------------------------------------------------
@pytest.fixture
def github(monkeypatch):
    files = _files()
    reads = []

    async def listing(client, api_base, token, path, ref):
        assert path == 'grasshopper_userobjects'
        return [{'type': 'file', 'name': name + '.ghuser', 'sha': 'blob-' + name}
                for name in files] + [
            {'type': 'dir', 'name': 'sub'},
            {'type': 'file', 'name': 'notes.txt', 'sha': 'x'},
            {'type': 'file', 'name': 'README.md', 'sha': 'y'}]

    async def content(client, api_base, token, entry, ref):
        reads.append(entry['name'])
        return files[entry['name'][:-len('.ghuser')]]

    monkeypatch.setattr(userobjects, '_list_repo_dir_cached', listing)
    monkeypatch.setattr(userobjects, '_get_repo_entry_content', content)
    files['_reads'] = reads
    yield files
    files.pop('_reads', None)


def test_the_route_serves_the_manifest_of_the_ghuser_files(api, auth_headers, github):
    reads = github.pop('_reads')
    headers = auth_headers('user')
    got = api.get('/ghinterface/userobject_manifest', headers=headers)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body['ref'] and body['version']
    assert {f['name'] for f in body['files']} == set(github)
    assert len(body['files']) > 40
    for entry in body['files']:
        data = github[entry['name']]
        assert entry['size'] == len(data)
        assert entry['sha256'] == hashlib.sha256(data).hexdigest()
    assert len(reads) == len(github)


def test_a_second_request_reads_no_file_it_has_seen(api, auth_headers, github):
    reads = github.pop('_reads')
    headers = auth_headers('user')
    api.get('/ghinterface/userobject_manifest', headers=headers)
    first = len(reads)
    again = api.get('/ghinterface/userobject_manifest', headers=headers)
    assert again.status_code == 200
    assert len(reads) == first                 # the blob shas are known


def test_the_channel_is_passed_through(api, auth_headers, github):
    github.pop('_reads')
    got = api.get('/ghinterface/userobject_manifest', params={'channel': 'v0.6.2.0'},
                  headers=auth_headers('user'))
    assert got.json()['ref'] == 'v0.6.2.0' and got.json()['version'] == '0.6.2.0'
    bad = api.get('/ghinterface/userobject_manifest', params={'channel': 'a..b'},
                  headers=auth_headers('user'))
    assert bad.status_code == 400


def test_the_route_needs_an_account(api):
    assert api.get('/ghinterface/userobject_manifest').status_code == 401


def test_the_older_routes_are_unchanged(api, auth_headers, github):
    github.pop('_reads')
    headers = auth_headers('user')
    names = api.get('/ghinterface/userobject_names', headers=headers)
    assert names.status_code == 200 and names.json() == sorted(github)
    one = sorted(github)[0]
    got = api.get('/ghinterface/userobject/' + one, headers=headers)
    assert got.status_code == 200 and got.content == github[one]
    assert got.headers['content-disposition'] == f'attachment; filename="{one}.ghuser"'
