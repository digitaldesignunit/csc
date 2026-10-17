#!/usr/bin/env python3.13
"""
The `csc_gh` library of the Grasshopper client: manifest and files.

* `GET /ghinterface/library_manifest`, `/ghinterface/library/{name}`
"""

import asyncio
import hashlib
import re
from typing import Annotated, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
import httpx

from apps.catalog.api.auth import get_current_user
from apps.catalog.models import User
from settings import get_settings
from logging_setup import get_logger
from .github import (
    SRC_FETCH_CONCURRENCY,
    _extract_api_url,
    _failure_text,
    _get_repo_entry_content,
    _github_path_not_found,
    _github_token,
    _http_exception_from_github,
    _list_repo_dir_cached,
    resolve_update_channel,
)


log = get_logger(__name__)

router = APIRouter()


# THE SHARED LIBRARY (decision 8.111) ----------------------------------------
# The package ``csc_gh`` (grasshopper_lib/csc_gh) is installed by CSC_Update next
# to the UserObjects: a manifest of the files of the release with the sha256 of
# each, and the files one by one. The client checks every file against the
# manifest before it replaces the installed package.
GH_LIBRARY_DIR = 'grasshopper_lib/csc_gh'
LIBRARY_FILE_RE = re.compile(r'^[a-z][a-z_]*\.py$')
LIBRARY_VERSION_RE = re.compile(
    r"^__version__\s*=\s*'(\d+[a-zA-Z]?)'\s*$", re.M)


def is_library_file(name: str) -> bool:
    """A ``.py`` file of the package folder (no path, no hidden file)."""
    return name == '__init__.py' or bool(LIBRARY_FILE_RE.match(name))


def library_manifest(ref: str, files: Dict[str, bytes]) -> dict:
    """The manifest of the library files (``{name: bytes}``): the version of
    ``__init__.py``, and per file its size and sha256."""
    init = files.get('__init__.py')
    match = LIBRARY_VERSION_RE.search(init.decode('utf-8')) if init else None
    return {
        'ref': ref,
        'version': match.group(1) if match else None,
        'files': [
            {'path': name, 'size': len(data),
             'sha256': hashlib.sha256(data).hexdigest()}
            for name, data in sorted(files.items())
        ],
    }


async def _library_entries(
    client: httpx.AsyncClient, api_base: str, token: Optional[str], ref: str
) -> List[dict]:
    entries = await _list_repo_dir_cached(
        client, api_base, token, GH_LIBRARY_DIR, ref)
    return [it for it in entries if it.get('type') == 'file'
            and is_library_file(it.get('name', ''))]


@router.get('/ghinterface/library_manifest')
async def get_library_manifest(
    current_user: Annotated[User, Depends(get_current_user)],
    channel: str = Query(default=''),
):
    """Version and checksums of the ``csc_gh`` package of the release."""
    try:
        ref = resolve_update_channel(channel)
        repo_url = get_settings().need('GITHUB_REPO_URL')
        token = _github_token()
        api_base = _extract_api_url(repo_url)
        async with httpx.AsyncClient(follow_redirects=True) as client:
            entries = await _library_entries(client, api_base, token, ref)
            if not entries:
                raise _github_path_not_found(ref, GH_LIBRARY_DIR)
            semaphore = asyncio.Semaphore(SRC_FETCH_CONCURRENCY)

            async def fetch(entry):
                async with semaphore:
                    return entry['name'], await _get_repo_entry_content(
                        client, api_base, token, entry, ref)

            files = dict(await asyncio.gather(*(fetch(e) for e in entries)))
        manifest = library_manifest(ref, files)
        if manifest['version'] is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='The library of this release has no __version__.')
        return manifest
    except HTTPException:
        raise
    except httpx.HTTPError as e:
        log.error('get_library_manifest GitHub: %s', _failure_text(e))
        raise _http_exception_from_github(e)
    except Exception:
        log.exception('get_library_manifest')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )


@router.get('/ghinterface/library/{name}', response_class=Response)
async def get_library_file(
    name: str,
    current_user: Annotated[User, Depends(get_current_user)],
    channel: str = Query(default=''),
):
    """One file of the ``csc_gh`` package (a ``.py`` of the package folder)."""
    if not is_library_file(name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Library file not found')
    try:
        ref = resolve_update_channel(channel)
        repo_url = get_settings().need('GITHUB_REPO_URL')
        token = _github_token()
        api_base = _extract_api_url(repo_url)
        async with httpx.AsyncClient(follow_redirects=True) as client:
            entries = await _library_entries(client, api_base, token, ref)
            matches = [it for it in entries if it.get('name') == name]
            if not matches:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail='Library file not found')
            content = await _get_repo_entry_content(
                client, api_base, token, matches[0], ref)
        return Response(content, media_type='application/octet-stream')
    except HTTPException:
        raise
    except httpx.HTTPError as e:
        log.error('get_library_file GitHub: %s', _failure_text(e))
        raise _http_exception_from_github(e)
    except Exception:
        log.exception('get_library_file')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )
