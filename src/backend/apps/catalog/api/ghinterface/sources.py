#!/usr/bin/env python3.13
"""
Release, reference, ZIP, component sources and XML of the Grasshopper
interface.

* `GET /ghinterface/version`, `/ghinterface/reference`,
  `/ghinterface/download`
* `GET /ghinterface/src_names`, `/ghinterface/src/{name}`
* `GET /ghinterface/xml_names`, `/ghinterface/xml/{name}`
"""

import asyncio
import hashlib
import json
import os
import re
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse
import httpx

from apps.catalog.api.auth import get_current_user, get_optional_current_user
from apps.catalog.api.catalog_common import internal_error
from apps.catalog.ghreference import build_reference, parse_source
from apps.catalog.models import User
from limiter import local_limiter, signed_in_or_ip
from services.github_service import GitHubService
from settings import get_settings
from logging_setup import get_logger
from .github import (
    GH_INTERFACE_ASSET_PREFIX,
    GH_PUBLIC_RATE,
    SRC_FETCH_CONCURRENCY,
    _blob_reference_cache,
    _blob_version_cache,
    _blob_xml_cache,
    _extract_api_url,
    _failure_text,
    _get_repo_entry_content,
    _github_headers,
    _github_token,
    _http_exception_from_github,
    _list_repo_dir_cached,
    _release_of_this_backend,
    default_update_ref,
    resolve_update_channel,
)


log = get_logger(__name__)

router = APIRouter()


# Matches an actual version declaration - the word "version", a ":" or "=",
# then the number. The separator is required so prose such as 'creates a
# version-0 snapshot' in a component description cannot be mistaken for a
# version declaration.
VERSION_DECLARATION_RE = re.compile(
    r'version\s*[:=]\s*(\d+(?:\.\d+)?[a-zA-Z]?)')


def get_source_version(source):
    """Extract a comparable version tuple from Grasshopper component source."""
    for line in source.lower().split('\n'):
        version_match = VERSION_DECLARATION_RE.search(line)
        if version_match:
            return _parse_version_string(version_match.group(1))
    return None


def _parse_version_string(version_str):
    match = re.match(r'(\d+)(?:\.(\d+))?([a-zA-Z]*)', version_str)
    if not match:
        return None

    base_num = int(match.group(1))
    dot_num = int(match.group(2)) if match.group(2) else 0
    letter_suffix = match.group(3).lower() if match.group(3) else ''
    letter_num = ord(letter_suffix) - ord('a') + 1 if letter_suffix else 0

    return (base_num, dot_num, letter_num)


def compare_versions(version1, version2):
    if version1 is None and version2 is None:
        return 0
    if version1 is None:
        return -1
    if version2 is None:
        return 1

    for i in range(max(len(version1), len(version2))):
        v1_elem = version1[i] if i < len(version1) else 0
        v2_elem = version2[i] if i < len(version2) else 0

        if v1_elem < v2_elem:
            return -1
        if v1_elem > v2_elem:
            return 1

    return 0


def _compute_dir_etag(dir_path: str) -> str:
    h = hashlib.sha256()
    try:
        for name in sorted(os.listdir(dir_path)):
            if not name.lower().endswith('.xml'):
                continue
            full = os.path.join(dir_path, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            h.update(name.encode('utf-8', 'ignore'))
            h.update(str(int(st.st_mtime)).encode('ascii'))
    except FileNotFoundError:
        pass
    return 'W/"' + h.hexdigest()[:16] + '"'


# ROUTES ----------------------------------------------------------------------

@router.get('/ghinterface/version')
@local_limiter.limit(GH_PUBLIC_RATE, key_func=signed_in_or_ip)
async def get_gh_interface_version(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
):
    """The Grasshopper interface release that belongs to this backend."""
    try:
        repo_url = get_settings().need('GITHUB_REPO_URL')
        token = _github_token()
        github_service = GitHubService(repo_url, token)
        release_info = await _release_of_this_backend(github_service)

        assets = [
            a for a in release_info.get('assets', [])
            if a.get('name', '').startswith(GH_INTERFACE_ASSET_PREFIX)
        ]
        asset_info = []
        for asset in assets:
            asset_info.append({
                'name': asset['name'],
                'url': asset.get('url', 'N/A'),
                'browser_download_url': asset.get(
                    'browser_download_url', 'N/A'
                ),
                'size': asset.get('size', 0)
            })

        return {
            'version': release_info.get('tag_name', ''),
            'tag_name': release_info.get('tag_name', ''),
            'name': release_info.get('name', ''),
            'published_at': release_info.get('published_at', ''),
            'html_url': release_info.get('html_url', ''),
            'assets': asset_info
        }

    except HTTPException:
        raise
    except httpx.HTTPError as e:
        log.error('get_gh_interface_version GitHub: %s', _failure_text(e))
        raise _http_exception_from_github(e)
    except Exception:
        log.exception('get_gh_interface_version')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )


