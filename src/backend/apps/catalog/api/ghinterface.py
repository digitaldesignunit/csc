#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import base64
import hashlib
import json
import os
import re
from typing import Annotated, List, Optional

# THIRD PARTY MODULE IMPORTS --------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse
import httpx

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.catalog.api.auth import get_current_user
from apps.catalog.models import User
from services.github_service import GitHubService

# INIT ROUTER -----------------------------------------------------------------
router = APIRouter()


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


def get_source_version(source):
    """Extract a comparable version tuple from Grasshopper component source."""
    src_lower = source.lower()
    version_str = [ln for ln in src_lower.split('\n') if "version" in ln]
    if version_str:
        version_match = re.search(
            r'(\d+(?:\.\d+)?[a-zA-Z]?)', version_str[0])
        if version_match:
            version_text = version_match.group(1)
            return _parse_version_string(version_text)
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
        token = os.environ['GITHUB_CSC_GH_TOKEN']
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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='GitHub service unavailable'
        )
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
        token = os.environ['GITHUB_CSC_GH_TOKEN']
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
            async with httpx.AsyncClient() as client:
                try:
                    headers = {
                        'Authorization': f'token {token}',
                        'Accept': 'application/octet-stream',
                        'User-Agent': 'CSC-Backend/1.0'
                    }

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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='GitHub service unavailable'
        )
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
    current_user: Annotated[User, Depends(get_current_user)]
):
    try:
        repo_url = os.environ['GITHUB_REPO_URL']
        token = os.environ['GITHUB_CSC_GH_TOKEN']
        api_base = _extract_api_url(repo_url)

        async with httpx.AsyncClient() as client:
            entries = await _list_repo_dir(
                client, api_base, token, 'grasshopper_userobjects_src'
            )
            result: List[List[object]] = []
            for item in entries:
                if item.get('type') == 'file':
                    name = item.get('name', '')
                    if '.' in name:
                        name_no_ext = name.rsplit('.', 1)[0]
                        path = item.get('path', '')
                        if path:
                            content_bytes = await _get_repo_file(
                                client, api_base, token, path
                            )
                            try:
                                text = content_bytes.decode('utf-8', 'replace')
                            except Exception:
                                text = ''
                            version_tuple = get_source_version(text)
                        else:
                            version_tuple = None
                        result.append([name_no_ext, version_tuple])
        return Response(
            json.dumps(result),
            media_type='application/json'
        )
    except httpx.HTTPError as e:
        print(f'[ERROR] list_src_names GitHub: {e}')
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='GitHub service unavailable',
        )
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
):
    try:
        repo_url = os.environ['GITHUB_REPO_URL']
        token = os.environ['GITHUB_CSC_GH_TOKEN']
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

        return Response(content, media_type='text/plain; charset=utf-8')
    except httpx.HTTPError as e:
        print(f'[ERROR] get_src_code GitHub: {e}')
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='GitHub service unavailable',
        )
    except HTTPException:
        raise
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
    current_user: Annotated[User, Depends(get_current_user)]
):
    try:
        repo_url = os.environ['GITHUB_REPO_URL']
        token = os.environ['GITHUB_CSC_GH_TOKEN']
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
        print(f'[ERROR] list_userobject_names GitHub: {e}')
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='GitHub service unavailable',
        )
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
):
    try:
        repo_url = os.environ['GITHUB_REPO_URL']
        token = os.environ['GITHUB_CSC_GH_TOKEN']
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
        print(f'[ERROR] get_userobject GitHub: {e}')
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='GitHub service unavailable',
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f'[ERROR] get_userobject: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )
