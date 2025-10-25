#!/usr/bin/env python3
"""
MongoDB LastModified Timestamp Migration Script

This script updates all 'lastmodified' timestamps to the current time for all
components in the CSC database. This is useful when making schema changes or
migrations that should trigger cache invalidation.

The script:
1. Connects to MongoDB
2. Finds all components in the database
3. Updates their lastmodified field to the current UTC timestamp
4. Provides a summary of the migration

Usage:
    python scripts/migrate_lastmodified_timestamps.py

Requirements:
    - pymongo
    - MongoDB connection string in environment or config
"""

import os
import sys
import json
from datetime import datetime
from typing import Optional
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('lastmodified_migration.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def load_config() -> Optional[dict]:
    """Load MongoDB configuration from environment or config file"""
    # Try to load from environment variables first
    mongo_uri = os.getenv('MONGO_URI')
    if mongo_uri:
        return {'uri': mongo_uri}

    # Try to load from config file
    config_path = os.path.normpath(os.path.abspath(
        os.path.join('..', 'src', 'backend', 'config', 'dbconfig.json')
    ))
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


def get_current_timestamp() -> str:
    """Get current UTC timestamp in ISO format with Z suffix"""
    return datetime.utcnow().isoformat() + 'Z'


def migrate_lastmodified_timestamps():
    """Main migration function"""
    logger.info("Starting lastmodified timestamp migration...")

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

        # Get current timestamp
        current_timestamp = get_current_timestamp()
        logger.info(f"Setting all lastmodified timestamps to: "
                    f"{current_timestamp}")

        # Count total components
        total_components = components_collection.count_documents({})
        logger.info(f"Found {total_components} components to update")

        if total_components == 0:
            logger.info("No components found in the database.")
            return True

        # Update all components with the current timestamp
        result = components_collection.update_many(
            {},  # Empty filter matches all documents
            {
                '$set': {
                    'lastmodified': current_timestamp
                }
            }
        )

        # Summary
        logger.info("=" * 60)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total components in database: {total_components}")
        logger.info(f"Components matched: {result.matched_count}")
        logger.info(f"Components modified: {result.modified_count}")
        logger.info(f"New timestamp applied: {current_timestamp}")
        logger.info("=" * 60)

        if result.matched_count == total_components:
            logger.info("Migration completed successfully!")
            logger.info("All component lastmodified timestamps updated.")
            return True
        else:
            logger.warning(
                f"Migration incomplete: Expected {total_components} matches, "
                f"but got {result.matched_count}"
            )
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

        # Get total components
        total_components = components_collection.count_documents({})

        # Get components with lastmodified field
        has_lastmodified_query = {"lastmodified": {"$exists": True}}
        has_lastmodified_count = components_collection.count_documents(
            has_lastmodified_query)

        # Get most recent lastmodified timestamps
        recent_components = list(
            components_collection.find(
                {},
                {"_id": 1, "lastmodified": 1}
            ).sort("lastmodified", -1).limit(5)
        )

        # Check for components without lastmodified field
        missing_lastmodified_query = {"lastmodified": {"$exists": False}}
        missing_lastmodified_count = components_collection.count_documents(
            missing_lastmodified_query)

        logger.info("=" * 50)
        logger.info("VERIFICATION RESULTS")
        logger.info("=" * 50)
        logger.info(f"Total components: {total_components}")
        logger.info(f"Components with lastmodified field: "
                    f"{has_lastmodified_count}")
        logger.info(f"Components missing lastmodified field: "
                    f"{missing_lastmodified_count}")
        logger.info("")
        logger.info("Most recent lastmodified timestamps:")
        for component in recent_components:
            timestamp = component.get('lastmodified', 'N/A')
            logger.info(f"  {component['_id']}: {timestamp}")
        logger.info("=" * 50)

        if missing_lastmodified_count == 0:
            logger.info("✓ All components have lastmodified field")
        else:
            logger.warning(f"⚠ Found {missing_lastmodified_count} components "
                           f"missing lastmodified field")

        if has_lastmodified_count == total_components:
            logger.info(f"✓ All {total_components} components have "
                        f"lastmodified timestamps")

        return missing_lastmodified_count == 0

    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False
    finally:
        if 'client' in locals():
            client.close()


if __name__ == "__main__":
    print("CSC LastModified Timestamp Migration Script")
    print("=" * 50)

    # Confirm with user
    confirm = input(
        "This will update ALL component lastmodified timestamps to the "
        "current time.\n"
        "This may invalidate caches and trigger re-processing.\n"
        "Are you sure you want to continue? (y/n): "
    ).lower().strip()

    if confirm not in ['y', 'yes']:
        print("Migration cancelled by user.")
        sys.exit(0)

    # Run migration
    success = migrate_lastmodified_timestamps()

    if success:
        print("\nMigration completed successfully!")

        # Ask user if they want to verify
        verify = input("\nWould you like to verify the migration? (y/n): "
                       ).lower().strip()
        if verify in ['y', 'yes']:
            verify_migration()
    else:
        print("\nMigration failed. Check the logs for details.")
        sys.exit(1)
