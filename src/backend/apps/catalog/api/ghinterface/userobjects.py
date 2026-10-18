#!/usr/bin/env python3.13
"""
User objects of the Grasshopper interface.

* `GET /ghinterface/userobject_names`, `/ghinterface/userobject/{name}`
* `GET /ghinterface/userobject_manifest` (decision 8.155): name, size and
  sha256 of every ``.ghuser`` of the channel, like the library manifest. The
  other two stay as they are: a CSC_Update that predates the manifest needs
  them to fetch the new CSC_Update.
"""

import asyncio
import hashlib
import re
from typing import Annotated, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
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

GH_USEROBJECTS_DIR = 'grasshopper_userobjects'
RELEASE_TAG_RE = re.compile(r'^v(\d+(\.\d+)+(-[0-9A-Za-z.]+)?)$')

# (size, sha256) of a file by its git blob sha: the content of a blob never
# changes, so a manifest request reads only the files it has not seen
_digest_cache: Dict[str, tuple] = {}


def channel_version(ref: str) -> str:
    """The version a channel stands for: the release version of a ``v<x>``
    tag, else the name of the branch or tag."""
    match = RELEASE_TAG_RE.match(ref)
    return match.group(1) if match else ref


def digest_of(data: bytes) -> tuple:
    """``(size, sha256)`` of one file."""
    return len(data), hashlib.sha256(data).hexdigest()


def userobject_manifest(ref: str, digests: Dict[str, tuple]) -> dict:
    """The manifest of the user objects from ``{name: (size, sha256)}`` (name
    without ``.ghuser``): per file its size and sha256, sorted by name, and the
    version of the channel."""
    return {
        'ref': ref,
        'version': channel_version(ref),
        'files': [{'name': name, 'size': size, 'sha256': digest}
                  for name, (size, digest) in sorted(digests.items())],
    }


@router.get('/ghinterface/userobject_names', response_model=List[str])
async def list_userobject_names(
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
        log.error('list_userobject_names GitHub: %s', _failure_text(e))
        raise _http_exception_from_github(e)
    except Exception:
        log.exception('list_userobject_names')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )


@router.get('/ghinterface/userobject/{name}')
async def get_userobject(
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
        log.error('get_userobject GitHub: %s', _failure_text(e))
        raise _http_exception_from_github(e)
    except Exception:
        log.exception('get_userobject')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )


@router.get('/ghinterface/userobject_manifest')
async def get_userobject_manifest(
    current_user: Annotated[User, Depends(get_current_user)],
    channel: str = Query(default=''),
):
    """Name, size and sha256 of every ``.ghuser`` of the channel, and the
    version of the channel (decision 8.155)."""
    try:
        ref = resolve_update_channel(channel)
        repo_url = get_settings().need('GITHUB_REPO_URL')
        token = _github_token()
        api_base = _extract_api_url(repo_url)

        async with httpx.AsyncClient(follow_redirects=True) as client:
            listing = await _list_repo_dir_cached(
                client, api_base, token, GH_USEROBJECTS_DIR, ref)
            entries = [it for it in listing if it.get('type') == 'file'
                       and it.get('name', '').lower().endswith('.ghuser')]
            if not entries:
                raise _github_path_not_found(ref, GH_USEROBJECTS_DIR)
            semaphore = asyncio.Semaphore(SRC_FETCH_CONCURRENCY)

            async def digest(entry) -> tuple:
                blob = entry.get('sha')
                known: Optional[tuple] = _digest_cache.get(blob) if blob else None
                if known is None:
                    async with semaphore:
                        data = await _get_repo_entry_content(
                            client, api_base, token, entry, ref)
                    known = digest_of(data)
                    if blob:
                        _digest_cache[blob] = known
                return entry['name'][:-len('.ghuser')], known

            digests = dict(await asyncio.gather(*(digest(e) for e in entries)))
        return userobject_manifest(ref, digests)
    except HTTPException:
        raise
    except httpx.HTTPError as e:
        log.error('get_userobject_manifest GitHub: %s', _failure_text(e))
        raise _http_exception_from_github(e)
    except Exception:
        log.exception('get_userobject_manifest')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )
