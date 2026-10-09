"""The component reference of the Grasshopper page (plan P11 stage 3, decision
8.118 C-5): the sources of a release are parsed with ``ast`` and never run."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.catalog.api import ghinterface
from apps.catalog.ghreference import build_reference, parse_source

SOURCES = Path(__file__).resolve().parents[2] / 'grasshopper_userobjects_src'

SAMPLE = '''#! python3
# -*- coding: utf-8 -*-
import Grasshopper  # NOQA

ghenv.Component.Name = 'Sample'  # NOQA
ghenv.Component.NickName = 'Smp'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '2 Catalog Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Lists things. '
    'Second sentence.'
)

OUTPUTS = [
    ('Ids', 'Ids',
     'Identity UUIDs'),
    ('Names', 'Nm', 'Names, parallel to Ids'),
]


class CSC_Sample(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: nobody
    Version: 261005
    """

    def BeforeRunScript(self):
        self.InputParams[0].Description = (
            'The dataset '
            'slug'
        )
        self.InputParams[1].Description = 'Optional filter'

    def RunScript(self, Dataset, Filter, Run):
        return (None, None)
'''


def test_a_source_gives_its_name_inputs_and_outputs():
    entry = parse_source('DDU_CSC_Sample.py', SAMPLE)
    assert entry['name'] == 'Sample' and entry['nickname'] == 'Smp'
    assert entry['category'] == 'DDU_CSC'
    assert entry['subcategory'] == '2 Catalog Interface'
    assert entry['description'] == 'Lists things. Second sentence.'
    assert entry['version'] == '261005'
    assert entry['inputs'] == [
        {'name': 'Dataset', 'description': 'The dataset slug'},
        {'name': 'Filter', 'description': 'Optional filter'},
        {'name': 'Run', 'description': ''},
    ]
    assert entry['outputs'] == [
        {'name': 'Ids', 'nickname': 'Ids', 'description': 'Identity UUIDs'},
        {'name': 'Names', 'nickname': 'Nm', 'description': 'Names, parallel to Ids'},
    ]


def test_no_outputs_is_told_apart_from_outputs_not_declared():
    declared_empty = SAMPLE.replace(
        SAMPLE[SAMPLE.index('OUTPUTS = ['):SAMPLE.index('class CSC_Sample')],
        'OUTPUTS = []' + chr(10) * 3)
    entry = parse_source('DDU_CSC_Sample.py', declared_empty)
    assert entry['outputs'] == [] and entry['outputs_declared'] is True
    declared = parse_source('DDU_CSC_Sample.py', SAMPLE)
    assert len(declared['outputs']) == 2 and declared['outputs_declared'] is True
    # a 0.5 source has no OUTPUTS at all
    none = SAMPLE.replace(
        SAMPLE[SAMPLE.index('OUTPUTS = ['):SAMPLE.index('class CSC_Sample')], '')
    old = parse_source('DDU_CSC_Sample.py', none)
    assert old['outputs'] == [] and old['outputs_declared'] is False


def test_a_source_that_does_not_parse_is_skipped_with_a_note():
    entry = parse_source('DDU_CSC_Broken.py', 'def RunScript(self,\n  x = (')
    assert entry['file'] == 'DDU_CSC_Broken.py'
    assert entry['skipped'].startswith('not parsed')
    assert parse_source('x.py', '')['skipped'] == 'not a component source'
    body = build_reference('v1', [entry, parse_source('DDU_CSC_Sample.py', SAMPLE)])
    assert [c['name'] for c in body['components']] == ['Sample']
    assert body['skipped'] == [{'file': 'DDU_CSC_Broken.py', 'note': entry['skipped']}]


def test_the_sources_are_not_executed(tmp_path):
    """A top-level side effect, a failing call and a dynamic value stay unrun."""
    marker = tmp_path / 'ran.txt'
    source = SAMPLE + f'''
