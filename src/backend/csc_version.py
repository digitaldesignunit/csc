"""
The CSC product version this backend belongs to.

One version for backend, web frontend and Grasshopper interface (released
together as tag ``v<version>``). Written by ``invoke bump-version``; checked
against VERSION, package.json and the release tag by scripts/ci/check_version.py.
"""

CSC_VERSION = '0.6.0.2'


def release_tag(version: str = CSC_VERSION) -> str:
    """Git tag of a release: ``v0.5.1.0``."""
    return f'v{version}'
