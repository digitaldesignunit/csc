#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import re
from typing import Dict

# THIRD PARTY MODULE IMPORTS --------------------------------------------------
import httpx

# LOCAL MODULE IMPORTS --------------------------------------------------------


class GitHubService:
    """Service for interacting with GitHub API for release management."""

    def __init__(self, repo_url: str, token: str):
        """
        Initialize GitHub service.

        Args:
            repo_url: GitHub repository URL (e.g.,
                "https://github.com/owner/repo")
            token: GitHub personal access token
        """
        self.token = token
        self.repo_url = repo_url
        self.api_base = self._extract_api_url(repo_url)
        self.headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'CSC-Backend/1.0'
        }

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

    def get_release_asset_download_url(self, release_info: Dict) -> str:
        """
        Get the download URL for the release asset.

        Args:
            release_info: Release information from get_latest_release_info()

        Returns:
            Download URL for the asset

        Raises:
            ValueError: If no suitable asset is found
        """
        assets = release_info.get('assets', [])
        print(f"Available assets: {[asset['name'] for asset in assets]}")

        if not assets:
            raise ValueError("No assets found in the latest release")

        # Look for ZIP files, prefer those with 'interface' or 'grasshopper'
        zip_assets = [asset for asset in assets
                      if asset['name'].lower().endswith('.zip')]

        if not zip_assets:
            raise ValueError("No ZIP assets found in the latest release")

        # Prefer assets with 'interface' or 'grasshopper' in the name
        preferred_assets = [
            asset for asset in zip_assets
            if any(keyword in asset['name'].lower()
                   for keyword in ['interface', 'grasshopper', 'gh'])
        ]

        # Use preferred asset if found, otherwise use first ZIP asset
        selected_asset = (preferred_assets[0] if preferred_assets
                          else zip_assets[0])

        print(f"Selected asset: {selected_asset['name']}")
        asset_url = selected_asset.get('browser_download_url', 'NOT FOUND')
        print(f"Asset URL: {asset_url}")

        # Use the GitHub API URL for downloading (requires authentication)
        # The browser_download_url is for public access, but we need API access
        download_url = selected_asset.get('url')
        if not download_url:
            # Fallback to browser_download_url if API URL not available
            download_url = selected_asset.get('browser_download_url')
            if not download_url:
                raise ValueError(
                    "No download URL found for the selected asset"
                )

        return download_url

    async def get_asset_filename(self, release_info: Dict) -> str:
        """
        Get the filename of the release asset.

        Args:
            release_info: Release information from get_latest_release_info()

        Returns:
            Filename of the asset
        """
        assets = release_info.get('assets', [])
        if not assets:
            raise ValueError("No assets found in the latest release")

        # Use same logic as get_release_asset_download_url
        zip_assets = [asset for asset in assets
                      if asset['name'].lower().endswith('.zip')]
        preferred_assets = [
            asset for asset in zip_assets
            if any(keyword in asset['name'].lower()
                   for keyword in ['interface', 'grasshopper', 'gh'])
        ]

        selected_asset = (preferred_assets[0] if preferred_assets
                          else zip_assets[0])
        return selected_asset['name']
