#!/usr/bin/env python3
"""
MongoDB Bounding Box Format Migration Script

This script migrates the bounding box format in the CSC database from:
OLD: [[minX, minY, minZ], [maxX, maxY, maxZ]] 
NEW: [X, Y, Z] (maximum extents)

Additionally, it converts date fields to proper ISO format:
- created: Convert to ISO format without changing the actual date
- lastmodified: Convert to ISO format and update to current time

The script:
1. Connects to MongoDB
2. Finds all components with the old bounding box format or old date format
3. Converts them to the new format
4. Updates the database
5. Provides a summary of the migration

Usage:
    python scripts/migrate_bounding_box_format.py

Requirements:
    - pymongo
    - MongoDB connection string in environment or config
"""

import os
import sys
import json
from typing import List, Any
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import logging
from datetime import datetime
import re

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bbx_migration.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load MongoDB configuration from environment or config file"""
    # Try to load from environment variables first
    mongo_uri = os.getenv('MONGO_URI')
    if mongo_uri:
        return {'uri': mongo_uri}
    
    # Try to load from config file
    config_path = os.path.normpath(os.path.abspath(os.path.join('..', 'src', 'backend', 'config', 'dbconfig.json')))
    print(f"Config path: {config_path}")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                # Construct MongoDB URI from config
                server = config.get('server')
                db = config.get('db')
                user = config.get('user')
                pwd = config.get('pwd')

                
                if user and pwd:
                    mongo_uri = (f"mongodb+srv://{user}:{pwd}@"
                                 f"{server}/{db}")
                
                return {'uri': mongo_uri}
        except Exception as e:
            logger.error(f"Failed to load config file: {e}")
            return None
    
    return None


def is_old_bbx_format(bbx: Any) -> bool:
    """
    Check if the bounding box is in the old format:
    [[minX, minY, minZ], [maxX, maxY, maxZ]]
    """
    if not isinstance(bbx, list) or len(bbx) != 2:
        return False
    
    min_coords, max_coords = bbx
    
    # Check if both are arrays with 3 numeric values
    if not isinstance(min_coords, list) or not isinstance(max_coords, list):
        return False
    
    if len(min_coords) != 3 or len(max_coords) != 3:
        return False
    
    # Check if all values are numbers
    try:
        all(isinstance(x, (int, float)) for x in min_coords + max_coords)
        return True
    except Exception:
        return False


def is_old_date_format(date_str: Any) -> bool:
    """
    Check if the date is in the old format:
    "240621-093139" or "241213-152418"
    """
    if not isinstance(date_str, str):
        return False
    
    # Check if it matches the pattern: YYMMDD-HHMMSS
    pattern = r'^\d{6}-\d{6}$'
    return bool(re.match(pattern, date_str))


def convert_bbx_format(old_bbx: List[List[float]]) -> List[float]:
    """
    Convert from old format [[minX, minY, minZ], [maxX, maxY, maxZ]]
    to new format [X, Y, Z] (maximum extents)
    """
    min_coords, max_coords = old_bbx
    
    # Calculate the maximum extents (dimensions)
    x_extent = abs(max_coords[0] - min_coords[0])
    y_extent = abs(max_coords[1] - min_coords[1])
    z_extent = abs(max_coords[2] - min_coords[2])
    
    return [x_extent, y_extent, z_extent]


def convert_date_format(old_date: str) -> str:
    """
    Convert from old format "240621-093139" to ISO format "2024-06-21T09:31:39Z"
    """
    try:
        # Parse the old format: YYMMDD-HHMMSS
        year = int(old_date[:2])
        month = int(old_date[2:4])
        day = int(old_date[4:6])
        hour = int(old_date[7:9])
        minute = int(old_date[9:11])
        second = int(old_date[11:13])
        
        # Assume 20xx for years (adjust if needed)
        full_year = 2000 + year
        
        # Create datetime object and convert to ISO format
        dt = datetime(full_year, month, day, hour, minute, second)
        return dt.isoformat() + 'Z'
    except Exception as e:
        logger.warning(f"Failed to convert date {old_date}: {e}")
        # Return current time as fallback
        return datetime.now().isoformat() + 'Z'


def migrate_bounding_boxes():
    """Main migration function"""
    logger.info("Starting bounding box and date format migration...")
    
    # Load configuration
    config = load_config()
    if not config:
        logger.error("Failed to load MongoDB configuration")
        return False
    
    try:
        # Connect to MongoDB
        client = MongoClient(config['uri'])
        
        # Get database - try default first, then extract from URI
        db = client.get_default_database()
        if db is None:
            # Try to get database from URI
            db_name = config['uri'].split('/')[-1].split('?')[0]
            db = client[db_name]
        
        components_collection = db.components
        
        logger.info(f"Connected to database: {db.name}")
        logger.info(f"Collection: {components_collection.name}")
        
        # Find all components that need migration (either old bbx format or old date format)
        migration_query = {
            "$or": [
                # Old bounding box format
                {
                    "bbx": {
                        "$type": "array",
                        "$elemMatch": {
                            "$type": "array",
                            "$elemMatch": {"$type": "number"}
                        }
                    }
                },
                # Old date format
                {
                    "$or": [
                        {"created": {"$regex": r"^\d{6}-\d{6}$"}},
                        {"lastmodified": {"$regex": r"^\d{6}-\d{6}$"}}
                    ]
                }
            ]
        }
        
        components_to_migrate = list(components_collection.find(migration_query))
        logger.info(f"Found {len(components_to_migrate)} components that need migration")
        
        if not components_to_migrate:
            logger.info("No components need migration. All components are already in the new format.")
            return True
        
        # Process each component
        migrated_count = 0
        skipped_count = 0
        error_count = 0
        
        for component in components_to_migrate:
            try:
                component_id = component.get('_id')
                updates = {}
                
                # Check and convert bounding box if needed
                old_bbx = component.get('bbx')
                if old_bbx and is_old_bbx_format(old_bbx):
                    new_bbx = convert_bbx_format(old_bbx)
                    updates['bbx'] = new_bbx
                    logger.info(
                        f"Component {component_id}: Converting bbx "
                        f"{old_bbx} -> {new_bbx}"
                    )
                
                # Check and convert created date if needed
                old_created = component.get('created')
                if old_created and is_old_date_format(old_created):
                    new_created = convert_date_format(old_created)
                    updates['created'] = new_created
                    logger.info(
                        f"Component {component_id}: Converting created "
                        f"{old_created} -> {new_created}"
                    )
                
                # Check and convert lastmodified date if needed
                old_lastmodified = component.get('lastmodified')
                if old_lastmodified and is_old_date_format(old_lastmodified):
                    # Always update lastmodified to current time when converting format
                    new_lastmodified = datetime.now().isoformat() + 'Z'
                    updates['lastmodified'] = new_lastmodified
                    logger.info(
                        f"Component {component_id}: Converting lastmodified "
                        f"{old_lastmodified} -> {new_lastmodified}"
                    )
                
                # Update the component if there are changes
                if updates:
                    result = components_collection.update_one(
                        {'_id': component_id},
                        {'$set': updates}
                    )
                    
                    if result.modified_count > 0:
                        migrated_count += 1
                        logger.info(f"Successfully migrated component {component_id}")
                    else:
                        logger.warning(f"Component {component_id}: No changes made")
                        skipped_count += 1
                else:
                    logger.info(f"Component {component_id}: No migration needed")
                    skipped_count += 1
                    
            except Exception as e:
                logger.error(f"Error processing component {component.get('_id', 'unknown')}: {e}")
                error_count += 1
        
        # Summary
        logger.info("=" * 50)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 50)
        logger.info(f"Total components found: {len(components_to_migrate)}")
        logger.info(f"Successfully migrated: {migrated_count}")
        logger.info(f"Skipped: {skipped_count}")
        logger.info(f"Errors: {error_count}")
        logger.info("=" * 50)
        
        if error_count == 0:
            logger.info("Migration completed successfully!")
            return True
        else:
            logger.warning(f"Migration completed with {error_count} errors")
            return False
            
    except PyMongoError as e:
        logger.error(f"MongoDB error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False
    finally:
        if 'client' in locals():
            client.close()
            logger.info("MongoDB connection closed")


def verify_migration():
    """Verify that the migration was successful"""
    logger.info("Verifying migration...")
    
    config = load_config()
    if not config:
        logger.error("Failed to load MongoDB configuration for verification")
        return False
    
    try:
        client = MongoClient(config['uri'])
        
        # Get database - try default first, then extract from URI
        db = client.get_default_database()
        if db is None:
            db_name = config['uri'].split('/')[-1].split('?')[0]
            db = client[db_name]
        
        components_collection = db.components
        
        # Check for any remaining old format bounding boxes
        old_bbx_query = {
            "bbx": {
                "$type": "array",
                "$elemMatch": {
                    "$type": "array",
                    "$elemMatch": {"$type": "number"}
                }
            }
        }
        
        remaining_old_bbx = list(components_collection.find(old_bbx_query))
        
        # Check for any remaining old format dates
        old_date_query = {
            "$or": [
                {"created": {"$regex": r"^\d{6}-\d{6}$"}},
                {"lastmodified": {"$regex": r"^\d{6}-\d{6}$"}}
            ]
        }
        
        remaining_old_dates = list(components_collection.find(old_date_query))
        
        if remaining_old_bbx:
            logger.warning(f"Found {len(remaining_old_bbx)} components still using old bbx format:")
            for comp in remaining_old_bbx[:3]:  # Show first 3
                logger.warning(f"  {comp.get('_id')}: bbx={comp.get('bbx')}")
        else:
            logger.info("✓ All components have been migrated to the new bbx format")
        
        if remaining_old_dates:
            logger.warning(
                f"Found {len(remaining_old_dates)} components still using old date format:"
            )
            for comp in remaining_old_dates[:3]:  # Show first 3
                logger.warning(
                    f"  {comp.get('_id')}: created={comp.get('created')}, "
                    f"lastmodified={comp.get('lastmodified')}"
                )
        else:
            logger.info("✓ All components have been migrated to the new date format")
        
        # Check new format
        new_bbx_query = {
            "bbx": {
                "$type": "array",
                "$elemMatch": {"$type": "number"}
            }
        }
        
        new_bbx_count = components_collection.count_documents(new_bbx_query)
        logger.info(f"✓ {new_bbx_count} components using new bbx format")
        
        # Check for ISO date format
        iso_date_query = {
            "$and": [
                {
                    "created": {
                        "$regex": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
                    }
                },
                {
                    "lastmodified": {
                        "$regex": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
                    }
                }
            ]
        }
        
        iso_date_count = components_collection.count_documents(iso_date_query)
        logger.info(f"✓ {iso_date_count} components using ISO date format")
        
        return len(remaining_old_bbx) == 0 and len(remaining_old_dates) == 0
        
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False
    finally:
        if 'client' in locals():
            client.close()


if __name__ == "__main__":
    print("CSC Bounding Box and Date Format Migration Script")
    print("=" * 60)
    
    # Run migration
    success = migrate_bounding_boxes()
    
    if success:
        print("\nMigration completed successfully!")
        
        # Ask user if they want to verify
        verify = input("\nWould you like to verify the migration? (y/n): ").lower().strip()
        if verify in ['y', 'yes']:
            verify_migration()
    else:
        print("\nMigration failed. Check the logs for details.")
        sys.exit(1)
