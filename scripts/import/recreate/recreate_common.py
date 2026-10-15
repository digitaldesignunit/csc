"""Paths, local-host rule and sign-in shared by the ReCreate import scripts.

The scripts run with ``python -I`` (the data is untrusted), which leaves the script's own folder off
``sys.path``; each script therefore inserts this folder itself before importing this module.

Defaults are the places of the local rehearsal (everything under the git-ignored ``.dev/``); every one is
an argument of the scripts. Computed output never goes into the repository tree outside ``.dev/``
(:func:`out_dir`), and the database tools refuse a host that is not this machine (:func:`require_local`).
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path
from typing import Callable, Optional, Tuple
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DOT_DEV = REPO / '.dev'

# the places of the local rehearsal (arguments of every script)
DEFAULT_DATA = DOT_DEV / 'open_datasets' / 'recreate' / 'zenodo-16809738'
DEFAULT_OUT = DOT_DEV / 'import_open' / 'recreate' / 'out'
DEFAULT_ASSETS = DOT_DEV / 'assets-261012'
DEFAULT_MONGO_URI = 'mongodb://127.0.0.1:27791'
DEFAULT_SERVER = 'http://127.0.0.1:8791'

CLIENT = 'catalog-import/0.1'
TOKEN_ENV = 'CSC_IMPORT_TOKEN'
LOCAL_HOSTS = ('127.0.0.1', 'localhost', '::1')


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.relative_to(folder)
        return True
    except ValueError:
        return False


def out_dir(value, *, create: bool = True) -> Path:
    """The folder computed files go to. Outside the repository, or inside ``.dev/`` (which git ignores);
    any other place in the repository is refused, so a generated file can never be committed by accident."""
    path = Path(value).resolve()
    if _inside(path, REPO) and not _inside(path, DOT_DEV):
        sys.exit(f'refusing to write inside the repository (only .dev/ is allowed there): {path}')
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def require_dot_dev(value, what: str = 'path') -> Path:
    """The folder, when it is inside the repository's ``.dev/`` (git ignores it). The rehearsal tools read
    and WRITE their files (previews, proxies), so they only work on a copy kept there, never on the original
    asset folders or anything else; anywhere else is refused."""
    path = Path(value).resolve()
    if not _inside(path, DOT_DEV):
        sys.exit(f'refusing: {what} {path} is not inside {DOT_DEV}. The rehearsal writes into it: use a copy '
                 f'of the assets kept under .dev/ and never the original (see "Local rehearsal" in the '
                 f'README: no --sweep, no backup folder)')
    return path


def require_local(uri: str) -> str:
    """The URI, when its host is this machine; anything else exits. A rehearsal tool never touches a
    shared or production database."""
    parts = urlparse(uri)
    # a replica-set URI names several hosts in one netloc (a, b), and a +srv URI looks hosts up in DNS:
    # neither is "this machine", whatever the first host says
    hosts = parts.netloc.rsplit('@', 1)[-1]
    if parts.scheme != 'mongodb' or ',' in hosts:
        sys.exit('refusing: this tool only runs against a database on this machine: one host, '
                 'a plain mongodb:// URI (not mongodb+srv://, not a list of hosts)')
    host = parts.hostname or ''
    if host not in LOCAL_HOSTS:
        sys.exit(f'refusing: this tool only runs against a database on this machine, not {host or uri!r}')
    return uri


def login(server: str, username: str, password: str, post: Optional[Callable] = None) -> str:
    """A bearer token from ``POST /auth/token``. The password is used once and not kept by this function."""
    if post is None:
        import requests
        post = requests.post
    response = post(server.rstrip('/') + '/auth/token',
                    data={'username': username, 'password': password},
                    headers={'X-CSC-Client': CLIENT}, timeout=60)
    if response.status_code != 200:
        sys.exit(f'sign-in failed ({response.status_code})')
    return response.json()['access_token']


def get_token(server: str, username: Optional[str], *, environ=None,
              ask: Callable[[str], str] = getpass.getpass, post: Optional[Callable] = None
              ) -> Tuple[str, Optional[Callable[[], str]]]:
    """``(token, renew)`` for the import account. The token is ``CSC_IMPORT_TOKEN`` when that is set (no
    renewal: ``renew`` is None), else the password of ``--username``, asked on the terminal (no echo) and
    exchanged at ``/auth/token``; ``renew()`` signs in again with that password, kept in memory only, for a
    run that outlives the token. Neither is ever printed."""
    environ = os.environ if environ is None else environ
    token = (environ.get(TOKEN_ENV) or '').strip()
    if token:
        return token, None
    if not username:
        sys.exit(f'no way to sign in: set {TOKEN_ENV} or pass --username (the password is asked)')
    password = ask(f'Password of {username} on {server}: ')

    def renew() -> str:
        return login(server, username, password, post)

    return renew(), renew
