#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import base64
import os
import re
from typing import Annotated, List, Optional

# THIRD PARTY MODULE IMPORTS --------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response, StreamingResponse
import httpx

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.catalogue.api.auth import get_current_user
from apps.catalogue.models import User
from utility.utility import get_github_repo_url, get_github_repo_token

# INIT ROUTER -----------------------------------------------------------------
router = APIRouter()


# CONFIG LOADING --------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(_HERE))), 'config'
)
_CONFIGFILE = os.path.join(_CONFIG_DIR, 'dbconfig.json')


# INTERNAL HELPERS ------------------------------------------------------------
def _extract_api_url(repo_url: str) -> str:
    pattern = r'https://github\.com/([^/]+)/([^/]+)/?'
    match = re.match(pattern, repo_url)
    if not match:
        raise ValueError(f'Invalid GitHub repository URL: {repo_url}')
    owner, repo = match.groups()
    return f'https://api.github.com/repos/{owner}/{repo}'


async def _list_repo_dir(
    client: httpx.AsyncClient,
    api_base: str,
    token: str,
    path: str,
) -> List[dict]:
    resp = await client.get(
        f'{api_base}/contents/{path}',
        headers={
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'CSC-Backend/1.0',
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Unexpected response from GitHub contents API',
        )
    return data


async def _get_repo_file(
    client: httpx.AsyncClient,
    api_base: str,
    token: str,
    path: str,
) -> bytes:
    resp = await client.get(
        f'{api_base}/contents/{path}',
        headers={
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'CSC-Backend/1.0',
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    payload = resp.json()
    content_b64: Optional[str] = payload.get('content')
    if not content_b64:
        # Try download_url if content not embedded
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to decode file content: {e}',
        )


# ROUTES ----------------------------------------------------------------------

@router.get('/ghupdates/src_names', response_model=List[str])
async def list_src_names(
    current_user: Annotated[User, Depends(get_current_user)]
):
    try:
        repo_url = get_github_repo_url(_CONFIGFILE)
        token = get_github_repo_token(_CONFIGFILE)
        api_base = _extract_api_url(repo_url)

        async with httpx.AsyncClient() as client:
            entries = await _list_repo_dir(
                client, api_base, token, 'grasshopper_userobjects_src'
            )
        names: List[str] = []
        for item in entries:
            if item.get('type') == 'file':
                name = item.get('name', '')
                if '.' in name:
                    names.append(name.rsplit('.', 1)[0])
        return sorted(list(dict.fromkeys(names)))
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f'Failed to query GitHub: {e}',
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get('/ghupdates/src/{name}', response_class=Response)
async def get_src_code(
    name: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    try:
        repo_url = get_github_repo_url(_CONFIGFILE)
        token = get_github_repo_token(_CONFIGFILE)
        api_base = _extract_api_url(repo_url)

        async with httpx.AsyncClient() as client:
            entries = await _list_repo_dir(
                client, api_base, token, 'grasshopper_userobjects_src'
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
            path = matches[0]['path']
            content = await _get_repo_file(client, api_base, token, path)

        # Guess text encoding as UTF-8, return as text/plain
        return Response(content, media_type='text/plain; charset=utf-8')
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f'Failed to fetch source from GitHub: {e}',
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get('/ghupdates/userobject_names', response_model=List[str])
async def list_userobject_names(
    current_user: Annotated[User, Depends(get_current_user)]
):
    try:
        repo_url = get_github_repo_url(_CONFIGFILE)
        token = get_github_repo_token(_CONFIGFILE)
        api_base = _extract_api_url(repo_url)

        async with httpx.AsyncClient() as client:
            entries = await _list_repo_dir(
                client, api_base, token, 'grasshopper_userobjects'
            )
        names: List[str] = []
        for item in entries:
            if item.get('type') == 'file':
                name = item.get('name', '')
                if name.lower().endswith('.ghuser'):
                    names.append(name[:-7])
        return sorted(list(dict.fromkeys(names)))
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f'Failed to query GitHub: {e}',
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get('/ghupdates/userobject/{name}')
async def get_userobject(
    name: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    try:
        repo_url = get_github_repo_url(_CONFIGFILE)
        token = get_github_repo_token(_CONFIGFILE)
        api_base = _extract_api_url(repo_url)

        async with httpx.AsyncClient() as client:
            entries = await _list_repo_dir(
                client, api_base, token, 'grasshopper_userobjects'
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
            path = matches[0]['path']
            content = await _get_repo_file(client, api_base, token, path)

        headers = {
            'Content-Disposition': f'attachment; filename="{name}.ghuser"'
        }
        return StreamingResponse(
            iter([content]),
            media_type='application/octet-stream',
            headers=headers,
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f'Failed to fetch file from GitHub: {e}',
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
