#!/usr/bin/env python3
"""
Add ``is_public`` field to all documents in ``component_identities``.

Existing identities default to ``is_public: false`` (private catalog access).

Usage:
    python scripts/db_maintenance/migrate_add_is_public_field.py [--dry-run]

Options:
    --dry-run    Report changes without writing to MongoDB
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from pymongo import MongoClient
from pymongo.errors import PyMongoError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('is_public_migration.log'),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def load_config() -> dict | None:
    mongo_uri = os.getenv('MONGO_URI')
    if mongo_uri:
        return {'uri': mongo_uri}

    config_path = os.path.normpath(
        os.path.abspath(
            os.path.join('scripts', 'config', 'dbconfig.json')
        )
    )
    if not os.path.exists(config_path):
        config_path = os.path.normpath(
            os.path.abspath(
                os.path.join('..', 'scripts', 'config', 'dbconfig.json')
            )
        )

    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as handle:
            config = json.load(handle)
            server = config.get('server')
            db = config.get('db')
            user = config.get('user')
            pwd = config.get('pwd')
            if user and pwd:
                return {
                    'uri': f'mongodb+srv://{user}:{pwd}@{server}/{db}',
                }
            return {'uri': f'mongodb+srv://{server}/{db}'}

    logger.error('MongoDB configuration not found (MONGO_URI or dbconfig.json)')
    return None


def migrate(*, dry_run: bool) -> bool:
    config = load_config()
    if not config or not config.get('uri'):
        return False

    try:
        client = MongoClient(config['uri'])
        db = client.get_default_database()
        if db is None:
            db_name = config['uri'].split('/')[-1].split('?')[0]
            db = client[db_name]

        identities = db['component_identities']
        missing_filter = {
            '$or': [
                {'is_public': {'$exists': False}},
                {'is_public': None},
            ],
        }
        missing_count = identities.count_documents(missing_filter)
        already_public = identities.count_documents({'is_public': True})

        logger.info('Database: %s', db.name)
        logger.info('Identities missing is_public: %s', missing_count)
        logger.info('Identities already public: %s', already_public)

        if dry_run:
            logger.info('[DRY RUN] Would set is_public=false on %s documents', missing_count)
            return True

        if missing_count == 0:
            logger.info('Nothing to migrate.')
            return True

        result = identities.update_many(
            missing_filter,
            {'$set': {'is_public': False}},
        )
        logger.info('Updated %s identities', result.modified_count)
        return True
    except PyMongoError as exc:
        logger.error('Migration failed: %s', exc)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Backfill is_public=false on component_identities',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show planned changes without updating MongoDB',
    )
    args = parser.parse_args()
    ok = migrate(dry_run=args.dry_run)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
