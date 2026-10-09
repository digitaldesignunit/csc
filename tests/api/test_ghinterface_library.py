"""The shared Grasshopper library as CSC_Update gets it (decision 8.111): a
manifest with the version and a sha256 per file, and the files one by one."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from apps.catalog.api import ghinterface

PACKAGE = Path(__file__).resolve().parents[2] / 'grasshopper_lib' / 'csc_gh'


def _files():
    return {p.name: p.read_bytes() for p in PACKAGE.glob('*.py')}


def test_only_python_files_of_the_package_folder_are_library_files():
    for name in ('__init__.py', 'build.py', 'ply.py', 'doc.py'):
        assert ghinterface.is_library_file(name), name
    for name in ('', '.hidden.py', 'a/b.py', '..\\x.py', 'build.pyc',
                 'Build.py', 'x.txt', '__pycache__'):
        assert not ghinterface.is_library_file(name), name


def test_the_manifest_has_the_version_and_a_checksum_per_file():
    manifest = ghinterface.library_manifest('v0.6.0.0', _files())
    init = (PACKAGE / '__init__.py').read_text(encoding='utf-8')
    version = re.search(r"^__version__ = '(\w+)'$", init, re.M).group(1)
    assert manifest['version'] == version and manifest['ref'] == 'v0.6.0.0'
    names = [f['path'] for f in manifest['files']]
    assert names == sorted(names) and '__init__.py' in names
    for entry in manifest['files']:
        data = (PACKAGE / entry['path']).read_bytes()
        assert entry['size'] == len(data)
        assert entry['sha256'] == hashlib.sha256(data).hexdigest()


def test_a_library_without_a_version_has_none():
    assert ghinterface.library_manifest('r', {'__init__.py': b'x = 1\n'})[
        'version'] is None
    assert ghinterface.library_manifest('r', {})['version'] is None


@pytest.fixture
def github(monkeypatch):
    files = _files()

    async def listing(client, api_base, token, path, ref):
        assert path == 'grasshopper_lib/csc_gh'
        return [{'type': 'file', 'name': name, 'sha': 's-' + name}
                for name in files] + [
            {'type': 'dir', 'name': '__pycache__'},
            {'type': 'file', 'name': 'notes.txt'}]

    async def content(client, api_base, token, entry, ref):
        return files[entry['name']]

    monkeypatch.setattr(ghinterface, '_list_repo_dir_cached', listing)
    monkeypatch.setattr(ghinterface, '_get_repo_entry_content', content)
    monkeypatch.setenv('GITHUB_REPO_URL', 'https://github.com/example/csc')
    return files


def test_the_routes_serve_the_manifest_and_the_files(api, auth_headers,
                                                     github):
    headers = auth_headers('user')
    manifest = api.get('/ghinterface/library_manifest', headers=headers)
    assert manifest.status_code == 200, manifest.text
    body = manifest.json()
    assert {f['path'] for f in body['files']} == set(github)
    for entry in body['files']:
        got = api.get('/ghinterface/library/' + entry['path'],
                      headers=headers)
        assert got.status_code == 200
        assert hashlib.sha256(got.content).hexdigest() == entry['sha256']
    assert api.get('/ghinterface/library/notes.txt',
                   headers=headers).status_code == 404
    assert api.get('/ghinterface/library/nothere.py',
                   headers=headers).status_code == 404


def test_the_routes_need_an_account(api):
    assert api.get('/ghinterface/library_manifest').status_code == 401
    assert api.get('/ghinterface/library/build.py').status_code == 401
