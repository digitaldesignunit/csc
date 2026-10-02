#!/usr/bin/env python3.13
"""
Geometry runner: derives everything computed from a snapshot's source
geometry (data model spec section 4.3, decisions 6.14, 8.7, 8.54).

One runner, ordered stages, replacing ``main_descriptors_simple.py`` and
``main_previewgen.py``:

    frame --> shape_class --> proxies --> descriptors --> complexity
    --> previews

Each stage stores its version and a fingerprint of its inputs on the
snapshot (``derivation``); a stage is stale when either differs or its output
is missing, and the sweep reruns everything stale, so a changed upstream
result reruns its dependents. A stage that ended in an error is current for
that version and input (``--retry-errors`` runs it again) and blocks the
stages that read its result. The cheap stages (frame, shape class) also run
synchronously in the API on every draft geometry write and on submit.

Where the heavy stages (proxies, descriptors, complexity, previews) run is
set by ``CSC_GEOMETRY_HEAVY_STAGES`` (``server``, the default, or ``remote``):
with ``remote`` this cron runs only frame and shape class, and a worker
elsewhere runs the rest with ``--remote``.

Usage (the cron entry passes ``--limit 25``; without ``--limit`` a run
handles 5 snapshots):
    python main_geometry.py                           # 5 stale snapshots
    python main_geometry.py --all                     # every stale snapshot
    python main_geometry.py --limit 50 --dry-run
    python main_geometry.py --snapshot <sid>          # one snapshot
    python main_geometry.py --stages shape_class,frame --recompute
    python main_geometry.py --stages proxies,descriptors --recompute --all

Off the server (decision 8.45): the same stages on another machine, through
the API of a running server, with no database access. Needs an admin account
(password in CSC_API_PASSWORD, or a token in CSC_API_TOKEN):
    python main_geometry.py --remote https://api.example.org --user svc --all
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import argparse
import asyncio
import os
import re
import shutil
import sys
import time
from typing import List, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pymongo import AsyncMongoClient

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.catalog.geometry_runner import derive_and_store
from apps.catalog.geometry_stages import (
    STAGES,
    Env,
    server_stages,
    stale_stages,
)
from utility import (
    create_logging_timestamp as logts,
    get_database_name,
    get_db_connectionstring,
    get_snapshot_meshes_directory,
    get_snapshot_point_clouds_directory,
    get_snapshot_preview_directory,
    get_snapshot_proxies_directory,
)

DEFAULT_LIMIT = 5
_SNAPSHOT_ID = re.compile(r'^[0-9a-fA-F-]{36}$')


def log(message: str, prefix: str = 'GEOMETRY') -> None:
    print(f'[{prefix}] {logts()} {message}', flush=True)


def _optional(getter) -> Optional[str]:
    try:
        return getter()
    except KeyError:
        return None


def parse_stages(value: str) -> List[str]:
    stages = [s.strip() for s in value.split(',') if s.strip()]
    unknown = [s for s in stages if s not in STAGES]
    if unknown:
        raise argparse.ArgumentTypeError(
            f'unknown stages {unknown}; choose from {", ".join(STAGES)}')
    return stages


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Derive frame, shape class, proxies, descriptors, '
                    'complexity and previews of catalog snapshots.')
    parser.add_argument('--stages', type=parse_stages, default=None,
                        metavar='A,B,...',
                        help=f'stages to run, in this order: '
                             f'{",".join(STAGES)}. Default: all of them, '
                             f'or with CSC_GEOMETRY_HEAVY_STAGES=remote '
                             f'only frame and shape_class; with --remote '
                             f'the heavy ones')
    parser.add_argument('--recompute', action='store_true',
                        help='run the stages on every snapshot, stale or '
                             'not (after changing how a stage computes: '
                             'bump its version instead when you can)')
    parser.add_argument('--all', dest='process_all', action='store_true',
                        help='no limit on the number of snapshots')
    parser.add_argument('--limit', type=int, default=None, metavar='N',
                        help=f'at most N snapshots (default {DEFAULT_LIMIT}, '
                             f'unlimited with --all)')
    parser.add_argument('--snapshot', metavar='SID',
                        help='only this snapshot')
    parser.add_argument('--dry-run', action='store_true',
                        help='compute, report, write nothing')
    parser.add_argument('--remote', metavar='URL',
                        help='work through the API of this server instead '
                             'of its database and disks (decision 8.45)')
    parser.add_argument('--user', help='--remote: the admin account')
    parser.add_argument('--retry-errors', action='store_true',
                        help='also rerun stages whose last run ended in an '
                             'error with the same version and inputs')
    return parser.parse_args(argv)


def _limit(args: argparse.Namespace) -> Optional[int]:
    if args.limit is not None:
        if args.limit <= 0:
            print('--limit must be a positive integer', file=sys.stderr)
            sys.exit(2)
        return args.limit
    if args.process_all or args.snapshot:
        return None
    return DEFAULT_LIMIT


async def run(args: argparse.Namespace) -> int:
    limit = _limit(args)
    try:
        default_stages = server_stages()
    except ValueError as exc:                    # CSC_GEOMETRY_HEAVY_STAGES
        log(str(exc), 'ERROR')
        return 2
    stages = [s for s in STAGES if s in (args.stages or default_stages)]
    env = Env(
        meshes_dir=get_snapshot_meshes_directory(),
        point_clouds_dir=_optional(get_snapshot_point_clouds_directory),
        preview_dir=get_snapshot_preview_directory(),
        log=lambda message: log(f'    {message}'))
    proxies_root = get_snapshot_proxies_directory()
    client = AsyncMongoClient(get_db_connectionstring(),
                              serverSelectionTimeoutMS=5000)
    visited = changed = failed = 0
    started = time.time()
    try:
        await client.aconnect()
        await client.admin.command('ping')
        db = client[get_database_name()]
        snapshots, identities = (db['component_snapshots'],
                                 db['component_identities'])
        query = {'_id': args.snapshot} if args.snapshot else {}
        cursor = snapshots.find(query).sort('_id', 1)
        async for snapshot in cursor:
            if limit is not None and visited >= limit:
                break
            identity = await identities.find_one(
                {'_id': snapshot['identity_id']})
            if identity is None:
                log(f'{snapshot["_id"]} has no identity', 'WARNING')
                continue
            if not args.recompute:
                due = stale_stages(snapshot, identity, env, stages,
                                   args.retry_errors)
                if not due:
                    continue
                log(f'{snapshot["_id"]} v{snapshot.get("version")}: '
                    f'stale {", ".join(due)}')
            else:
                log(f'{snapshot["_id"]} v{snapshot.get("version")}: '
                    f'recompute {", ".join(stages)}')
            visited += 1
            began = time.time()
            outcome = await derive_and_store(
                snapshots, snapshot, identity, env, proxies_root,
                stages, force=args.recompute, dry_run=args.dry_run,
                retry_errors=args.retry_errors)
            took = time.time() - began
            if outcome.errors:
                failed += 1
                for stage, message in outcome.errors.items():
                    log(f'    {stage}: {message}', 'ERROR')
            if outcome.changed:
                changed += 1
            log(f'    ran {", ".join(outcome.ran) or "nothing"} '
                f'({took:.1f} s)'
                + (' [dry run]' if args.dry_run else ''))
        if not args.snapshot and not args.dry_run:
            # whatever the stages of this run: also on a server that leaves
            # the heavy stages to a remote worker (the files are still here)
            live = {s['_id'] async for s in snapshots.find({}, {'_id': 1})}
            _sweep_orphans(env.preview_dir, proxies_root, live)
        await _report_failures(snapshots)
    finally:
        await client.close()
    log(f'visited {visited}, changed {changed}, with errors {failed} '
        f'({time.time() - started:.0f} s)')
    return 0 if not failed else 1


async def _report_failures(snapshots) -> None:
    """Name every snapshot that carries a stage error, so a failure is never
    silent (decision 8.60): the stage and the stored (short) text."""
    query = {'$or': [{f'derivation.{stage}.error': {'$type': 'string'}}
                     for stage in STAGES]}
    rows = [row async for row in snapshots.find(
        query, {'derivation': 1, 'version': 1, 'identity_id': 1}
    ).sort('_id', 1).limit(51)]
    if not rows:
        return
    log(f'snapshots with failed stages: {min(len(rows), 50)}'
        f'{"+" if len(rows) > 50 else ""}', 'WARNING')
    for row in rows[:50]:
        for stage, stamp in (row.get('derivation') or {}).items():
            if stamp and stamp.get('error'):
                log(f'    {row["_id"]} v{row.get("version")} {stage}: '
                    f'{stamp["error"]}', 'WARNING')


def _sweep_orphans(preview_dir: Optional[str], proxies_root: str,
                   live_ids: set) -> None:
    """Previews and deviation maps of snapshots that no longer exist.

    Deletes only entries named like a snapshot id (``<uuid>.webp`` and
    ``<uuid>/``), and does nothing at all when the database holds no
    snapshot --- a wrong or empty database must not empty the folders.
    """
    if not live_ids:
        log('no snapshot in the database: orphan sweep skipped', 'WARNING')
        return
    if preview_dir and os.path.isdir(preview_dir):
        for name in os.listdir(preview_dir):
            stem, ext = os.path.splitext(name)
            if ext == '.webp' and _SNAPSHOT_ID.match(stem) \
                    and stem not in live_ids:
                os.remove(os.path.join(preview_dir, name))
                log(f'deleted stale preview {name}')
    if os.path.isdir(proxies_root):
        for name in os.listdir(proxies_root):
            path = os.path.join(proxies_root, name)
            if os.path.isdir(path) and _SNAPSHOT_ID.match(name) \
                    and name not in live_ids:
                shutil.rmtree(path, ignore_errors=True)
                log(f'deleted maps of removed snapshot {name}')


def run_remote_mode(args: argparse.Namespace) -> int:
    import httpx

    from apps.catalog.remote_runner import (
        HEAVY_STAGES,
        RemoteError,
        RemoteRunner,
        run_remote,
    )
    stages = [s for s in STAGES if s in (args.stages or HEAVY_STAGES)]
    try:
        runner = RemoteRunner(
            args.remote, token=os.environ.get('CSC_API_TOKEN'),
            user=args.user, password=os.environ.get('CSC_API_PASSWORD'),
            log=log)
        visited, uploaded, refused = run_remote(
            runner, stages, _limit(args), snapshot=args.snapshot,
            force=args.recompute, dry_run=args.dry_run,
            retry_errors=args.retry_errors)
    except (RemoteError, httpx.HTTPError) as exc:
        log(str(exc), 'ERROR')
        return 2
    log(f'visited {visited}, uploaded {uploaded}, refused {refused}')
    return 0 if not refused else 1


if __name__ == '__main__':
    arguments = _parse_args()
    if arguments.remote:
        sys.exit(run_remote_mode(arguments))
    sys.exit(asyncio.run(run(arguments)))
