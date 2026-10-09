#!/usr/bin/env python3.13
"""
Worker side of the geometry runner off the server (decision 8.45).

``main_geometry.py --remote <url>`` pulls the snapshots whose stages are
stale, fetches their source files, runs the stages locally and uploads the
results (``api/geometry_remote.py``). No database access: the worker only
needs an admin account on the server. A result computed from geometry that
changed meanwhile is refused (409) and left for the next pass.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json
import os
import shutil
import tempfile
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import httpx

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.geometry_cache import FIELDS_OF_STAGE, ResultCache, cache_key
from apps.catalog.geometry_stages import (
    STAGES,
    VERSIONS,
    Env,
    Outcome,
    run_stages,
)
from csc_version import CSC_VERSION

CLIENT_NAME = 'geometry-runner'
HEAVY_STAGES = ('proxies', 'descriptors', 'complexity', 'previews')
TIMEOUT = httpx.Timeout(120.0, connect=15.0)


class RemoteError(RuntimeError):
    """The server refused or failed a request."""


class RemoteRunner:
    """A logged-in admin session on a CSC server."""

    def __init__(self, base_url: str = '', *, token: Optional[str] = None,
                 user: Optional[str] = None, password: Optional[str] = None,
                 log: Callable[[str], None] = print,
                 client: Optional[httpx.Client] = None,
                 cache: Optional[ResultCache] = None) -> None:
        """``client`` replaces the HTTP client (tests pass the app's own);
        ``cache`` is the result cache of decision 8.122 f."""
        self.log = log
        self.cache = cache
        # what the run did, for its report: uploaded from the cache,
        # computed, a cached upload the server refused (then computed)
        self.stats = {'cached': 0, 'computed': 0, 'fallbacks': 0}
        self.client = client or httpx.Client(
            base_url=base_url.rstrip('/'), timeout=TIMEOUT)
        # sent with every request, never set on the client: a test passes
        # the app's shared client
        self.headers = {'X-CSC-Client': f'{CLIENT_NAME}/{CSC_VERSION}'}
        if token is None:
            if not (user and password):
                raise RemoteError('give a token, or a user and a password')
            response = self._call(
                'POST', '/auth/token',
                data={'username': user, 'password': password})
            self._check(response)
            token = response.json()['access_token']
        self.headers['Authorization'] = f'Bearer {token}'

    def _call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """One request; a network failure is a ``RemoteError``, like a
        refusal, so a run ends with a message and not a traceback."""
        try:
            return self.client.request(method, path, headers=self.headers,
                                       **kwargs)
        except httpx.HTTPError as exc:
            raise RemoteError(f'{method} {path}: {type(exc).__name__}') \
                from exc

    @staticmethod
    def _check(response: httpx.Response) -> httpx.Response:
        if response.is_success:
            return response
        try:
            detail = response.json().get('detail')
        except ValueError:
            detail = response.text[:200]
        raise RemoteError(f'{response.request.method} '
                          f'{response.request.url.path}: '
                          f'{response.status_code} {detail}')

    # PULL --------------------------------------------------------------------
    def stale(self, stages: Iterable[str], limit: int,
              after: Optional[str] = None, retry_errors: bool = False
              ) -> Tuple[List[dict], Optional[str]]:
        params: Dict[str, Any] = {'stages': ','.join(stages), 'limit': limit,
                                  'retry_errors': retry_errors}
        if after:
            params['after'] = after
        body = self._check(self._call('GET', '/geometry/stale',
                                      params=params)).json()
        return body['items'], body['last']

    def work(self, snapshot_id: str, stages: Iterable[str],
             retry_errors: bool = False) -> dict:
        return self._check(self._call(
            'GET', f'/geometry/work/{snapshot_id}',
            params={'stages': ','.join(stages),
                    'retry_errors': retry_errors})).json()

    def fetch_sources(self, work: dict, root: str) -> None:
        """The PLY files the server would read, in the layout the stages
        expect below ``root`` (``meshes/`` and ``point_clouds/``)."""
        sid = work['snapshot']['_id']
        for index, label in work['files']['meshes'].items():
            target = os.path.join(root, 'meshes', sid, index, f'{label}.ply')
            self._download(f'/snapshots/{sid}/meshes/{index}/{label}', target)
        for index in work['files']['point_clouds']:
            target = os.path.join(root, 'point_clouds', sid, f'{index}.ply')
            self._download(f'/snapshots/{sid}/point_clouds/{index}.ply',
                           target)

    def _download(self, path: str, target: str) -> None:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        try:
            with self.client.stream('GET', path,
                                    headers=self.headers) as response:
                if not response.is_success:
                    response.read()
                    self._check(response)
                with open(target, 'wb') as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
        except httpx.HTTPError as exc:
            raise RemoteError(f'GET {path}: {type(exc).__name__}') from exc

    # PUSH --------------------------------------------------------------------
    def cache_key_of(self, work: dict) -> Optional[Dict[str, Any]]:
        """The key of a result for ``work``; None when the server does not
        say the file sizes (an older server: no cache then)."""
        if 'file_sizes' not in work:
            return None
        return cache_key(work['snapshot'], work['context'],
                         work['file_sizes'], work.get('versions'))

    @staticmethod
    def result_body(work: dict, outcome: Outcome) -> Dict[str, Any]:
        """The ``result`` part of an upload for ``outcome``."""
        fields: Dict[str, Any] = {}
        # a failed stage sends its error and no fields (the server refuses
        # an explicit null and takes no result from a failed stage); the
        # exception is the partial descriptors of a stage that half worked
        failed_fields = {key for stage in outcome.errors
                         for key in FIELDS_OF_STAGE.get(stage, ())
                         if not (stage == 'descriptors'
                                 and key == 'descriptors')}
        for key, value in outcome.set.items():
            if key == 'derivation' or key.endswith('_source'):
                continue                  # stamps and sources: the server's
            if value is None or key in failed_fields:
                continue
            if key == 'geometry':
                fields['fitted_proxies'] = [
                    p for p in value.get('proxies') or []
                    if (p.get('fit') or {}).get('method') != 'authored']
            else:
                fields[key] = value
        if isinstance(fields.get('descriptors'), dict):
            # a descriptor the stages do not write (the dataset-specific
            # `sas_vectors`, kept on the piece) stays on the server and is
            # not sent back: the server refuses a key it does not know
            from apps.catalog.api.geometry_remote import ALLOWED_DESCRIPTORS
            fields['descriptors'] = {
                k: v for k, v in fields['descriptors'].items()
                if k in ALLOWED_DESCRIPTORS}
        return {
            'stages': outcome.ran,
            'source_fingerprint': work['source_fingerprint'],
            'context': work['context'],
            'versions': {stage: VERSIONS[stage] for stage in outcome.ran},
            'errors': outcome.errors,
            'set': fields,
        }

    def upload(self, work: dict, outcome: Outcome) -> dict:
        snapshot_id = work['snapshot']['_id']
        body = self.result_body(work, outcome)
        files = [('files', (name, data, 'application/octet-stream'))
                 for name, data in outcome.write_files.items()]
        if outcome.preview is not None:
            files.append(('files', ('preview.webp', outcome.preview,
                                    'image/webp')))
        response = self._call(
            'POST', f'/geometry/results/{snapshot_id}',
            data={'result': json.dumps(body)}, files=files or None)
        return self._check(response).json()

    # ONE SNAPSHOT ------------------------------------------------------------
    def process(self, snapshot_id: str, stages: List[str],
                force: bool = False, retry_errors: bool = False
                ) -> Optional[Outcome]:
        """Pull, compute, upload one snapshot; None when nothing was stale."""
        work = self.work(snapshot_id, stages, retry_errors)
        todo = stages if force else [s for s in stages if s in work['stale']]
        if not todo:
            return None
        if work['versions'] != VERSIONS:
            raise RemoteError(
                f'this runner has stage versions {VERSIONS}, the server '
                f'{work["versions"]}: update the runner')
        key = self.cache_key_of(work) if self.cache else None
        if key is not None:
            hit = self.cache.lookup(key, todo)
            if hit.outcome is not None:
                try:
                    self.upload(work, hit.outcome)
                    self.stats['cached'] += 1
                    self.log('    from the cache')
                    return hit.outcome
                except RemoteError as exc:
                    # never fail the run for a cached result: compute it
                    self.stats['fallbacks'] += 1
                    self.log(f'    cached result refused ({exc}); computing')
            else:
                self.log(f'    not cached: {hit.reason}')
        root = tempfile.mkdtemp(prefix='csc-geometry-')
        try:
            self.fetch_sources(work, root)
            env = Env(meshes_dir=os.path.join(root, 'meshes'),
                      point_clouds_dir=os.path.join(root, 'point_clouds'),
                      preview_dir=None, log=lambda m: self.log(f'    {m}'))
            outcome = run_stages(work['snapshot'], work['identity'], env,
                                 todo, force=True)
            if outcome.changed:
                self.upload(work, outcome)
                self.stats['computed'] += 1
                if key is not None and not outcome.errors \
                        and not self.cache.covers(key, outcome.ran):
                    self.cache.store(key, outcome)      # refresh the entry
            return outcome
        finally:
            shutil.rmtree(root, ignore_errors=True)


def run_remote(runner: RemoteRunner, stages: List[str],
               limit: Optional[int], snapshot: Optional[str] = None,
               force: bool = False, dry_run: bool = False,
               page: int = 20, retry_errors: bool = False
               ) -> Tuple[int, int, int]:
    """Process stale snapshots until none are left (or ``limit``); returns
    ``(visited, uploaded, refused)``."""
    visited = uploaded = refused = 0
    if snapshot:
        queue = [{'snapshot_id': snapshot}]
        cursor: Optional[str] = None
    else:
        queue, cursor = [], None
    while True:
        if not queue and not snapshot:
            queue, cursor = runner.stale(stages, page, cursor, retry_errors)
            if not queue:
                break
        if not queue:
            break
        item = queue.pop(0)
        if limit is not None and visited >= limit:
            break
        visited += 1
        sid = item['snapshot_id']
        runner.log(f'{sid}: {", ".join(item.get("stale") or stages)}')
        if dry_run:
            continue
        try:
            outcome = runner.process(sid, stages, force=force,
                                     retry_errors=retry_errors)
        except RemoteError as exc:
            refused += 1
            runner.log(f'    refused: {exc}')
            continue
        if outcome is not None:
            uploaded += 1
            for stage, message in outcome.errors.items():
                runner.log(f'    {stage}: {message}')
            runner.log(f'    uploaded {", ".join(outcome.ran)}')
        if snapshot:
            break
    return visited, uploaded, refused


__all__ = ['RemoteRunner', 'RemoteError', 'run_remote', 'HEAVY_STAGES',
           'STAGES']
