"""Picking the Grasshopper interface ZIP out of a product release."""

import pytest

from services.github_service import GitHubService

RELEASE = {'tag_name': 'v0.5.1.0', 'assets': [
    {'name': 'csc-frontend-0.5.1.0.zip', 'browser_download_url': 'https://x/frontend'},
    {'name': 'csc-backend-0.5.1.0.tar.gz', 'browser_download_url': 'https://x/backend'},
    {'name': 'csc-gh-interface-0.5.1.0.zip', 'browser_download_url': 'https://x/gh'},
]}


def test_prefix_selects_the_gh_interface_zip():
    service = GitHubService('https://github.com/o/r')
    assert service.get_release_asset_download_url(
        RELEASE, 'csc-gh-interface-') == 'https://x/gh'


def test_prefix_without_match_fails_instead_of_guessing():
    with pytest.raises(ValueError):
        GitHubService.select_asset(RELEASE, 'csc-nothing-')


def test_old_single_zip_releases_still_resolve_without_prefix():
    old = {'tag_name': 'gh-interface-0.5.0.0-beta-9', 'assets': [
        {'name': 'ddu-csc-grasshopper-interface-0.5.0.0-beta-9.zip'}]}
    assert GitHubService.select_asset(old)['name'].startswith('ddu-csc-')
