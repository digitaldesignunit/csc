#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import asyncio
import base64
import hashlib
import json
import os
import re
import time
from typing import Annotated, Dict, List, Optional, Tuple

# THIRD PARTY MODULE IMPORTS --------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse
import httpx

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.catalog.api.auth import get_current_user
from apps.catalog.models import User
from services.github_service import GitHubService

# INIT ROUTER -----------------------------------------------------------------
router = APIRouter()

# GITHUB LOOKUP CACHES --------------------------------------------------------
# Directory listings are re-read constantly during a single CSC_Update run
# (once per source file and once per UserObject), so they are cached briefly.
REPO_DIR_CACHE_TTL_SECONDS = 120.0


# Blob shas are content addressed, so a version parsed from one never changes.
SRC_FETCH_CONCURRENCY = 8

_repo_dir_cache: Dict[str, Tuple[float, List[dict]]] = {}
_blob_version_cache: Dict[str, Optional[tuple]] = {}

# GitHub branch CSC_Update reads from (query param `channel`).
DEFAULT_UPDATE_CHANNEL = 'main'


# INTERNAL HELPERS ------------------------------------------------------------
def _extract_api_url(repo_url: str) -> str:
    pattern = r'https://github\.com/([^/]+)/([^/]+)/?'
    match = re.match(pattern, repo_url)
    if not match:
        raise ValueError(f'Invalid GitHub repository URL: {repo_url}')
    owner, repo = match.groups()
    return f'https://api.github.com/repos/{owner}/{repo}'


def _github_token() -> Optional[str]:
    """
    Optional PAT. Public repos work without it; a token increases rate limits.
    """
    token = (os.getenv('GITHUB_CSC_GH_TOKEN') or '').strip()
    return token or None


def _github_headers(
    token: Optional[str],
    accept: str = 'application/vnd.github.v3+json',
) -> dict:
    headers = {
        'Accept': accept,
        'User-Agent': 'CSC-Backend/1.0',
    }
    if token:
        headers['Authorization'] = f'token {token}'
    return headers


def resolve_update_channel(channel: Optional[str]) -> str:
    """
    GitHub branch to read Grasshopper sources/UserObjects from.

    Empty/None defaults to main. The name is passed to GitHub as `ref` and
    must match a remote branch exactly.
    """
    if channel is None or channel == '':
        return DEFAULT_UPDATE_CHANNEL
    if (
        len(channel) > 250
        or any(c.isspace() or ord(c) < 32 for c in channel)
        or '..' in channel
        or '\\' in channel
        or '?' in channel
        or '#' in channel
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                'Invalid update channel. Branch name must match a GitHub '
                'branch exactly.'
            ),
        )
    return channel


def _github_path_not_found(channel: str, what: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            f'{what} not found for update channel "{channel}". '
            'The GitHub branch name must match exactly.'
        ),
    )


async def _list_repo_dir(
    client: httpx.AsyncClient,
    api_base: str,
    token: Optional[str],
    path: str,
    ref: str,
) -> List[dict]:
    resp = await client.get(
        f'{api_base}/contents/{path}',
        headers=_github_headers(token),
        params={'ref': ref},
        timeout=30.0,
    )
    if resp.status_code == 404:
        raise _github_path_not_found(ref, f'Repository path "{path}"')
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Unexpected response from GitHub contents API',
        )
    return data


async def _list_repo_dir_cached(
    client: httpx.AsyncClient,
    api_base: str,
    token: Optional[str],
    path: str,
    ref: str,
) -> List[dict]:
    now = time.monotonic()
    cache_key = f'{ref}:{path}'
    cached = _repo_dir_cache.get(cache_key)
    if cached and (now - cached[0]) < REPO_DIR_CACHE_TTL_SECONDS:
        return cached[1]
    entries = await _list_repo_dir(client, api_base, token, path, ref)
    _repo_dir_cache[cache_key] = (now, entries)
    return entries


async def _get_repo_blob(
    client: httpx.AsyncClient,
    api_base: str,
    token: Optional[str],
    sha: str,
) -> bytes:
    resp = await client.get(
        f'{api_base}/git/blobs/{sha}',
        headers=_github_headers(
            token, accept='application/vnd.github.v3.raw'
        ),
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.content


async def _get_repo_file(
    client: httpx.AsyncClient,
    api_base: str,
    token: Optional[str],
    path: str,
    ref: str,
) -> bytes:
    resp = await client.get(
        f'{api_base}/contents/{path}',
        headers=_github_headers(token),
        params={'ref': ref},
        timeout=30.0,
    )
    if resp.status_code == 404:
        raise _github_path_not_found(ref, f'File "{path}"')
    resp.raise_for_status()
    payload = resp.json()
    content_b64: Optional[str] = payload.get('content')
    if not content_b64:
        download_url = payload.get('download_url')
        if not download_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='File content not found in GitHub response',
            )
        resp2 = await client.get(
            download_url,
            headers={'User-Agent': 'CSC-Backend/1.0'},
            timeout=30.0,
        )
        resp2.raise_for_status()
        return resp2.content
    try:
        return base64.b64decode(content_b64)
    except Exception as e:
        print(f'[ERROR] _get_repo_file base64 decode: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to decode file content',
        )


