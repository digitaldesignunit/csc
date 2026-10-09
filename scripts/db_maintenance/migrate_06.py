"""Migrate a CSC database from 0.5 to 0.6 (data model spec section 8.1).

Runs the steps of ``apps.catalog.migration06`` in run order. Every step is
idempotent and stops the run with nothing written for that step when a
guard finds a document it cannot classify. ``--dry-run`` computes and
reports everything but writes nothing (files included).

Mongo connection: ``--uri``, else ``MONGO_URI`` env, else
``scripts/config/dbconfig.json`` (``{"uri": ...}``). Storage directories
default to ``SNAPSHOT_MESHES_DIR`` / ``SNAPSHOT_CAPTURE_DIR``.

Usage
-----
::

    python scripts/db_maintenance/migrate_06.py --list
    python scripts/db_maintenance/migrate_06.py --all --dry-run
    python scripts/db_maintenance/migrate_06.py --steps 1,1b,1c
    python scripts/db_maintenance/migrate_06.py --steps 11b \\
        --mapping .dev/reattribute_06.json --by-user <admin user id>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_BACKEND = os.getenv('CSC_BACKEND_DIR') or str(_REPO / 'src' / 'backend')
sys.path.insert(0, _BACKEND)

from apps.catalog.migration06.mappings import MigrationAbort  # noqa: E402
from apps.catalog.migration06.steps import (  # noqa: E402
    CUTOVER_STEPS,
    STEPS,
    Context,
    default_dirs,
    run,
)


def _uri(explicit: str | None) -> str:
    if explicit:
        return explicit
    if os.getenv('MONGO_URI'):
        return os.environ['MONGO_URI']
    config = _REPO / 'scripts' / 'config' / 'dbconfig.json'
    if config.is_file():
        return json.loads(config.read_text(encoding='utf-8'))['uri']
    sys.exit('no database: pass --uri, set MONGO_URI or create '
             'scripts/config/dbconfig.json')


def _list() -> None:
    for step in STEPS:
        after = ', '.join(step.after) or '---'
        print(f'{step.id:4s} {step.kind:7s} after {after:12s} {step.title}')
    print(f'--all runs the db steps: {", ".join(CUTOVER_STEPS)}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--uri')
    parser.add_argument('--db', default='csc')
    which = parser.add_mutually_exclusive_group()
    which.add_argument('--all', action='store_true',
                       help='every cutover step (not the runner, 14, 11b)')
    which.add_argument('--steps', help='comma-separated step ids')
    which.add_argument('--list', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    dirs = default_dirs()
    parser.add_argument('--meshes-dir', type=Path, default=dirs['meshes_dir'])
    parser.add_argument('--capture-dir', type=Path,
                        default=dirs['capture_dir'])
    parser.add_argument('--no-files', action='store_true',
                        help='step 6c: do not move fixture PLY files')
    parser.add_argument('--archive-dir', type=Path,
                        help='step 13: where the designs archive goes')
    parser.add_argument('--condition-datasets',
                        help='step 6b: migrate the grades of exactly these '
                             'datasets (comma-separated; default: those '
                             'whose grades vary)')
    parser.add_argument('--mapping', type=Path,
                        help='step 11b: JSON {from: [usernames], '
                             'datasets|identities|snapshots: {key: user id '
                             'or username}}; template '
                             'reattribute_06.example.json, the filled-in '
                             'file stays untracked')
    parser.add_argument('--shared-account', default='ddu')
    parser.add_argument('--by-user', help='step 11b: the admin running it')
    args = parser.parse_args()

    if args.list:
        _list()
        return 0
    if args.all:
        step_ids = list(CUTOVER_STEPS)
    elif args.steps:
        step_ids = [s.strip() for s in args.steps.split(',') if s.strip()]
    else:
        parser.error('pass --all, --steps or --list')

    from pymongo import MongoClient
    with MongoClient(_uri(args.uri), serverSelectionTimeoutMS=5000) as client:
        ctx = Context(
            db=client[args.db],
            dry_run=args.dry_run,
            meshes_dir=args.meshes_dir,
            capture_dir=args.capture_dir,
            archive_dir=args.archive_dir,
            files=not args.no_files,
            condition_datasets=(args.condition_datasets.split(',')
                                if args.condition_datasets else None),
            shared_account=args.shared_account,
            shared_mapping=(json.loads(args.mapping.read_text('utf-8'))
                            if args.mapping else None),
            operator_user_id=args.by_user,
        )
        try:
            run(ctx, step_ids)
        except MigrationAbort as exc:
            print(f'ABORTED: {exc}', file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
