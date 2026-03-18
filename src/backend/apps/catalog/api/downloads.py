#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os
from typing import Annotated

# THIRD PARTY MODULE IMPORTS --------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
import httpx

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.catalog.api.auth import get_current_user
from apps.catalog.models import User
from services.github_service import GitHubService
# INIT ROUTER -----------------------------------------------------------------
router = APIRouter()


# ROUTES ----------------------------------------------------------------------

@router.get('/downloads/gh-interface/version')
async def get_gh_interface_version(
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Get the latest release version information for the Grasshopper interface.
    Requires authentication.
    """
    try:
        # Load GitHub configuration
        repo_url = os.environ['GITHUB_REPO_URL']
        token = os.environ['GITHUB_CSC_GH_TOKEN']

        # Initialize GitHub service
        github_service = GitHubService(repo_url, token)

        # Get latest release info
        release_info = await github_service.get_latest_release_info()

        # Debug: Show asset information
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

        # Extract relevant information
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


@router.get('/downloads/gh-interface')
async def download_gh_interface(
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Download the latest Grasshopper interface release as a ZIP file.
    Requires authentication.
    """
    try:
        # Load GitHub configuration
        repo_url = os.environ['GITHUB_REPO_URL']
        token = os.environ['GITHUB_CSC_GH_TOKEN']

        # Initialize GitHub service
        github_service = GitHubService(repo_url, token)

        # Get latest release info
        release_info = await github_service.get_latest_release_info()

        if not release_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No releases found in the repository"
            )

        # Get download URL and filename
        download_url = github_service.get_release_asset_download_url(
            release_info
        )
        filename = await github_service.get_asset_filename(release_info)

        # Debug logging
        # print(f"Release info: {release_info}")
        # print(f"Download URL: {download_url}")
        # print(f"Filename: {filename}")

        # Create a streaming response
        async def generate():
            async with httpx.AsyncClient() as client:
                try:
                    # Use the GitHub API URL with proper headers
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
                        # print(f"Response status: {response.status_code}")
                        # print(f"Response headers: {dict(response.headers)}")
                        # content_type = response.headers.get(
                        #     'content-type', 'N/A'
                        # )
                        # print(f"Content-Type: {content_type}")
                        # content_length = response.headers.get(
                        #     'content-length', 'N/A'
                        # )
                        # print(f"Content-Length: {content_length}")
                        response.raise_for_status()
                        # Stream the file content
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

        # Return streaming response with proper headers
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