async def _download_raw(
    client: httpx.AsyncClient,
    download_url: str,
) -> bytes:
    resp = await client.get(
        download_url,
        headers={'User-Agent': 'CSC-Backend/1.0'},
        timeout=30.0,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.content


async def _get_repo_entry_content(
    client: httpx.AsyncClient,
    api_base: str,
    token: Optional[str],
    entry: dict,
    ref: str,
) -> bytes:
    """Read one file from a contents listing entry.

    With a token, prefer /git/blobs on api.github.com (5000 req/hour).
    Without a token, prefer download_url (raw.githubusercontent.com) so
    CSC_Update does not burn the unauthenticated 60 req/hour REST quota.
    Fall back to the other method if the first fails.
    """
    download_url = entry.get('download_url')
    sha = entry.get('sha')

    async def via_raw() -> bytes:
        return await _download_raw(client, download_url)

    async def via_blob() -> bytes:
        if not sha:
            return await _get_repo_file(
                client, api_base, token, entry['path'], ref
            )
        return await _get_repo_blob(client, api_base, token, sha)

    if token:
        try:
            return await via_blob()
        except httpx.HTTPError:
            if download_url:
                return await via_raw()
            raise
    if download_url:
        try:
            return await via_raw()
        except httpx.HTTPError:
            return await via_blob()
    return await via_blob()


def _http_exception_from_github(e: httpx.HTTPError) -> HTTPException:
    """Map GitHub HTTP failures to a CSC_Update-visible error."""
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        remaining = e.response.headers.get('X-RateLimit-Remaining')
        url = str(e.request.url) if e.request is not None else ''
        if code == 401:
            return HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    'GitHub rejected the request. Remove an invalid '
                    'GITHUB_CSC_GH_TOKEN, or omit it for the public repo.'
                ),
            )
        if code == 403 or remaining == '0':
            return HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    'GitHub API rate limit exceeded. Wait for the hourly '
                    'reset, or set GITHUB_CSC_GH_TOKEN for a higher limit.'
                ),
            )
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f'GitHub HTTP {code} for {url}',
        )
    if isinstance(e, httpx.TimeoutException):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f'GitHub request timed out: {e}',
        )
    if isinstance(e, httpx.ConnectError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f'Cannot connect to GitHub: {e}',
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f'GitHub service unavailable ({type(e).__name__}): {e}',
    )


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
async def get_gh_interface_version(
    current_user: Annotated[User, Depends(get_current_user)]
):
    """Get the latest release version for the Grasshopper interface."""
    try:
        repo_url = os.environ['GITHUB_REPO_URL']
        token = _github_token()
        github_service = GitHubService(repo_url, token)
        release_info = await github_service.get_latest_release_info()

        assets = release_info.get('assets', [])
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

    except httpx.HTTPError as e:
        print(f'[ERROR] get_gh_interface_version GitHub: {e}')
        raise _http_exception_from_github(e)
    except Exception as e:
        print(f'[ERROR] get_gh_interface_version: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )


@router.get('/ghinterface/download')
async def download_gh_interface(
    current_user: Annotated[User, Depends(get_current_user)]
):
    """Download the latest Grasshopper interface release as a ZIP file."""
    try:
        repo_url = os.environ['GITHUB_REPO_URL']
        token = _github_token()
        github_service = GitHubService(repo_url, token)
        release_info = await github_service.get_latest_release_info()

        if not release_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No releases found in the repository"
            )

        download_url = github_service.get_release_asset_download_url(
            release_info
        )
        filename = await github_service.get_asset_filename(release_info)

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
                    print(f"HTTP error: {e}")
                    try:
                        response_text = await e.response.aread()
                        print(f"Response text: {response_text}")
                    except Exception as read_error:
                        print(f"Could not read response: {read_error}")
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

    except httpx.HTTPError as e:
        print(f'[ERROR] download_gh_interface GitHub: {e}')
        raise _http_exception_from_github(e)
    except ValueError as e:
        print(f'[ERROR] download_gh_interface asset lookup: {e}')
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Release asset not found'
        )
    except Exception as e:
        print(f'[ERROR] download_gh_interface: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )


@router.get('/ghinterface/src_names', response_model=List[str])
async def list_src_names(
    current_user: Annotated[User, Depends(get_current_user)],
    channel: str = Query(default='main'),
):
    try:
        ref = resolve_update_channel(channel)
        repo_url = os.environ['GITHUB_REPO_URL']
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
                    print(
                        f'[ERROR] cache_version {item.get("name")}: {result}'
                    )

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
        print(f'[ERROR] list_src_names GitHub: {e}')
        raise _http_exception_from_github(e)
    except Exception as e:
        print(f'[ERROR] list_src_names: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )


@router.get('/ghinterface/src/{name}', response_class=Response)
async def get_src_code(
    name: str,
    current_user: Annotated[User, Depends(get_current_user)],
    channel: str = Query(default='main'),
):
    try:
        ref = resolve_update_channel(channel)
        repo_url = os.environ['GITHUB_REPO_URL']
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
        print(f'[ERROR] get_src_code GitHub: {e}')
        raise _http_exception_from_github(e)
    except Exception as e:
        print(f'[ERROR] get_src_code: {e}')
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get('/ghinterface/xml/{name}', response_class=Response)
async def get_xml(
    request: Request,
    name: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    try:
        if '/' in name or '\\' in name or '..' in name:
            raise HTTPException(status_code=400, detail='Invalid name')
        if not name.startswith('DDU_CSC_'):
            raise HTTPException(
                status_code=400,
                detail='Invalid component prefix',
            )

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
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get('/ghinterface/userobject_names', response_model=List[str])
async def list_userobject_names(
    current_user: Annotated[User, Depends(get_current_user)],
    channel: str = Query(default='main'),
):
    try:
        ref = resolve_update_channel(channel)
        repo_url = os.environ['GITHUB_REPO_URL']
        token = _github_token()
        api_base = _extract_api_url(repo_url)

        async with httpx.AsyncClient(follow_redirects=True) as client:
            entries = await _list_repo_dir_cached(
                client, api_base, token, 'grasshopper_userobjects', ref
            )
        names: List[str] = []
        for item in entries:
            if item.get('type') == 'file':
                name = item.get('name', '')
                if name.lower().endswith('.ghuser'):
                    names.append(name[:-7])
        return sorted(list(dict.fromkeys(names)))
    except HTTPException:
        raise
    except httpx.HTTPError as e:
        print(f'[ERROR] list_userobject_names GitHub: {e}')
        raise _http_exception_from_github(e)
    except Exception as e:
        print(f'[ERROR] list_userobject_names: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )


@router.get('/ghinterface/userobject/{name}')
async def get_userobject(
    name: str,
    current_user: Annotated[User, Depends(get_current_user)],
    channel: str = Query(default='main'),
):
    try:
        ref = resolve_update_channel(channel)
        repo_url = os.environ['GITHUB_REPO_URL']
        token = _github_token()
        api_base = _extract_api_url(repo_url)

        async with httpx.AsyncClient(follow_redirects=True) as client:
            entries = await _list_repo_dir_cached(
                client, api_base, token, 'grasshopper_userobjects', ref
            )
            target_name = f'{name}.ghuser'
            matches = [
                it for it in entries
                if it.get('type') == 'file' and it.get('name') == target_name
            ]
            if not matches:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail='UserObject (.ghuser) not found',
                )
            content = await _get_repo_entry_content(
                client, api_base, token, matches[0], ref
            )

        headers = {
            'Content-Disposition': f'attachment; filename="{name}.ghuser"'
        }
        return StreamingResponse(
            iter([content]),
            media_type='application/octet-stream',
            headers=headers,
        )
    except HTTPException:
        raise
    except httpx.HTTPError as e:
        print(f'[ERROR] get_userobject GitHub: {e}')
        raise _http_exception_from_github(e)
    except Exception as e:
        print(f'[ERROR] get_userobject: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )
