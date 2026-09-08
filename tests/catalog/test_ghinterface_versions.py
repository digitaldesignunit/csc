"""Tests for Grasshopper component source version parsing."""

import asyncio

import httpx
import pytest
from fastapi import HTTPException

from apps.catalog.api.ghinterface import (
    _get_repo_entry_content,
    compare_versions,
    get_source_version,
    resolve_update_channel,
)


def test_version_declaration_is_parsed():
    assert get_source_version('    Version: 260611') == (260611, 0, 0)


def test_dotted_and_lettered_versions_are_parsed():
    assert get_source_version('Version: 251009.1') == (251009, 1, 0)
    assert get_source_version('Version: 251009a') == (251009, 0, 1)


def test_prose_mentioning_version_does_not_shadow_declaration():
    source = (
        "ghenv.Component.Description = (\n"
        "    'Creates a catalog identity and version-0 snapshot via "
        "POST /identities. '\n"
        ")\n"
        '    Version: 260611\n'
    )
    assert get_source_version(source) == (260611, 0, 0)


def test_source_without_declaration_has_no_version():
    source = 'Snapshot UUIDs (ordered by version)\nreturn 0\n'
    assert get_source_version(source) is None


def test_newer_server_version_compares_greater():
    server = get_source_version('Version: 260611')
    document = get_source_version('Version: 260610')
    assert compare_versions(server, document) == 1
    assert compare_versions(document, server) == -1
    assert compare_versions(server, server) == 0


def test_resolve_update_channel_defaults_to_main():
    assert resolve_update_channel(None) == 'main'
    assert resolve_update_channel('') == 'main'
    assert resolve_update_channel('main') == 'main'


def test_resolve_update_channel_preserves_exact_branch_name():
    assert resolve_update_channel('feature/gh-xml') == 'feature/gh-xml'
    assert resolve_update_channel('develop') == 'develop'


def test_resolve_update_channel_rejects_invalid_names():
    with pytest.raises(HTTPException) as exc:
        resolve_update_channel('has space')
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        resolve_update_channel('../main')
    assert exc.value.status_code == 400


def test_entry_content_without_token_uses_download_url():
    """Unauthenticated REST is 60 req/hour; raw download_url does not count."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=b'Version: 260908')

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            content = await _get_repo_entry_content(
                client,
                'https://api.github.com/repos/digitaldesignunit/csc',
                None,
                {
                    'sha': 'abc123',
                    'path': 'grasshopper_userobjects_src/Foo.py',
                    'download_url': (
                        'https://raw.githubusercontent.com/digitaldesignunit/'
                        'csc/main/grasshopper_userobjects_src/Foo.py'
                    ),
                },
                'main',
            )
            assert content == b'Version: 260908'

    asyncio.run(run())
    assert calls == [
        'https://raw.githubusercontent.com/digitaldesignunit/'
        'csc/main/grasshopper_userobjects_src/Foo.py'
    ]
    assert not any('/git/blobs/' in url for url in calls)


def test_entry_content_with_token_uses_blobs_api():
    """A valid PAT should stay on api.github.com (5000 req/hour)."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=b'Version: 260908')

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            content = await _get_repo_entry_content(
                client,
                'https://api.github.com/repos/digitaldesignunit/csc',
                'ghp_valid',
                {
                    'sha': 'abc123',
                    'path': 'grasshopper_userobjects_src/Foo.py',
                    'download_url': (
                        'https://raw.githubusercontent.com/digitaldesignunit/'
                        'csc/main/grasshopper_userobjects_src/Foo.py'
                    ),
                },
                'main',
            )
            assert content == b'Version: 260908'

    asyncio.run(run())
    assert calls == [
        'https://api.github.com/repos/digitaldesignunit/csc/git/blobs/abc123'
    ]


def test_github_timeout_is_described_in_503():
    from apps.catalog.api.ghinterface import _http_exception_from_github

    exc = _http_exception_from_github(httpx.TimeoutException('timed out'))
    assert exc.status_code == 503
    assert 'timed out' in exc.detail
