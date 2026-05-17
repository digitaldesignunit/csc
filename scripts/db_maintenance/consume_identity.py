#!/usr/bin/env python3
"""
Mark a v0.5 identity as consumed (admin archive semantics).

Sets ``consumed_at`` and clears ``reserved`` on ``component_identities``.
Does not move or delete geometry files.

Usage::

    conda run -n csc python scripts/db_maintenance/consume_identity.py \\
        0499c9a7-eaf5-4fd3-96ab-d6065f8eba65 --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import PyMongoError

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_uri() -> str:
    uri = os.environ.get('MONGODB_URI')
    if not uri:
        cfg = REPO_ROOT / 'scripts' / 'config' / 'dbconfig.json'
        if cfg.is_file():
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


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


def main() -> None:
    parser = argparse.ArgumentParser(description='Consume a component identity')
    parser.add_argument('identity_id', help='UUID of component_identities._id')
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Write consumed_at (default is dry-run)',
    )
    args = parser.parse_args()

    client = MongoClient(_load_uri(), serverSelectionTimeoutMS=30000)
    db = client.get_default_database()
    col = db['component_identities']

    doc = col.find_one({'_id': args.identity_id})
    if not doc:
        raise SystemExit(f'Identity not found: {args.identity_id}')

    if doc.get('consumed_at'):
        print(f'Already consumed at {doc["consumed_at"]}')
        return

    now = now_iso()
    print(f'Identity: {args.identity_id}')
    print(f'  catalog_number: {doc.get("catalog_number")}')
    print(f'  current_snapshot_id: {doc.get("current_snapshot_id")}')
    print(f'  would set consumed_at: {now}')

    if not args.apply:
        print('Dry-run only. Re-run with --apply to consume.')
        return

    try:
        result = col.update_one(
            {'_id': args.identity_id},
            {
                '$set': {
                    'consumed_at': now,
                    'reserved': '',
                    'lastmodified': now,
                },
            },
        )
    except PyMongoError as exc:
        raise SystemExit(f'Mongo error: {exc}') from exc
    finally:
        client.close()

    if result.modified_count:
        print('Consumed.')
    else:
        print('No document modified.')


if __name__ == '__main__':
    main()
