#!/usr/bin/env python3
"""
Normalize timestamp fields in MongoDB to UTC ISO 8601 with 'Z' suffix and
no fractional seconds, e.g. '2024-06-21T09:31:39Z'.

Targets:
- components.lastmodified
- designs.created
- designs.lastmodified

Non-interactive: reads config env or config file like other
maintenance scripts.
"""

import os
import sys
import json
from datetime import datetime, timezone
from typing import Optional
from pymongo import MongoClient
import logging


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def load_config() -> Optional[dict]:
    mongo_uri = os.getenv('MONGO_URI')
    if mongo_uri:
        return {'uri': mongo_uri}

    config_path = os.path.normpath(
        os.path.abspath(
            os.path.join(
                '..', '..', 'src', 'backend', 'config', 'dbconfig.json'
            )
        )
    )
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            server = config.get('server')
            db = config.get('db')
            user = config.get('user')
            pwd = config.get('pwd')
            if user and pwd:
                return {
                    'uri': (
                        f"mongodb+srv://{user}:{pwd}@{server}/{db}"
                    )
                }
        except Exception as e:
            logger.error(f'Failed to load config file: {e}')
    return None


def to_utc_z_seconds(ts: str) -> Optional[str]:
    """Convert various ISO-like strings to UTC Z format without subseconds.

    Returns normalized string in format: 2024-06-21T09:31:39Z
    """
    if not ts or not isinstance(ts, str):
        return None
    try:
        s = ts.strip()
        # Remove trailing Z if present (handles cases like
        # "2025-10-26T18:14:26.812561+00:00Z")
        if s.endswith('Z'):
            s = s[:-1]
        # Now parse - fromisoformat can handle formats like:
        # "2024-06-21T09:31:39", "2024-06-21T09:31:39.123",
        # "2024-06-21T09:31:39+00:00"
        dt = datetime.fromisoformat(s)
        # Ensure UTC timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        # Remove microseconds and format as YYYY-MM-DDTHH:MM:SSZ
        dt_utc = dt.replace(microsecond=0)
        # Format manually to ensure exact format: 2024-06-21T09:31:39Z
        return dt_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
    except Exception:
        return None


def normalize_collection_timestamps(db) -> bool:
    components = db.components
    designs = db.designs

    modified = 0

    # Components.lastmodified
    for doc in components.find({}, {'_id': 1, 'lastmodified': 1}):
        lm = doc.get('lastmodified')
        normalized = to_utc_z_seconds(lm)
        if normalized and normalized != lm:
            components.update_one(
                {'_id': doc['_id']},
                {'$set': {'lastmodified': normalized}}
            )
            modified += 1

    # Designs.created and lastmodified
    for doc in designs.find({}, {'_id': 1, 'created': 1, 'lastmodified': 1}):
        updates = {}
        cr = doc.get('created')
        lm = doc.get('lastmodified')
        ncr = to_utc_z_seconds(cr)
        nlm = to_utc_z_seconds(lm)
        if ncr and ncr != cr:
            updates['created'] = ncr
        if nlm and nlm != lm:
            updates['lastmodified'] = nlm
        if updates:
            designs.update_one({'_id': doc['_id']}, {'$set': updates})
            modified += 1

    logger.info(f'Normalized timestamps in {modified} documents')
    return True


def main() -> int:
    config = load_config()
    if not config:
        logger.error('No MongoDB configuration found')
        return 1
    client = MongoClient(config['uri'])
    try:
        db = client.get_default_database()
        logger.info(f'Connected to database: {db.name}')
        ok = normalize_collection_timestamps(db)
        return 0 if ok else 1
    finally:
        client.close()


if __name__ == '__main__':
    sys.exit(main())
