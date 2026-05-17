#!/usr/bin/env python3
"""
M4.8 prep — copy legacy component previews to snapshot_previews/
==================================================================

Copies ``{PREVIEW_DIR}/{identity_id}.webp`` to
``{SNAPSHOT_PREVIEW_DIR}/{current_snapshot_id}.webp`` for every identity
that has a current snapshot.

After this script has been run (and verified), the API can rely on
``snapshot_previews/`` only and you may retire the legacy preview tree
when ready.

Safety
------

* **Dry-run by default.** Pass ``--apply`` to copy files.
* Skips when the destination already exists (use ``--force`` to overwrite).
* Logs to ``logs/m4_snapshot_preview_backfill.log``.

Usage
-----

::

    export PREVIEW_DIR=...
    export SNAPSHOT_PREVIEW_DIR=...
    export MONGODB_URI=...

    python scripts/db_maintenance/m4_snapshot_preview_backfill.py
    python scripts/db_maintenance/m4_snapshot_preview_backfill.py --apply
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import PyMongoError

REPO_ROOT = Path(__file__).resolve().parents[2]
_LOG_DIR = REPO_ROOT / 'logs'
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_PATH = _LOG_DIR / 'm4_snapshot_preview_backfill.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(_LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def _load_uri() -> str:
    uri = os.environ.get('MONGODB_URI')
    if not uri:
        cfg = REPO_ROOT / 'scripts' / 'config' / 'dbconfig.json'
        if cfg.is_file():
            import json
            with cfg.open('r', encoding='utf-8') as handle:
                data = json.load(handle)
            uri = (
                f"mongodb+srv://{data['user']}:{data['pwd']}@"
                f"{data['server']}/{data['db']}"
            )
    if not uri:
        raise SystemExit(
            'Set MONGODB_URI or provide scripts/config/dbconfig.json'
        )
    return uri


def _preview_dirs() -> tuple[Path, Path]:
    legacy = os.environ.get('PREVIEW_DIR')
    target = os.environ.get('SNAPSHOT_PREVIEW_DIR')
    if not legacy or not target:
        raise SystemExit(
            'Set PREVIEW_DIR and SNAPSHOT_PREVIEW_DIR '
            '(same values as the FastAPI process).'
        )
    return Path(legacy).resolve(), Path(target).resolve()


def run(*, apply: bool, force: bool) -> int:
    legacy_dir, target_dir = _preview_dirs()
    target_dir.mkdir(parents=True, exist_ok=True)

    client = MongoClient(_load_uri(), serverSelectionTimeoutMS=15000)
    db = client.get_default_database()
    identities = db['component_identities']

    stats = {
        'total': 0,
        'copied': 0,
        'skipped_exists': 0,
        'skipped_missing_source': 0,
        'skipped_no_snapshot': 0,
        'errors': 0,
    }

    try:
        cursor = identities.find(
            {},
            {'_id': 1, 'current_snapshot_id': 1},
        )
        for doc in cursor:
            stats['total'] += 1
            identity_id = doc.get('_id')
            snapshot_id = doc.get('current_snapshot_id')
            if not snapshot_id:
                stats['skipped_no_snapshot'] += 1
                continue

            src = legacy_dir / f'{identity_id}.webp'
            dest = target_dir / f'{snapshot_id}.webp'

            if not src.is_file():
                stats['skipped_missing_source'] += 1
                continue

            if dest.is_file() and not force:
                stats['skipped_exists'] += 1
                continue

            if not apply:
                logger.info('[dry-run] copy %s -> %s', src, dest)
                stats['copied'] += 1
                continue

            try:
                shutil.copy2(src, dest)
                stats['copied'] += 1
            except OSError as exc:
                stats['errors'] += 1
                logger.error('copy failed %s -> %s: %s', src, dest, exc)
    except PyMongoError as exc:
        logger.error('Mongo error: %s', exc)
        return 1
    finally:
        client.close()

    logger.info('--- summary ---')
    for key, value in stats.items():
        logger.info('  %s: %s', key, value)
    if not apply:
        logger.info('Dry-run only. Re-run with --apply to copy files.')
    return 1 if stats['errors'] else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Copy legacy identity previews to snapshot_previews/',
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Perform copies (default: dry-run)',
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing destination files',
    )
    args = parser.parse_args()
    raise SystemExit(run(apply=args.apply, force=args.force))


if __name__ == '__main__':
    main()