@router.get('/ghinterface/reference')
@local_limiter.limit(GH_PUBLIC_RATE, key_func=signed_in_or_ip)
async def get_component_reference(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    channel: str = Query(default=''),
):
    """
    The components of the release (a signed-in caller may name a ``?channel=``
    branch or tag; an anonymous caller always gets the release): name,
    nickname, subcategory, description, inputs from the ``RunScript``
    signature with the descriptions ``BeforeRunScript`` sets, outputs from
    ``OUTPUTS`` (decision 8.112). The sources are only parsed (``ast``), never
    run; one that does not parse is listed under ``skipped`` with a note. A
    parse is kept per blob sha, so a release costs one directory listing and
    the sources it has not read yet.
    """
    try:
        # an anonymous caller always gets the release this backend runs: every
        # new ref costs up to ~50 GitHub calls on the server's token, and ref
        # cycling by anyone could use up the quota CSC_Update needs too
        ref = resolve_update_channel(channel if current_user is not None else '')
        repo_url = get_settings().need('GITHUB_REPO_URL')
        token = _github_token()
        api_base = _extract_api_url(repo_url)

        async with httpx.AsyncClient(follow_redirects=True) as client:
            entries = await _list_repo_dir_cached(
                client, api_base, token, 'grasshopper_userobjects_src', ref)
            files = [
                item for item in entries
                if item.get('type') == 'file'
                and item.get('name', '').endswith('.py')
                and item.get('sha')
            ]
            semaphore = asyncio.Semaphore(SRC_FETCH_CONCURRENCY)
            todo = [i for i in files if i['sha'] not in _blob_reference_cache]

            async def read(item: dict) -> None:
                async with semaphore:
                    content = await _get_repo_entry_content(
                        client, api_base, token, item, ref)
                _blob_reference_cache[item['sha']] = parse_source(
                    item['name'], content.decode('utf-8', 'replace'))

            results = await asyncio.gather(
                *(read(item) for item in todo), return_exceptions=True)
            failures = [r for r in results if isinstance(r, Exception)]
            if failures and len(failures) == len(todo):
                raise failures[0]
            for item, result in zip(todo, results):
                if isinstance(result, Exception):
                    log.error('component reference %s: %s', item.get('name'),
                              _failure_text(result))
            parsed = []
            for item in files:
                entry = _blob_reference_cache.get(item['sha'])
                parsed.append(entry if entry is not None else {
                    'file': item['name'],
                    'skipped': 'the source could not be read'})
        body = build_reference(ref, parsed)
        return Response(
            json.dumps(body), media_type='application/json',
            headers={'Cache-Control': 'public, max-age=300'})
    except HTTPException:
        raise
    except httpx.HTTPError as e:
        log.error('get_component_reference GitHub: %s', _failure_text(e))
        raise _http_exception_from_github(e)
    except Exception:
        log.exception('get_component_reference')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )


