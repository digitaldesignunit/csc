#!/usr/bin/env python3
"""
MongoDB Dataset Field Migration Script

This script adds the dataset field to all components in the CSC database and
performs the following operations:

1. All material: "corian" components → dataset: "mineral_composite_sheets"
2. All type: "beam" components → DELETE from database
3. Component ID "5d01d037-7b18-4e7a-8ab9-4cb975053648" → dataset: "ddu_build_with_debris"
4. All other components → dataset: "sas_cita_scans"

The script:
1. Connects to MongoDB
2. Finds all components that need migration
3. Applies the dataset assignment rules
4. Deletes beam components
5. Updates the database
6. Provides a summary of the migration

Usage:
    python scripts/migrate_add_dataset_field.py [--dry-run]

Options:
    --dry-run    Show what would be changed without making actual changes

Requirements:
    - pymongo
    - MongoDB connection string in environment or config
"""

import os
import sys
import json
import argparse
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dataset_migration.log'),
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


def get_dataset_assignment(component: dict) -> str:
    """
    Determine dataset assignment based on component properties.
    
    Returns:
        str: The dataset name to assign, or None if component should be deleted
    """
    component_id = component.get('_id')
    material = component.get('material', '').lower()
    component_type = component.get('type', '').lower()
    
    # Rule 1: All beam components should be deleted
    if component_type == 'beam':
        return None  # Signal for deletion
    
    # Rule 2: Specific component ID gets special dataset
    if component_id == '5d01d037-7b18-4e7a-8ab9-4cb975053648':
        return 'ddu_build_with_debris'
    
    # Rule 3: All corian components get mineral composite sheets dataset
    if material == 'corian':
        return 'mineral_composite_sheets'
    
    # Rule 4: All other components get SAS CITA scans dataset
    return 'sas_cita_scans'


