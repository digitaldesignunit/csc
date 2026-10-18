"""Paths, local-host rule and sign-in shared by the ReCreate import scripts.

The scripts run with ``python -I`` (the data is untrusted), which leaves the script's own folder off
``sys.path``; each script therefore inserts this folder itself before importing this module.

Defaults are the places of the local rehearsal (everything under the git-ignored ``.dev/``); every one is
an argument of the scripts. Computed output never goes into the repository tree outside ``.dev/``
(:func:`out_dir`), and the database tools refuse a host that is not this machine (:func:`require_local`).
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlsplit
from urllib.request import urlopen

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


# FETCHING A ZENODO RECORD (shared by the fetch steps of the import tools) -----------------------
API = 'https://zenodo.org/api/records/{record}'
CHUNK = 1 << 20
TIMEOUT = 120

Opener = Callable[[str], object]       # url -> a binary file-like object (context manager)


def default_open(url: str):
    return urlopen(url, timeout=TIMEOUT)             # noqa: S310 -- https, the Zenodo API


def expected_md5(checksum: str) -> str:
    """``md5:<hex>`` of the record, as a bare lower-case hex string. Whitespace and carriage returns are
    stripped: a list read on Windows carries them (the first version of this check failed on them)."""
    kind, _, digest = str(checksum).strip().partition(':')
    if kind.strip().lower() != 'md5' or not digest.strip():
        raise ValueError(f'not an md5 checksum: {checksum!r}')
    return digest.strip().lower()


def md5_of(path: Path) -> str:
    digest = hashlib.md5()                           # noqa: S324 -- the record's own sum, not security
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(CHUNK), b''):
            digest.update(block)
    return digest.hexdigest()


ALLOWED_HOST = 'zenodo.org'


def url_problem(url: str) -> str:
    """Why a file URL of the record is not fetched, or '' when it may be: only https, and only from
    zenodo.org (or a sub-domain of it). A record is data from the network; it must not be able to send
    this tool to a local file, a plain-http server or another site."""
    parts = urlsplit(str(url))
    host = (parts.hostname or '').lower()
    if parts.scheme != 'https':
        return f'the URL is not https ({parts.scheme or "no scheme"})'
    if host != ALLOWED_HOST and not host.endswith('.' + ALLOWED_HOST):
        return f'the host is not {ALLOWED_HOST} ({host or "none"})'
    return ''


def safe_name(key: str) -> str:
    """A file name of the record that cannot leave the destination folder."""
    if not key or key in ('.', '..') or '/' in key or '\\' in key or '\x00' in key:
        raise ValueError(f'unsafe file name in the record: {key!r}')
    return key


def load_record(record: str, record_file: Path = None, opener: Opener = default_open) -> Dict:
    """The record metadata: from a local JSON file (offline, tests) or from the Zenodo API."""
    if record_file is not None:
        return json.loads(Path(record_file).read_text(encoding='utf-8'))
    with opener(API.format(record=record)) as response:
        return json.loads(response.read().decode('utf-8'))


def download(url: str, target: Path, opener: Opener = default_open) -> str:
    """Download ``url`` to ``target`` through a temporary name; returns the MD5 of what arrived."""
    part = target.with_name(target.name + '.part')
    digest = hashlib.md5()                           # noqa: S324
    try:
        with opener(url) as response, open(part, 'wb') as handle:
            for block in iter(lambda: response.read(CHUNK), b''):
                digest.update(block)
                handle.write(block)
        part.replace(target)
    finally:
        part.unlink(missing_ok=True)
    return digest.hexdigest()


def sync(record: Dict, dest: Path, opener: Opener = default_open, log=print,
         local_name: Callable[[str], str] = None) -> Dict[str, List[str]]:
    """Bring ``dest`` in line with the record. Returns the names ``fetched``, ``skipped`` (already there
    with the right sum) and ``refused`` (the sum did not match; the file is deleted). ``local_name`` maps a
    key of the record to the file name under ``dest`` (default: the key itself, which must be a plain name;
    a record may key its files with a folder, ``a/b.zip``)."""
    dest.mkdir(parents=True, exist_ok=True)
    done: Dict[str, List[str]] = {'fetched': [], 'skipped': [], 'refused': []}
    for entry in record['files']:
        name = (local_name or safe_name)(entry['key'])
        want = expected_md5(entry['checksum'])
        target = dest / name
        if target.is_file() and md5_of(target) == want:
            log(f'  ok      {name}')
            done['skipped'].append(name)
            continue
        problem = url_problem(entry['links']['self'])
        if problem:
            log(f'  REFUSED {name}: {problem}; not fetched')
            done['refused'].append(name)
            continue
        got = download(entry['links']['self'], target, opener)
        if got != want:
            target.unlink(missing_ok=True)           # a wrong file is never kept
            log(f'  REFUSED {name}: md5 {got}, the record says {want}; deleted')
            done['refused'].append(name)
        else:
            log(f'  fetched {name}')
            done['fetched'].append(name)
    return done

# THE API (shared by the run steps of the import tools) ------------------------------------------
RETRIES = 3                  # retries of one request after the first try (decision 8.157 f)
RETRY_AFTER_MAX = 60         # seconds: a longer Retry-After of the server is not waited for


def retry_wait(retry: int, retry_after: Optional[str]) -> float:
    """Seconds to wait before retry number ``retry`` (0, 1, 2): the server's ``Retry-After`` (whole seconds,
    at most RETRY_AFTER_MAX) when it sends one, else 1, 2, 4 seconds."""
    try:
        return float(min(max(int(str(retry_after).strip()), 0), RETRY_AFTER_MAX))
    except ValueError:
        return float(2 ** retry)


class Api:
    def __init__(self, server, token, renew=None, sleep=time.sleep):
        self.server = server.rstrip('/')
        self.token = token
        self.renew = renew
        import requests
        self.http = requests.Session()
        self.calls = 0
        self.retried = 0
        self.sleep = sleep

    def _send(self, method, url, headers, **kw):
        """One request. A 503 (the database is not available, decision 8.157 e) and a connection error
        (requests ConnectionError / Timeout) are tried again, at most RETRIES times; any other answer,
        a 500 included, comes back at once, so a real defect is not hidden. The steps of the import tools
        are idempotent, so a repeated request is safe."""
        import requests
        for retry in range(RETRIES + 1):
            try:
                self.calls += 1
                response = self.http.request(method, url, headers=headers, timeout=300, **kw)
            except (requests.ConnectionError, requests.Timeout):
                if retry == RETRIES:
                    raise
                wait = retry_wait(retry, None)
            else:
                if response.status_code != 503 or retry == RETRIES:
                    return response
                wait = retry_wait(retry, response.headers.get('Retry-After'))
            self.retried += 1
            self.sleep(wait)

    def request(self, method, path, **kw):
        for attempt in (1, 2):
            headers = {'Authorization': 'Bearer ' + self.token, 'X-CSC-Client': CLIENT}
            response = self._send(method, self.server + path, headers, **kw)
            if response.status_code == 401 and attempt == 1 and self.renew:
                self.token = self.renew()          # the token ran out during a long run
                continue
            return response

    def json(self, method, path, ok=(200, 201), **kw):
        response = self.request(method, path, **kw)
        if response.status_code not in ok:
            raise RuntimeError(f'{method} {path} -> {response.status_code}: {response.text[:400]}')
        return response.json() if response.content else None


def user_id_of(token):
    payload = token.split('.')[1]
    payload += '=' * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))['sub']


def ensure_datasets(api, plan, owner_id, log, wanted):
    have = {d['_id'] for d in api.json('GET', '/datasets')}
    for dataset in plan['datasets']:
        if dataset['id'] not in wanted:
            continue
        if dataset['id'] not in have:
            api.json('POST', '/datasets', ok=(201,), json={
                'id': dataset['id'], 'name': dataset['name'],
                'description': dataset['description'], 'visibility': 'members'})
            log(f'dataset {dataset["id"]} created')
        api.json('PUT', f'/datasets/{dataset["id"]}/members/{owner_id}',
                 json={'roles': ['moderator', 'contributor']})
