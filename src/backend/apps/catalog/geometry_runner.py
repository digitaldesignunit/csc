#!/usr/bin/env python3.13
"""
Writes the outcome of ``geometry_stages.run_stages`` (spec section 4.3).

Shared by the cron runner (``main_geometry.py``) and the API routes that run
stages 1--2 synchronously: files first, then one guarded ``update_one`` on
the snapshot, then the files that are no longer referenced.

The update is guarded by the snapshot's ``etag``: a concurrent edit makes it
a no-op and the next sweep sees the snapshot stale again, so a derivation
never overwrites an author's change with results computed from the old one.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import asyncio
import os
import uuid
from typing import Any, Dict, List, Mapping, Optional, Tuple

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.etag import compute_snapshot_etag
from apps.catalog.geometry_stages import Env, Outcome, now_z, run_stages


def _safe_join(root: str, relative: str) -> str:
    """``root/relative``, refusing anything that leaves ``root``."""
    path = os.path.normpath(os.path.join(root, relative))
    if not path.startswith(os.path.normpath(root) + os.sep):
        raise ValueError(f'path escapes the storage folder: {relative!r}')
    return path


def stage_files(outcome: Outcome, proxies_root: Optional[str],
                preview_dir: Optional[str], snapshot_id: str
                ) -> List[Tuple[str, str]]:
    """Write the outcome's files under temporary names; returns
    ``(temporary, final)`` pairs. Nothing is visible under a final name until
    ``commit_files``, which runs only after the guarded update succeeded
    (review finding 10): a lost race leaves no file of the lost result.
    Deviation maps go below ``proxies_root`` (paths ``proxies/<sid>/...`` are
    relative to its parent), the preview into ``preview_dir``."""
    pairs: List[Tuple[str, str]] = []
    try:
        if outcome.write_files:
            if not proxies_root:
                raise RuntimeError('SNAPSHOT_PROXIES_DIR is not configured')
            for name, data in outcome.write_files.items():
                final = _safe_join(proxies_root, name.split('/', 1)[1])
                pairs.append((_write_temp(final, data), final))
        if outcome.preview is not None and preview_dir:
            final = os.path.join(preview_dir, f'{snapshot_id}.webp')
            pairs.append((_write_temp(final, outcome.preview), final))
    except BaseException:
        discard_files(pairs)
        raise
    return pairs


def _write_temp(final: str, data: bytes) -> str:
    os.makedirs(os.path.dirname(final), exist_ok=True)
    temporary = f'{final}.{uuid.uuid4().hex[:8]}.tmp'
    with open(temporary, 'wb') as handle:
        handle.write(data)
    return temporary


def commit_files(pairs: List[Tuple[str, str]]) -> None:
    for temporary, final in pairs:
        os.replace(temporary, final)


def discard_files(pairs: List[Tuple[str, str]]) -> None:
    for temporary, _final in pairs:
        try:
            os.remove(temporary)
        except OSError:
            pass


def delete_files(outcome: Outcome, proxies_root: Optional[str]) -> None:
    if not proxies_root:
        return
    for name in outcome.delete_files:
        try:
            os.remove(_safe_join(proxies_root, name.split('/', 1)[1]))
        except (FileNotFoundError, ValueError):
            pass


def build_update(snapshot: Mapping[str, Any], outcome: Outcome
                 ) -> Dict[str, Any]:
    """The guarded Mongo update for an outcome (new etag included)."""
    merged: Dict[str, Any] = {**snapshot, **outcome.set}
    for key in outcome.unset:
        merged.pop(key, None)
    update: Dict[str, Any] = {'$set': {
        **outcome.set, 'lastmodified': now_z(),
        'etag': compute_snapshot_etag(merged)}}
    if outcome.unset:
        update['$unset'] = {key: '' for key in outcome.unset}
    return update


async def derive_and_store(snapshots, snapshot: Mapping[str, Any],
                           identity: Mapping[str, Any], env: Env,
                           proxies_root: Optional[str], stages,
                           force: bool = False, dry_run: bool = False,
                           retry_errors: bool = False) -> Outcome:
    """Run the stages in a worker thread and store what changed."""
    outcome = await asyncio.to_thread(run_stages, snapshot, identity, env,
                                      stages, force, retry_errors)
    if not outcome.changed or dry_run:
        return outcome
    sid = str(snapshot['_id'])
    pairs = await asyncio.to_thread(stage_files, outcome, proxies_root,
                                    env.preview_dir, sid)
    try:
        result = await snapshots.update_one(
            {'_id': sid, 'etag': snapshot.get('etag')},
            build_update(snapshot, outcome))
    except BaseException:
        discard_files(pairs)
        raise
    if result.matched_count == 0:
        discard_files(pairs)
        env.log(f'{sid} changed while it was derived; left for the next '
                f'sweep')
        outcome.errors['write'] = 'snapshot changed during derivation'
        return outcome
    await asyncio.to_thread(commit_files, pairs)
    await asyncio.to_thread(delete_files, outcome, proxies_root)
    return outcome


def derive_and_store_sync(snapshots, snapshot: Mapping[str, Any],
                          identity: Mapping[str, Any], env: Env,
                          proxies_root: Optional[str], stages,
                          force: bool = False, dry_run: bool = False,
                          retry_errors: bool = False) -> Outcome:
    """``derive_and_store`` for a synchronous pymongo collection (the
    migration rehearsal and tests)."""
    outcome = run_stages(snapshot, identity, env, stages, force, retry_errors)
    if not outcome.changed or dry_run:
        return outcome
    sid = str(snapshot['_id'])
    pairs = stage_files(outcome, proxies_root, env.preview_dir, sid)
    try:
        result = snapshots.update_one(
            {'_id': sid, 'etag': snapshot.get('etag')},
            build_update(snapshot, outcome))
    except BaseException:
        discard_files(pairs)
        raise
    if result.matched_count == 0:
        discard_files(pairs)
        outcome.errors['write'] = 'snapshot changed during derivation'
        return outcome
    commit_files(pairs)
    delete_files(outcome, proxies_root)
    return outcome
