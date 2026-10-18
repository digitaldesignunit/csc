#!/usr/bin/env python3.13
"""
The GitHub side of the Grasshopper interface routes: the release this backend
belongs to, the lookups of directories, blobs and files with their caches, and
the mapping of GitHub failures to answers. No route lives here.
"""

import base64
import re
import time
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, status
import httpx

from services.github_service import GitHubService
from csc_version import release_tag
from settings import get_settings
from logging_setup import get_logger


log = get_logger(__name__)


# GITHUB LOOKUP CACHES --------------------------------------------------------
# Directory listings are re-read constantly during a single CSC_Update run
# (once per source file and once per UserObject), so they are cached briefly.
REPO_DIR_CACHE_TTL_SECONDS = 120.0


# Blob shas are content addressed, so a version parsed from one never changes.
SRC_FETCH_CONCURRENCY = 8

_repo_dir_cache: Dict[str, Tuple[float, List[dict]]] = {}
_blob_version_cache: Dict[str, Optional[tuple]] = {}
# the parse of a source, by blob sha (content addressed, so it never changes)
_blob_reference_cache: Dict[str, dict] = {}
# the user object XML of the release, by blob sha
_blob_xml_cache: Dict[str, bytes] = {}

# the two reads an anonymous visitor may make (the page's download card and
# component reference): release information that is public on GitHub
GH_PUBLIC_RATE = '30/minute'

# UserObjects, sources and the interface ZIP are served from the GitHub release
# this backend belongs to (tag v<CSC_VERSION>), so a deploy updates backend, web
# and Grasshopper together and merging to main publishes nothing. Testers pick a
# branch with `?channel=`; GH_UPDATE_REF overrides the default (e.g. staging).
GH_INTERFACE_ASSET_PREFIX = 'csc-gh-interface-'


def default_update_ref() -> str:
    return get_settings().gh_update_ref or release_tag()


async def _release_of_this_backend(github_service: GitHubService) -> dict:
    """The GitHub release tagged v<CSC_VERSION>; 404 if it does not exist."""
    tag = release_tag()
    try:
        return await github_service.get_release_by_tag(tag)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f'No GitHub release {tag}: this backend runs a version '
                    'that has not been released (local or pre-release build).'
                ),
            )
        raise


# INTERNAL HELPERS ------------------------------------------------------------
def _failure_text(exc: BaseException) -> str:
    """What a GitHub failure may put in the log: the class of the error and,
    for an answer, its status. Never the URL (the ``ref`` in it is the
    channel the client typed, a download URL is pre-signed), the body or the
    traceback (decision 8.144 h)."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f'{type(exc).__name__} (status {exc.response.status_code})'
    return type(exc).__name__


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
    token = get_settings().github_csc_gh_token.get_secret_value().strip()
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
    Git ref (release tag or branch) to read Grasshopper sources/UserObjects
    from.

    Empty/None means this backend's own release (``default_update_ref``). A
    given name is passed to GitHub as `ref` and must match a remote branch or
    tag exactly.
    """
    if channel is None or channel == '':
        return default_update_ref()
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
                'Invalid update channel. It must match a GitHub branch or '
                'tag exactly.'
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
    except Exception:
        log.exception('_get_repo_file base64 decode')
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
            detail='GitHub request timed out',
        )
    if isinstance(e, httpx.ConnectError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Cannot connect to GitHub',
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail='GitHub service unavailable',
    )
