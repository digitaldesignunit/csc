#!/usr/bin/env python3
"""
MongoDB Fragment Field Boolean Migration Script

This script ensures the 'fragment' field is a boolean for all components in the CSC database.
It handles various data types that might be stored in the fragment field and converts them
to proper boolean values.

The script:
1. Connects to MongoDB
2. Finds all components with non-boolean fragment field values
3. Converts them to proper boolean values based on common patterns
4. Updates the database
5. Provides a summary of the migration

Usage:
    python scripts/migrate_fragment_boolean.py

Requirements:
    - pymongo
    - MongoDB connection string in environment or config
"""

import os
import sys
import json
from typing import Any, Union
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('fragment_boolean_migration.log'),
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


def convert_to_boolean(value: Any) -> bool:
    """
    Convert various data types to boolean following common patterns.
    
    Args:
        value: The value to convert to boolean
        
    Returns:
        bool: The converted boolean value
    """
    if isinstance(value, bool):
        return value
    
    if isinstance(value, str):
        # String values
        value_lower = value.lower().strip()
        if value_lower in ['true', '1', 'yes', 'y', 'on']:
            return True
        elif value_lower in ['false', '0', 'no', 'n', 'off', '']:
            return False
        else:
            # Non-empty string is considered True
            logger.warning(f"Unknown string value '{value}', treating as True")
            return True
    
    if isinstance(value, (int, float)):
        # Numeric values: 0 is False, anything else is True
        return bool(value)
    
    if value is None:
        # None/null values default to False
        return False
    
    if isinstance(value, list):
        # List values: empty list is False, non-empty is True
        return len(value) > 0
    
    if isinstance(value, dict):
        # Dict values: empty dict is False, non-empty is True
        return len(value) > 0
    
    # For any other type, convert to string and check
    try:
        str_value = str(value).lower().strip()
        if str_value in ['true', '1', 'yes', 'y', 'on']:
            return True
        elif str_value in ['false', '0', 'no', 'n', 'off', '']:
            return False
        else:
            # Non-empty string representation is considered True
            logger.warning(f"Unknown value type '{type(value).__name__}' with value '{value}', treating as True")
            return True
    except Exception as e:
        logger.error(f"Error converting value '{value}' to boolean: {e}")
        return False


def migrate_fragment_boolean():
    """Main migration function"""
    logger.info("Starting fragment field boolean migration...")
    
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
        
        # Find all components with fragment field that is not a boolean
        migration_query = {
            "fragment": {"$exists": True, "$not": {"$type": "bool"}}
        }

        components_to_migrate = list(
            components_collection.find(migration_query)
        )
        logger.info(
            f"Found {len(components_to_migrate)} components with non-boolean "
            f"fragment field"
        )

        if not components_to_migrate:
            logger.info(
                "No components need migration. All components already have "
                "boolean fragment field values."
            )
            return True

        # Process each component
        migrated_count = 0
        skipped_count = 0
        error_count = 0
        conversion_stats = {}

        for component in components_to_migrate:
            try:
                component_id = component.get('_id')
                current_value = component.get('fragment')
                current_type = type(current_value).__name__
                
                # Convert to boolean
                boolean_value = convert_to_boolean(current_value)
                
                # Track conversion statistics
                conversion_key = f"{current_type} -> {boolean_value}"
                conversion_stats[conversion_key] = conversion_stats.get(conversion_key, 0) + 1
                
                # Update the component
                result = components_collection.update_one(
                    {'_id': component_id},
                    {'$set': {'fragment': boolean_value}}
                )

                if result.modified_count > 0:
                    migrated_count += 1
                    logger.info(
                        f"Successfully migrated component {component_id}: "
                        f"'{current_value}' ({current_type}) -> {boolean_value} (bool)"
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
        logger.info("=" * 60)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total components found with non-boolean fragment: {len(components_to_migrate)}")
        logger.info(f"Successfully migrated: {migrated_count}")
        logger.info(f"Skipped: {skipped_count}")
        logger.info(f"Errors: {error_count}")
        logger.info("")
        logger.info("CONVERSION STATISTICS:")
        for conversion, count in conversion_stats.items():
            logger.info(f"  {conversion}: {count} components")
        logger.info("=" * 60)
        
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
        
        # Check for components with fragment field
        has_fragment_query = {"fragment": {"$exists": True}}
        has_fragment_count = components_collection.count_documents(has_fragment_query)
        
        # Check for components with boolean fragment field
        boolean_fragment_query = {"fragment": {"$type": "bool"}}
        boolean_fragment_count = components_collection.count_documents(boolean_fragment_query)
        
        # Check for components with non-boolean fragment field (should be 0)
        non_boolean_fragment_query = {
            "fragment": {"$exists": True, "$not": {"$type": "bool"}}
        }
        non_boolean_fragment_count = components_collection.count_documents(non_boolean_fragment_query)
        
        # Check for components with True fragment
        true_fragment_query = {"fragment": True}
        true_fragment_count = components_collection.count_documents(true_fragment_query)
        
        # Check for components with False fragment
        false_fragment_query = {"fragment": False}
        false_fragment_count = components_collection.count_documents(false_fragment_query)
        
        # Total components
        total_components = components_collection.count_documents({})
        
        logger.info("=" * 50)
        logger.info("VERIFICATION RESULTS")
        logger.info("=" * 50)
        logger.info(f"Total components: {total_components}")
        logger.info(f"Components with fragment field: {has_fragment_count}")
        logger.info(f"Components with boolean fragment: {boolean_fragment_count}")
        logger.info(f"Components with non-boolean fragment: {non_boolean_fragment_count}")
        logger.info(f"Components with fragment=True: {true_fragment_count}")
        logger.info(f"Components with fragment=False: {false_fragment_count}")
        logger.info("=" * 50)
        
        if non_boolean_fragment_count == 0:
            logger.info("✓ All components with fragment field have boolean values")
        else:
            logger.warning(f"⚠ Found {non_boolean_fragment_count} components still with non-boolean fragment field")
        
        if boolean_fragment_count > 0:
            logger.info(f"✓ {boolean_fragment_count} components now have boolean fragment field")
        
        return non_boolean_fragment_count == 0
        
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False
    finally:
        if 'client' in locals():
            client.close()


if __name__ == "__main__":
    print("CSC Fragment Field Boolean Migration Script")
    print("=" * 50)
    
    # Run migration
    success = migrate_fragment_boolean()
    
    if success:
        print("\nMigration completed successfully!")
        
        # Ask user if they want to verify
        verify = input("\nWould you like to verify the migration? (y/n): ").lower().strip()
        if verify in ['y', 'yes']:
            verify_migration()
    else:
        print("\nMigration failed. Check the logs for details.")
        sys.exit(1)
