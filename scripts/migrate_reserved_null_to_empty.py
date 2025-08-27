#!/usr/bin/env python3
"""
MongoDB Reserved Field Migration Script

This script changes the "reserved" field from null to empty string for all
components in the CSC database. Currently, components that are not reserved
have a null value for the reserved field, but we want them to have an empty
string instead.

The script:
1. Connects to MongoDB
2. Finds all components with reserved field set to null
3. Updates them to have an empty string instead
4. Provides a summary of the migration

Usage:
    python scripts/migrate_reserved_null_to_empty.py

Requirements:
    - pymongo
    - MongoDB connection string in environment or config
"""

import os
import sys
import json
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('reserved_null_to_empty_migration.log'),
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


def migrate_reserved_null_to_empty():
    """Main migration function"""
    logger.info("Starting reserved field null to empty string migration...")
    
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
        
        # Find all components with reserved field set to null
        migration_query = {"reserved": None}

        components_to_migrate = list(
            components_collection.find(migration_query)
        )
        logger.info(
            f"Found {len(components_to_migrate)} components with null "
            f"reserved field"
        )

        if not components_to_migrate:
            logger.info(
                "No components need migration. All components already have "
                "non-null reserved field values."
            )
            return True

        # Process each component
        migrated_count = 0
        skipped_count = 0
        error_count = 0

        for component in components_to_migrate:
            try:
                component_id = component.get('_id')
                
                # Update the component to set reserved to empty string
                result = components_collection.update_one(
                    {'_id': component_id},
                    {'$set': {'reserved': ''}}
                )

                if result.modified_count > 0:
                    migrated_count += 1
                    logger.info(
                        f"Successfully migrated component {component_id}: "
                        f"null -> empty string"
                    )
                else:
                    logger.warning(
                        f"Component {component_id}: No changes made"
                    )
                    skipped_count += 1

            except Exception as e:
                logger.error(
                    f"Error processing component "
                    f"{component.get('_id', 'unknown')}: {e}"
                )
                error_count += 1
        
        # Summary
        logger.info("=" * 50)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 50)
        logger.info(f"Total components found with null reserved: {len(components_to_migrate)}")
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
        
        # Check for components with null reserved field (should be 0)
        null_reserved_query = {"reserved": None}
        null_reserved_count = components_collection.count_documents(null_reserved_query)
        
        # Check for components with empty string reserved field
        empty_reserved_query = {"reserved": ""}
        empty_reserved_count = components_collection.count_documents(empty_reserved_query)
        
        # Check for components with non-empty reserved field (actually reserved)
        reserved_components_query = {
            "$and": [
                {"reserved": {"$ne": ""}},
                {"reserved": {"$ne": None}}
            ]
        }
        reserved_components_count = components_collection.count_documents(
            reserved_components_query
        )
        
        # Check for components with reserved field (any value)
        has_reserved_query = {"reserved": {"$exists": True}}
        has_reserved_count = components_collection.count_documents(has_reserved_query)
        
        # Total components
        total_components = components_collection.count_documents({})
        
        logger.info("=" * 50)
        logger.info("VERIFICATION RESULTS")
        logger.info("=" * 50)
        logger.info(f"Total components: {total_components}")
        logger.info(f"Components with reserved field: {has_reserved_count}")
        logger.info(f"Components with null reserved: {null_reserved_count}")
        logger.info(f"Components with empty string reserved: {empty_reserved_count}")
        logger.info(f"Components actually reserved: {reserved_components_count}")
        logger.info("=" * 50)
        
        if null_reserved_count == 0:
            logger.info("✓ All components have non-null reserved field values")
        else:
            logger.warning(f"⚠ Found {null_reserved_count} components still with null reserved field")
        
        if empty_reserved_count > 0:
            logger.info(f"✓ {empty_reserved_count} components now have empty string reserved field")
        
        if reserved_components_count > 0:
            logger.info(f"✓ {reserved_components_count} components are actually reserved")
        
        return null_reserved_count == 0
        
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False
    finally:
        if 'client' in locals():
            client.close()


if __name__ == "__main__":
    print("CSC Reserved Field Null to Empty String Migration Script")
    print("=" * 65)
    
    # Run migration
    success = migrate_reserved_null_to_empty()
    
    if success:
        print("\nMigration completed successfully!")
        
        # Ask user if they want to verify
        verify = input("\nWould you like to verify the migration? (y/n): ").lower().strip()
        if verify in ['y', 'yes']:
            verify_migration()
    else:
        print("\nMigration failed. Check the logs for details.")
        sys.exit(1)
