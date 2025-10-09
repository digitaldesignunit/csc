#!/usr/bin/env python3
"""
Migration script to add bbx_origin field to all components in MongoDB.

This script adds a new 'bbx_origin' field to every component in the database
with a placeholder value of [0, 0, 0]. This field will store the center of
the bounding box in PCA coordinate space.

Usage:
    python migrate_add_bbx_origin_field.py [--dry-run]

Author: AI Assistant
Date: 2025-01-09
"""

import argparse
import logging
import sys
from datetime import datetime
from typing import List, Dict, Any

# MongoDB imports
try:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
except ImportError:
    print("Error: pymongo not installed. Please install with: pip install pymongo")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migrate_bbx_origin.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load MongoDB configuration from environment or config file."""
    import os
    import json
    
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
                user = config.get('user')
                pwd = config.get('pwd')
                db = config.get('db')
                
                if all([server, user, pwd, db]):
                    uri = f"mongodb+srv://{user}:{pwd}@{server}/{db}?retryWrites=true&w=majority"
                    return {'uri': uri, 'database': db, 'collection': 'components'}
                else:
                    logger.error("Missing required config fields")
                    return None
        except Exception as e:
            logger.error(f"Failed to load config file: {e}")
            return None
    
    return None


def connect_to_mongodb(config: Dict[str, str]):
    """Connect to MongoDB and return client and collection."""
    try:
        client = MongoClient(config['uri'])
        
        # Get database - try default first, then extract from URI
        db = client.get_default_database()
        if db is None:
            # Try to get database from URI
            db_name = config['uri'].split('/')[-1].split('?')[0]
            db = client[db_name]
        
        collection = db[config['collection']]
        
        # Test connection
        client.admin.command('ping')
        logger.info(f"Successfully connected to MongoDB: {db.name}.{config['collection']}")
        
        return client, collection
    except PyMongoError as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        sys.exit(1)


def get_components_to_update(collection) -> List[Dict[str, Any]]:
    """Get all components that need the bbx_origin field added."""
    try:
        # Find components that don't have bbx_origin field
        query = {"bbx_origin": {"$exists": False}}
        components = list(collection.find(query))
        
        logger.info(f"Found {len(components)} components without bbx_origin field")
        return components
    except PyMongoError as e:
        logger.error(f"Error querying components: {e}")
        sys.exit(1)


def migrate_components(collection, components: List[Dict[str, Any]], dry_run: bool = False) -> Dict[str, int]:
    """Migrate components by adding bbx_origin field."""
    stats = {
        'total_processed': 0,
        'successful_updates': 0,
        'errors': 0,
        'skipped': 0
    }
    
    # Default placeholder value
    bbx_origin_placeholder = [0.0, 0.0, 0.0]
    
    logger.info(f"Starting migration of {len(components)} components...")
    if dry_run:
        logger.info("DRY RUN MODE - No changes will be made to the database")
    
    for i, component in enumerate(components):
        component_id = component.get('_id', 'unknown')
        stats['total_processed'] += 1
        
        try:
            if dry_run:
                logger.info(f"[DRY RUN] Would add bbx_origin to component {component_id}")
                stats['successful_updates'] += 1
            else:
                # Add bbx_origin field
                result = collection.update_one(
                    {"_id": component_id},
                    {
                        "$set": {
                            "bbx_origin": bbx_origin_placeholder,
                            "lastmodified": datetime.utcnow().isoformat() + "Z"
                        }
                    }
                )
                
                if result.modified_count == 1:
                    stats['successful_updates'] += 1
                    if (i + 1) % 100 == 0:  # Log progress every 100 components
                        logger.info(f"Processed {i + 1}/{len(components)} components")
                else:
                    logger.warning(f"No changes made to component {component_id}")
                    stats['skipped'] += 1
                    
        except PyMongoError as e:
            logger.error(f"Error updating component {component_id}: {e}")
            stats['errors'] += 1
        except Exception as e:
            logger.error(f"Unexpected error processing component {component_id}: {e}")
            stats['errors'] += 1
    
    return stats


def verify_migration(collection) -> Dict[str, int]:
    """Verify the migration by checking field presence."""
    try:
        # Count components with bbx_origin field
        with_bbx_origin = collection.count_documents({"bbx_origin": {"$exists": True}})
        total_components = collection.count_documents({})
        without_bbx_origin = total_components - with_bbx_origin
        
        return {
            'total_components': total_components,
            'with_bbx_origin': with_bbx_origin,
            'without_bbx_origin': without_bbx_origin
        }
    except PyMongoError as e:
        logger.error(f"Error verifying migration: {e}")
        return {}


def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(description='Add bbx_origin field to MongoDB components')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Perform a dry run without making changes')
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("MONGODB COMPONENT MIGRATION: Add bbx_origin field")
    logger.info("=" * 60)
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info(f"Dry run: {args.dry_run}")
    
    # Load configuration
    config = load_config()
    if not config:
        logger.error("Failed to load MongoDB configuration")
        return
    
    logger.info(f"Database: {config['database']}")
    logger.info(f"Collection: {config['collection']}")
    
    # Connect to MongoDB
    client, collection = connect_to_mongodb(config)
    
    try:
        # Get components to update
        components = get_components_to_update(collection)
        
        if not components:
            logger.info("No components need migration. All components already have bbx_origin field.")
            return
        
        # Show migration plan
        logger.info("\n" + "=" * 60)
        logger.info("MIGRATION PLAN")
        logger.info("=" * 60)
        logger.info(f"Components to update: {len(components)}")
        logger.info(f"Field to add: bbx_origin = [0.0, 0.0, 0.0] (placeholder)")
        logger.info(f"Also update: lastmodified timestamp")
        
        if args.dry_run:
            logger.info("\nDRY RUN COMPLETE - No changes made to database")
            return
        
        # Show confirmation info (auto-proceed since this is a safe migration)
        print("\n" + "=" * 60)
        print("PROCEEDING WITH MIGRATION")
        print("=" * 60)
        print(f"This will:")
        print(f"  - Add bbx_origin field to {len(components)} components")
        print(f"  - Set bbx_origin to [0.0, 0.0, 0.0] as placeholder")
        print(f"  - Update lastmodified timestamp for each component")
        print("\nProceeding automatically...")
        
        # Perform the migration
        stats = migrate_components(collection, components, dry_run=args.dry_run)
        
        # Show results
        logger.info("\n" + "=" * 60)
        logger.info("MIGRATION RESULTS")
        logger.info("=" * 60)
        logger.info(f"Total processed: {stats['total_processed']}")
        logger.info(f"Successful updates: {stats['successful_updates']}")
        logger.info(f"Errors: {stats['errors']}")
        logger.info(f"Skipped: {stats['skipped']}")
        
        # Verify migration
        logger.info("\nVerifying migration...")
        verification = verify_migration(collection)
        if verification:
            logger.info(f"Total components in database: {verification['total_components']}")
            logger.info(f"Components with bbx_origin: {verification['with_bbx_origin']}")
            logger.info(f"Components without bbx_origin: {verification['without_bbx_origin']}")
            
            if verification['without_bbx_origin'] == 0:
                logger.info("✅ Migration completed successfully!")
            else:
                logger.warning(f"⚠️  {verification['without_bbx_origin']} components still missing bbx_origin field")
        
    except KeyboardInterrupt:
        logger.info("\nMigration interrupted by user")
    except Exception as e:
        logger.error(f"Migration failed with error: {e}")
        sys.exit(1)
    finally:
        client.close()
        logger.info("MongoDB connection closed")


if __name__ == "__main__":
    main()

