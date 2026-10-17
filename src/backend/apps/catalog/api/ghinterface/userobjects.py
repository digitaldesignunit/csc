#!/usr/bin/env python3.13
"""
User objects of the Grasshopper interface.

* `GET /ghinterface/userobject_names`, `/ghinterface/userobject/{name}`
"""

from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
import httpx

from apps.catalog.api.auth import get_current_user
from apps.catalog.models import User
from settings import get_settings
from logging_setup import get_logger
from .github import (
    _extract_api_url,
    _failure_text,
    _get_repo_entry_content,
    _github_token,
    _http_exception_from_github,
    _list_repo_dir_cached,
    resolve_update_channel,
)


log = get_logger(__name__)

router = APIRouter()


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
