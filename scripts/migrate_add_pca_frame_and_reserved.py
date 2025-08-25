#!/usr/bin/env python3
"""
MongoDB PCA Frame and Reserved Properties Migration Script

This script adds two new properties to all components in the CSC database:
1. pca_frame: PCA transformation matrix (identical to iframe for now)
2. reserved: UUID of user who has reserved the component (empty for now)

The script:
1. Connects to MongoDB
2. Finds all components that don't have these properties
3. Adds the properties with default values
4. Updates the database
5. Provides a summary of the migration

Usage:
    python scripts/migrate_add_pca_frame_and_reserved.py

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
        logging.FileHandler('pca_frame_migration.log'),
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


def get_default_pca_frame() -> dict:
    """Get the default PCA frame structure (identical to iframe)"""
    return {
        "o": [0, 0, 0],      # origin
        "x": [1, 0, 0],      # x-axis
        "y": [0, 1, 0],      # y-axis
        "z": [0, 0, 1]       # z-axis
    }


def migrate_pca_frame_and_reserved():
    """Main migration function"""
    logger.info("Starting PCA frame and reserved properties migration...")
    
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
        
        # Find all components that need migration (missing pca_frame or reserved)
        migration_query = {
            "$or": [
                {"pca_frame": {"$exists": False}},
                {"reserved": {"$exists": False}}
            ]
        }

        components_to_migrate = list(
            components_collection.find(migration_query)
        )
        logger.info(
            f"Found {len(components_to_migrate)} components that need migration"
        )

        if not components_to_migrate:
            logger.info(
                "No components need migration. All components already have "
                "pca_frame and reserved properties."
            )
            return True

        # Process each component
        migrated_count = 0
        skipped_count = 0
        error_count = 0

        for component in components_to_migrate:
            try:
                component_id = component.get('_id')
                updates = {}

                # Check and add pca_frame if missing
                if 'pca_frame' not in component:
                    # Use iframe if available, otherwise use default
                    if component.get('iframe'):
                        updates['pca_frame'] = component['iframe']
                        logger.info(
                            f"Component {component_id}: Using iframe as pca_frame"
                        )
                    else:
                        updates['pca_frame'] = get_default_pca_frame()
                        logger.info(
                            f"Component {component_id}: Added default pca_frame"
                        )

                # Check and add reserved if missing
                if 'reserved' not in component:
                    updates['reserved'] = None  # Empty (not reserved)
                    logger.info(
                        f"Component {component_id}: Added empty reserved property"
                    )

                # Update the component if there are changes
                if updates:
                    result = components_collection.update_one(
                        {'_id': component_id},
                        {'$set': updates}
                    )

                    if result.modified_count > 0:
                        migrated_count += 1
                        logger.info(
                            f"Successfully migrated component {component_id}"
                        )
                    else:
                        logger.warning(
                            f"Component {component_id}: No changes made"
                        )
                        skipped_count += 1
                else:
                    logger.info(
                        f"Component {component_id}: No migration needed"
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
        
        # Check for components missing pca_frame
        missing_pca_frame_query = {"pca_frame": {"$exists": False}}
        missing_pca_frame = list(components_collection.find(missing_pca_frame_query))
        
        # Check for components missing reserved
        missing_reserved_query = {"reserved": {"$exists": False}}
        missing_reserved = list(components_collection.find(missing_reserved_query))
        
        # Check for components with pca_frame
        has_pca_frame_query = {"pca_frame": {"$exists": True}}
        has_pca_frame_count = components_collection.count_documents(has_pca_frame_query)
        
        # Check for components with reserved
        has_reserved_query = {"reserved": {"$exists": True}}
        has_reserved_count = components_collection.count_documents(has_reserved_query)
        
        # Check for components with non-null reserved (actually reserved)
        reserved_components_query = {"reserved": {"$ne": None}}
        reserved_components_count = components_collection.count_documents(reserved_components_query)
        
        if missing_pca_frame:
            logger.warning(f"Found {len(missing_pca_frame)} components still missing pca_frame:")
            for comp in missing_pca_frame[:3]:  # Show first 3
                logger.warning(f"  {comp.get('_id')}")
        else:
            logger.info("✓ All components have pca_frame property")
        
        if missing_reserved:
            logger.warning(f"Found {len(missing_reserved)} components still missing reserved property:")
            for comp in missing_reserved[:3]:  # Show first 3
                logger.warning(f"  {comp.get('_id')}")
        else:
            logger.info("✓ All components have reserved property")
        
        logger.info(f"✓ {has_pca_frame_count} components have pca_frame property")
        logger.info(f"✓ {has_reserved_count} components have reserved property")
        logger.info(f"✓ {reserved_components_count} components are actually reserved (non-null)")
        
        return len(missing_pca_frame) == 0 and len(missing_reserved) == 0
        
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False
    finally:
        if 'client' in locals():
            client.close()


if __name__ == "__main__":
    print("CSC PCA Frame and Reserved Properties Migration Script")
    print("=" * 60)
    
    # Run migration
    success = migrate_pca_frame_and_reserved()
    
    if success:
        print("\nMigration completed successfully!")
        
        # Ask user if they want to verify
        verify = input("\nWould you like to verify the migration? (y/n): ").lower().strip()
        if verify in ['y', 'yes']:
            verify_migration()
    else:
        print("\nMigration failed. Check the logs for details.")
        sys.exit(1)
