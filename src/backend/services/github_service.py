#!/usr/bin/env python3.13

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import re
from typing import Dict, Optional

# THIRD PARTY MODULE IMPORTS --------------------------------------------------
import httpx

# LOCAL MODULE IMPORTS --------------------------------------------------------


class GitHubService:
    """Service for interacting with GitHub API for release management."""

    def __init__(self, repo_url: str, token: Optional[str] = None):
        """
        Initialize GitHub service.

        Args:
            repo_url: GitHub repository URL (e.g.,
                "https://github.com/owner/repo")
            token: Optional GitHub personal access token. Public repos
                work without one; a token increases API rate limits.
        """
        self.token = token
        self.repo_url = repo_url
        self.api_base = self._extract_api_url(repo_url)
        self.headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'CSC-Backend/1.0'
        }
        if token:
            self.headers['Authorization'] = f'token {token}'

    def _extract_api_url(self, repo_url: str) -> str:
        """Extract API URL from repository URL."""
        # Convert https://github.com/owner/repo to
        # https://api.github.com/repos/owner/repo
        pattern = r'https://github\.com/([^/]+)/([^/]+)/?'
        match = re.match(pattern, repo_url)
        if not match:
            raise ValueError(f"Invalid GitHub repository URL: {repo_url}")

        owner, repo = match.groups()
        return f"https://api.github.com/repos/{owner}/{repo}"

    async def get_latest_release_info(self) -> Dict:
        """
        Get information about the latest release.

        Returns:
            Dictionary containing release information

        Raises:
            httpx.HTTPError: If GitHub API request fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/releases/latest",
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()

    async def get_release_by_tag(self, tag: str) -> Dict:
        """
        Get information about the release with exactly this tag.

        Raises:
            httpx.HTTPError: If the GitHub API request fails (404: no such
                release)
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/releases/tags/{tag}",
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    def select_asset(release_info: Dict, prefix: Optional[str] = None) -> Dict:
        """
        Pick the ZIP asset to hand out from a release.

        A product release carries several ZIPs (frontend bundle, GH
        interface), so an exact name *prefix* wins; without one the first ZIP
        whose name mentions the interface / Grasshopper is used.

        Raises:
            ValueError: If no suitable asset is found
        """
        zip_assets = [asset for asset in release_info.get('assets', [])
                      if asset['name'].lower().endswith('.zip')]
        if not zip_assets:
            raise ValueError(
                f"No ZIP assets in release {release_info.get('tag_name')}")
        if prefix:
            matches = [a for a in zip_assets if a['name'].startswith(prefix)]
            if not matches:
                raise ValueError(
                    f"No asset {prefix}*.zip in release "
                    f"{release_info.get('tag_name')}")
            return matches[0]
        preferred = [
            asset for asset in zip_assets
            if any(keyword in asset['name'].lower()
                   for keyword in ['interface', 'grasshopper', 'gh'])
        ]
        return preferred[0] if preferred else zip_assets[0]

    def get_release_asset_download_url(
        self,
        release_info: Dict,
        prefix: Optional[str] = None,
    ) -> str:
        """
        Download URL of the asset :meth:`select_asset` picks.

        Raises:
            ValueError: If no suitable asset is found
        """
        selected_asset = self.select_asset(release_info, prefix)
        # Authenticated downloads use the API asset URL; public repos can
        # use browser_download_url without a token.
        if self.token:
            download_url = (
                selected_asset.get('url')
                or selected_asset.get('browser_download_url')
            )
        else:
            download_url = (
                selected_asset.get('browser_download_url')
                or selected_asset.get('url')
            )
        if not download_url:
            raise ValueError(
                "No download URL found for the selected asset"
            )
        return download_url

    async def get_asset_filename(
        self,
        release_info: Dict,
        prefix: Optional[str] = None,
    ) -> str:
        """Filename of the asset :meth:`select_asset` picks."""
        return self.select_asset(release_info, prefix)['name']