open({str(marker)!r}, 'w').write('executed')
raise SystemExit('this must not run')
ghenv.Component.Description = __import__('os').getcwd()
'''
    entry = parse_source('DDU_CSC_Evil.py', source)
    assert not marker.exists()
    assert entry['name'] == 'Sample'
    # a value that is not a literal reads as empty, it is never evaluated
    assert entry['description'] == ''


def test_the_real_sources_all_parse_with_inputs_and_outputs_described():
    parsed = [parse_source(p.name, p.read_text(encoding='utf-8'))
              for p in sorted(SOURCES.glob('*.py'))]
    body = build_reference('worktree', parsed)
    assert body['skipped'] == []
    assert len(body['components']) >= 40
    by_file = {c['file']: c for c in body['components']}
    snap = by_file['DDU_CSC_ListIdentitySnapshots.py']
    assert [o['name'] for o in snap['outputs']] == ['SnapshotID', 'SnapshotName']
    assert snap['inputs'][0]['name'] == 'Input' and snap['inputs'][0]['description']
    for component in body['components']:
        assert component['subcategory'], component['file']


@pytest.fixture
def github(monkeypatch):
    sources = {
        'DDU_CSC_Sample.py': SAMPLE,
        'DDU_CSC_Broken.py': 'def (',
        'DDU_CSC_Ignored.cs': 'class X {}',
    }
    calls = {'content': 0, 'listing': 0}

    async def listing(client, api_base, token, path, ref):
        assert path == 'grasshopper_userobjects_src'
        calls['listing'] += 1
        return [{'type': 'file', 'name': name, 'sha': 'sha-' + name}
                for name in sources] + [{'type': 'dir', 'name': 'sub'}]

    async def content(client, api_base, token, entry, ref):
        calls['content'] += 1
        return sources[entry['name']].encode('utf-8')

    monkeypatch.setattr(ghinterface, '_list_repo_dir_cached', listing)
    monkeypatch.setattr(ghinterface, '_get_repo_entry_content', content)
    monkeypatch.setenv('GITHUB_REPO_URL', 'https://github.com/example/csc')
    ghinterface._blob_reference_cache.clear()
    return calls


def test_the_reference_route_answers_anonymous_callers(api, github):
    got = api.get('/ghinterface/reference')
    assert got.status_code == 200, got.text
    body = got.json()
    assert [c['name'] for c in body['components']] == ['Sample']
    assert [s['file'] for s in body['skipped']] == ['DDU_CSC_Broken.py']
    assert got.headers['cache-control'] == 'public, max-age=300'
    assert body['ref']


def test_an_anonymous_caller_cannot_choose_the_ref(api, auth_headers, monkeypatch):
    """?channel= is ignored without an account (no GitHub calls for a ref of the
    caller's choosing); a signed-in caller keeps it."""
    refs = []

    async def listing(client, api_base, token, path, ref):
        refs.append(ref)
        return [{'type': 'file', 'name': 'DDU_CSC_Sample.py', 'sha': 'sha-' + ref}]

    async def content(client, api_base, token, entry, ref):
        return SAMPLE.encode('utf-8')

    monkeypatch.setattr(ghinterface, '_list_repo_dir_cached', listing)
    monkeypatch.setattr(ghinterface, '_get_repo_entry_content', content)
    monkeypatch.setenv('GITHUB_REPO_URL', 'https://github.com/example/csc')
    ghinterface._blob_reference_cache.clear()
    release = ghinterface.default_update_ref()
    anonymous = api.get('/ghinterface/reference', params={'channel': 'main'})
    assert anonymous.status_code == 200, anonymous.text
    assert anonymous.json()['ref'] == release
    assert refs == [release]               # no listing for "main"
    signed = api.get('/ghinterface/reference', params={'channel': 'main'},
                     headers=auth_headers('user'))
    assert signed.status_code == 200, signed.text
    assert signed.json()['ref'] == 'main'
    assert refs == [release, 'main']
    # the existing validation still applies to a signed-in caller
    bad = api.get('/ghinterface/reference', params={'channel': 'a..b'},
                  headers=auth_headers('user'))
    assert bad.status_code == 400


def test_a_blob_is_read_once_per_sha(api, github):
    assert api.get('/ghinterface/reference').status_code == 200
    first = github['content']
    assert first == 2                      # the two .py files, not the .cs
    assert api.get('/ghinterface/reference').status_code == 200
    assert github['content'] == first      # parsed already: no new read
    assert github['listing'] == 2


def test_the_version_route_answers_anonymous_callers(api, monkeypatch):
    async def release(github_service):
        return {'tag_name': 'v0.6.0.0', 'name': 'v0.6.0.0',
                'published_at': '2026-10-01T00:00:00Z', 'html_url': 'https://example.org/r',
                'assets': [{'name': 'csc-gh-interface-0.6.0.0.zip', 'size': 10}]}

    monkeypatch.setattr(ghinterface, '_release_of_this_backend', release)
    monkeypatch.setenv('GITHUB_REPO_URL', 'https://github.com/example/csc')
    got = api.get('/ghinterface/version')
    assert got.status_code == 200, got.text
    assert got.json()['version'] == 'v0.6.0.0'


def test_the_other_routes_still_need_an_account(api, github):
    for url in ('/ghinterface/download', '/ghinterface/src_names',
                '/ghinterface/src/DDU_CSC_Sample', '/ghinterface/xml_names',
                '/ghinterface/library_manifest', '/ghinterface/userobject_names'):
        assert api.get(url).status_code == 401, url
