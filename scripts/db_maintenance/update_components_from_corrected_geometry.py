#!/usr/bin/env python3
'''
Update MongoDB component documents with corrected geometry exports.

Uses the JSON files produced by correct_component_geometries.py to update
geometry, PCA metadata, and bounding boxes for each component. Supports a
dry-run mode for previewing changes.
'''

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pymongo import MongoClient
from pymongo.errors import PyMongoError


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_ROOT = Path(r'D:\01_PROJECT_WORKDATA\component_geometry_corrected')


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('update_corrected_geometry.log'),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def load_config() -> Optional[Dict[str, str]]:
    mongo_uri = os.getenv('MONGO_URI')
    if mongo_uri:
        return {'uri': mongo_uri}
    config_path = REPO_ROOT / 'src' / 'backend' / 'config' / 'dbconfig.json'
    if not config_path.exists():
        logger.error('Config file not found at %s', config_path)
        return None
    try:
        with config_path.open('r', encoding='utf-8') as file:
            config = json.load(file)
        server = config.get('server')
        db_name = config.get('db')
        user = config.get('user')
        password = config.get('pwd')
        if not server or not db_name:
            logger.error('Config file missing required "server" or "db" entries.')
            return None
        if user and password:
            mongo_uri = f'mongodb+srv://{user}:{password}@{server}/{db_name}'
        else:
            mongo_uri = f'mongodb://{server}/{db_name}'
        return {'uri': mongo_uri}
    except Exception as error:
        logger.error('Failed to load dbconfig.json: %s', error)
        return None


def load_corrected_components(input_root: Path) -> List[Tuple[str, Dict]]:
    components: List[Tuple[str, Dict]] = []
    if not input_root.exists():
        logger.error('Input root %s does not exist.', input_root)
        return components
    for entry in sorted(input_root.iterdir()):
        if not entry.is_dir():
            continue
        component_id = entry.name
        json_path = entry / f'{component_id}.json'
        if not json_path.exists():
            logger.warning('[%s] Missing JSON file at %s; skipping.', component_id, json_path)
            continue
        try:
            with json_path.open('r', encoding='utf-8') as json_file:
                component_data = json.load(json_file)
            components.append((component_id, component_data))
        except json.JSONDecodeError as error:
            logger.error('[%s] Failed to parse JSON: %s', component_id, error)
        except Exception as error:
            logger.error('[%s] Unexpected error reading JSON: %s', component_id, error)
    return components


def build_update_payload(component_data: Dict, timestamp: str) -> Dict:
    payload: Dict = {}
    for field in ('geometry', 'bbx', 'bbx_origin', 'pca_frame', 'marker_points'):
        if field in component_data:
            payload[field] = component_data[field]
    payload['lastmodified'] = timestamp
    payload['validated'] = False
    return payload


def update_components_from_files(input_root: Path, dry_run: bool = False) -> bool:
    logger.info('Loading corrected component JSON files from %s', input_root)
    components = load_corrected_components(input_root)
    if not components:
        logger.warning('No component JSON files found. Nothing to update.')
        return True
    config = load_config()
    if not config:
        return False
    try:
        client = MongoClient(config['uri'])
        db = client.get_default_database()
        if db is None:
            db_name = config['uri'].split('/')[-1].split('?')[0]
            db = client[db_name]
        collection = db.components
        logger.info('Connected to MongoDB database: %s', db.name)
        timestamp = datetime.utcnow().isoformat() + 'Z'
        logger.info('Using lastmodified timestamp: %s', timestamp)
        matched = 0
        modified = 0
        missing = []
        for component_id, component_data in components:
            update_payload = build_update_payload(component_data, timestamp)
            if dry_run:
                logger.info('[DRY-RUN][%s] Would update fields: %s', component_id, list(update_payload.keys()))
                continue
            result = collection.update_one({'_id': component_id}, {'$set': update_payload})
            if result.matched_count == 0:
                missing.append(component_id)
            else:
                matched += 1
                if result.modified_count > 0:
                    modified += 1
                logger.info('[%s] Updated component document (modified=%s).', component_id, bool(result.modified_count))
        if dry_run:
            logger.info('Dry run complete. %s components would be processed.', len(components))
            return True
        logger.info('Update summary: processed=%s matched=%s modified=%s', len(components), matched, modified)
        if missing:
            logger.warning('Missing %s components in database: %s', len(missing), ', '.join(missing))
        return True
    except PyMongoError as error:
        logger.error('MongoDB error: %s', error)
        return False
    except Exception as error:
        logger.error('Unexpected error: %s', error)
        return False
    finally:
        if 'client' in locals():
            client.close()
            logger.info('MongoDB connection closed.')


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Update MongoDB components from corrected geometry JSON files.',
    )
    parser.add_argument(
        '--input-root',
        type=Path,
        default=DEFAULT_INPUT_ROOT,
        help='Root folder containing <uuid>/<uuid>.json exports.',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show planned updates without modifying the database.',
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    logger.info('CSC Corrected Geometry Update Script')
    logger.info('Dry run mode: %s', args.dry_run)
    success = update_components_from_files(args.input_root, args.dry_run)
    if not success:
        sys.exit(1)


if __name__ == '__main__':
    main()