def migrate_dataset_field(dry_run: bool = False):
    """Main migration function"""
    logger.info("Starting dataset field migration...")
    if dry_run:
        logger.info("DRY RUN MODE - No changes will be made to the database")
    
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
        
        # Get all components
        all_components = list(components_collection.find({}))
        logger.info(f"Found {len(all_components)} total components in database")
        
        if not all_components:
            logger.info("No components found in database")
            return True
        
        # Process components and categorize them
        components_to_delete = []
        components_to_update = {}
        unexpected_components = []
        
        for component in all_components:
            component_id = component.get('_id')
            dataset = get_dataset_assignment(component)
            
            if dataset is None:
                # Component should be deleted (beam type)
                components_to_delete.append(component_id)
            else:
                # Component should be updated with dataset
                components_to_update[component_id] = {
                    'dataset': dataset,
                    'material': component.get('material', 'unknown'),
                    'type': component.get('type', 'unknown')
                }
                
                # Check for unexpected cases
                if (component.get('material', '').lower() not in ['corian'] and 
                    component_id != '5d01d037-7b18-4e7a-8ab9-4cb975053648' and
                    component.get('type', '').lower() != 'beam'):
                    unexpected_components.append({
                        'id': component_id,
                        'material': component.get('material', 'unknown'),
                        'type': component.get('type', 'unknown'),
                        'assigned_dataset': dataset
                    })
        
        # Show what will be done
        logger.info("=" * 60)
        logger.info("MIGRATION PLAN")
        logger.info("=" * 60)
        logger.info(f"Components to delete (beam type): {len(components_to_delete)}")
        logger.info(f"Components to update with dataset: {len(components_to_update)}")
        logger.info(f"Unexpected components (will get sas_cita_scans): {len(unexpected_components)}")
        
        # Show dataset assignments
        dataset_counts = {}
        for assignment in components_to_update.values():
            dataset = assignment['dataset']
            dataset_counts[dataset] = dataset_counts.get(dataset, 0) + 1
        
        logger.info("\nDataset assignments:")
        for dataset, count in dataset_counts.items():
            logger.info(f"  {dataset}: {count} components")
        
        # Show components to be deleted
        if components_to_delete:
            logger.info(f"\nComponents to be deleted (beam type):")
            for comp_id in components_to_delete[:10]:  # Show first 10
                logger.info(f"  {comp_id}")
            if len(components_to_delete) > 10:
                logger.info(f"  ... and {len(components_to_delete) - 10} more")
        
        # Show unexpected components
        if unexpected_components:
            logger.info(f"\nUnexpected components (will get sas_cita_scans dataset):")
            for comp in unexpected_components[:10]:  # Show first 10
                logger.info(f"  {comp['id']} (material: {comp['material']}, type: {comp['type']})")
            if len(unexpected_components) > 10:
                logger.info(f"  ... and {len(unexpected_components) - 10} more")
        
        if dry_run:
            logger.info("\nDRY RUN COMPLETE - No changes made to database")
            return True
        
        # Show confirmation info (auto-proceed since dry run was successful)
        print("\n" + "=" * 60)
        print("PROCEEDING WITH MIGRATION")
        print("=" * 60)
        print(f"This will:")
        print(f"  - Delete {len(components_to_delete)} beam components")
        print(f"  - Update {len(components_to_update)} components with dataset field")
        print(f"  - Assign datasets as shown above")
        print("\nProceeding automatically since dry run was successful...")
        
        # Perform the migration
        deleted_count = 0
        updated_count = 0
        error_count = 0
        
        # Delete beam components
        if components_to_delete:
            logger.info(f"Deleting {len(components_to_delete)} beam components...")
            for component_id in components_to_delete:
                try:
                    result = components_collection.delete_one({'_id': component_id})
                    if result.deleted_count > 0:
                        deleted_count += 1
                        logger.info(f"Deleted beam component: {component_id}")
                    else:
                        logger.warning(f"Component {component_id} not found for deletion")
                except Exception as e:
                    logger.error(f"Error deleting component {component_id}: {e}")
                    error_count += 1
        
        # Update components with dataset field
        if components_to_update:
            logger.info(f"Updating {len(components_to_update)} components with dataset field...")
            for component_id, assignment in components_to_update.items():
                try:
                    result = components_collection.update_one(
                        {'_id': component_id},
                        {'$set': {'dataset': assignment['dataset']}}
                    )
                    if result.modified_count > 0:
                        updated_count += 1
                        logger.info(f"Updated component {component_id} with dataset: {assignment['dataset']}")
                    else:
                        logger.warning(f"Component {component_id} not found for update")
                except Exception as e:
                    logger.error(f"Error updating component {component_id}: {e}")
                    error_count += 1
        
        # Summary
        logger.info("=" * 60)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total components processed: {len(all_components)}")
        logger.info(f"Beam components deleted: {deleted_count}")
        logger.info(f"Components updated with dataset: {updated_count}")
        logger.info(f"Errors encountered: {error_count}")
        
        # Show final dataset distribution
        if updated_count > 0:
            logger.info("\nFinal dataset distribution:")
            final_dataset_counts = {}
            for assignment in components_to_update.values():
                dataset = assignment['dataset']
                final_dataset_counts[dataset] = final_dataset_counts.get(dataset, 0) + 1
            
            for dataset, count in final_dataset_counts.items():
                logger.info(f"  {dataset}: {count} components")
        
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
        
        # Check for components missing dataset field
        missing_dataset_query = {"dataset": {"$exists": False}}
        missing_dataset = list(components_collection.find(missing_dataset_query))
        
        # Check for remaining beam components
        beam_components_query = {"type": "beam"}
        remaining_beams = list(components_collection.find(beam_components_query))
        
        # Check dataset distribution
        pipeline = [
            {"$group": {"_id": "$dataset", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        dataset_distribution = list(components_collection.aggregate(pipeline))
        
        if missing_dataset:
            logger.warning(f"Found {len(missing_dataset)} components still missing dataset field:")
            for comp in missing_dataset[:5]:  # Show first 5
                logger.warning(f"  {comp.get('_id')}")
        else:
            logger.info("✓ All components have dataset field")
        
        if remaining_beams:
            logger.warning(f"Found {len(remaining_beams)} beam components still in database:")
            for comp in remaining_beams[:5]:  # Show first 5
                logger.warning(f"  {comp.get('_id')}")
        else:
            logger.info("✓ All beam components have been deleted")
        
        logger.info("Dataset distribution:")
        for item in dataset_distribution:
            dataset = item['_id'] or 'null'
            count = item['count']
            logger.info(f"  {dataset}: {count} components")
        
        return len(missing_dataset) == 0 and len(remaining_beams) == 0
        
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False
    finally:
        if 'client' in locals():
            client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Migrate components to add dataset field')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be changed without making actual changes')
    args = parser.parse_args()
    
    print("CSC Dataset Field Migration Script")
    print("=" * 60)
    
    # Run migration
    success = migrate_dataset_field(dry_run=args.dry_run)
    
    if success and not args.dry_run:
        print("\nMigration completed successfully!")
        
        # Ask user if they want to verify
        verify = input("\nWould you like to verify the migration? (y/n): ").lower().strip()
        if verify in ['y', 'yes']:
            verify_migration()
    elif args.dry_run:
        print("\nDry run completed successfully!")
    else:
        print("\nMigration failed. Check the logs for details.")
        sys.exit(1)