@router.get('/ghinterface/download')
async def download_gh_interface(
    current_user: Annotated[User, Depends(get_current_user)]
):
    """Download this backend's Grasshopper interface release as a ZIP."""
    try:
        repo_url = get_settings().need('GITHUB_REPO_URL')
        token = _github_token()
        github_service = GitHubService(repo_url, token)
        release_info = await _release_of_this_backend(github_service)

        if not release_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No releases found in the repository"
            )

        download_url = github_service.get_release_asset_download_url(
            release_info, GH_INTERFACE_ASSET_PREFIX
        )
        filename = await github_service.get_asset_filename(
            release_info, GH_INTERFACE_ASSET_PREFIX
        )

        async def generate():
            async with httpx.AsyncClient(follow_redirects=True) as client:
                try:
                    headers = _github_headers(
                        token, accept='application/octet-stream'
                    )

                    async with client.stream(
                        'GET',
                        download_url,
                        headers=headers,
                        timeout=60.0,
                        follow_redirects=True
                    ) as response:
                        response.raise_for_status()
                        async for chunk in response.aiter_bytes(
                            chunk_size=8192
                        ):
                            yield chunk
                except httpx.HTTPStatusError as e:
                    # the URL is pre-signed and the body is GitHub's: neither
                    # goes to the log
                    log.warning('GitHub download failed: %s', _failure_text(e))
                    raise

        return StreamingResponse(
            generate(),
            media_type='application/zip',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'X-Release-Version': release_info.get('tag_name', ''),
                'X-Release-Name': release_info.get('name', '')
            }
        )

    except HTTPException:
        raise
    except httpx.HTTPError as e:
        log.error('download_gh_interface GitHub: %s', _failure_text(e))
        raise _http_exception_from_github(e)
    except ValueError as e:
        log.warning('download_gh_interface asset lookup: %s',
                    type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Release asset not found'
        )
    except Exception:
        log.exception('download_gh_interface')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )


@router.get('/ghinterface/src_names', response_model=List[str])
async def list_src_names(
    current_user: Annotated[User, Depends(get_current_user)],
    channel: str = Query(default=''),
):
    try:
        ref = resolve_update_channel(channel)
        repo_url = get_settings().need('GITHUB_REPO_URL')
        token = _github_token()
        api_base = _extract_api_url(repo_url)

        async with httpx.AsyncClient(follow_redirects=True) as client:
            entries = await _list_repo_dir_cached(
                client, api_base, token, 'grasshopper_userobjects_src', ref
            )
            files = [
                item for item in entries
                if item.get('type') == 'file'
                and '.' in item.get('name', '')
                and item.get('sha')
            ]

            semaphore = asyncio.Semaphore(SRC_FETCH_CONCURRENCY)
            to_fetch = [
                item for item in files
                if item['sha'] not in _blob_version_cache
            ]

            async def cache_version(item: dict) -> None:
                async with semaphore:
                    content_bytes = await _get_repo_entry_content(
                        client, api_base, token, item, ref
                    )
                text = content_bytes.decode('utf-8', 'replace')
                _blob_version_cache[item['sha']] = get_source_version(text)

            # Only files that were never read at this sha hit GitHub, and
            # they are read concurrently. In the steady state this route
            # costs a single (cached) directory listing.
            fetched = await asyncio.gather(
                *(cache_version(item) for item in to_fetch),
                return_exceptions=True,
            )
            failures = [
                result for result in fetched
                if isinstance(result, Exception)
            ]
            if failures and len(failures) == len(to_fetch):
                raise failures[0]
            for item, result in zip(to_fetch, fetched):
                if isinstance(result, Exception):
                    log.error('cache_version %s: %s', item.get('name'),
                              _failure_text(result))

            result: List[List[object]] = [
                [
                    item['name'].rsplit('.', 1)[0],
                    _blob_version_cache.get(item['sha']),
                ]
                for item in files
            ]
        return Response(
            json.dumps(result),
            media_type='application/json'
        )
    except HTTPException:
        raise
    except httpx.HTTPError as e:
        log.error('list_src_names GitHub: %s', _failure_text(e))
        raise _http_exception_from_github(e)
    except Exception:
        log.exception('list_src_names')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )


@router.get('/ghinterface/src/{name}', response_class=Response)
async def get_src_code(
    name: str,
    current_user: Annotated[User, Depends(get_current_user)],
    channel: str = Query(default=''),
):
    try:
        ref = resolve_update_channel(channel)
        repo_url = get_settings().need('GITHUB_REPO_URL')
        token = _github_token()
        api_base = _extract_api_url(repo_url)

        async with httpx.AsyncClient(follow_redirects=True) as client:
            entries = await _list_repo_dir_cached(
                client, api_base, token, 'grasshopper_userobjects_src', ref
            )
            matches = [
                it for it in entries
                if it.get('type') == 'file'
                and it.get('name', '').rsplit('.', 1)[0] == name
            ]
            if not matches:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail='Source file not found',
                )
            if len(matches) > 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail='Multiple source files share this name',
                )
            content = await _get_repo_entry_content(
                client, api_base, token, matches[0], ref
            )

        return Response(content, media_type='text/plain; charset=utf-8')
    except HTTPException:
        raise
    except httpx.HTTPError as e:
        log.error('get_src_code GitHub: %s', _failure_text(e))
        raise _http_exception_from_github(e)
    except Exception:
        log.exception('get_src_code')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )


@router.get('/ghinterface/xml_names', response_model=List[str])
async def list_xml_names(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)]
):
    try:
        cache_dir = request.app.gh_xml_cache_dir
        names: List[str] = []
        if os.path.isdir(cache_dir):
            for fname in os.listdir(cache_dir):
                if fname.lower().endswith('.xml'):
                    names.append(fname[:-4])
        names_sorted = sorted(list(dict.fromkeys(names)))

        etag = _compute_dir_etag(cache_dir)
        payload = json.dumps(names_sorted)
        headers = {
            'ETag': etag,
            'Cache-Control': 'public, max-age=300',
        }
        return Response(
            payload,
            media_type='application/json',
            headers=headers,
        )
    except Exception as e:
        raise internal_error(e, 'xml_names')


async def _release_xml(name: str) -> Response:
    """
    The user object XML of this backend's release, read from GitHub (an
    anonymous caller; never another ref). The file is kept per blob sha, which
    is content addressed.
    """
    ref = default_update_ref()
    repo_url = get_settings().need('GITHUB_REPO_URL')
    token = _github_token()
    api_base = _extract_api_url(repo_url)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        entries = await _list_repo_dir_cached(
            client, api_base, token, 'grasshopper_userobjects_xml', ref)
        wanted = f'{name}.xml'
        match = next((it for it in entries
                      if it.get('type') == 'file' and it.get('name') == wanted
                      and it.get('sha')), None)
        if match is None:
            raise HTTPException(status_code=404, detail='XML not found')
        content = _blob_xml_cache.get(match['sha'])
        if content is None:
            content = await _get_repo_entry_content(
                client, api_base, token, match, ref)
            _blob_xml_cache[match['sha']] = content
    return Response(
        content,
        media_type='text/xml; charset=utf-8',
        headers={'ETag': 'W/"' + hashlib.sha256(content).hexdigest()[:16] + '"',
                 'Cache-Control': 'public, max-age=300'},
    )


@router.get('/ghinterface/xml/{name}', response_class=Response)
@local_limiter.limit(GH_PUBLIC_RATE, key_func=signed_in_or_ip)
async def get_xml(
    request: Request,
    name: str,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
):
    """
    A user object as Grasshopper XML (copy and paste into a definition). A
    signed-in caller reads the server's XML directory; an anonymous caller
    gets the file of the release this backend runs from GitHub, nothing else.
    """
    try:
        if '/' in name or '\\' in name or '..' in name:
            raise HTTPException(status_code=400, detail='Invalid name')
        if not name.startswith('DDU_CSC_'):
            raise HTTPException(
                status_code=400,
                detail='Invalid component prefix',
            )

        if current_user is None:
            return await _release_xml(name)

        cache_dir = request.app.gh_xml_cache_dir
        path = os.path.join(cache_dir, f'{name}.xml')
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail='XML not found')

        with open(path, 'rb') as f:
            content = f.read()

        etag = 'W/"' + hashlib.sha256(content).hexdigest()[:16] + '"'
        headers = {
            'ETag': etag,
            'Cache-Control': 'public, max-age=300',
        }
        return Response(
            content,
            media_type='text/xml; charset=utf-8',
            headers=headers,
        )
    except HTTPException:
        raise
    except httpx.HTTPError as e:
        log.error('get_xml GitHub: %s', _failure_text(e))
        raise _http_exception_from_github(e)
    except Exception as e:
        raise internal_error(e, 'get_xml')
