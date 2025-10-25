#!/usr/bin/env python3
"""
MongoDB Marker Points and Multi-Mesh Migration Script

This script performs a comprehensive migration of the CSC database:

1. Adds 'marker_points' field to all components (empty list as default)
2. Migrates single-mesh components to multi-mesh format
3. Validates all components against ComponentModel schema
4. Reports inconsistencies and fixes them where possible

The script:
1. Connects to MongoDB
2. Finds all components that need migration
3. Adds marker_points field with empty list default
4. Converts single mesh geometry to multi-mesh format
5. Validates components against the current schema
6. Reports and optionally fixes inconsistencies
7. Provides a comprehensive summary

Usage:
    python scripts/migrate_marker_points_and_multi_mesh.py

Requirements:
    - pymongo
    - MongoDB connection string in environment or config
"""

import os
import sys
import json
from typing import List, Dict, Any, Optional
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
        logging.FileHandler('marker_points_multi_mesh_migration.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def load_config() -> Optional[Dict[str, str]]:
    """Load MongoDB configuration from environment or config file"""
    # Try to load from environment variables first
    mongo_uri = os.getenv('MONGO_URI')
    if mongo_uri:
        return {'uri': mongo_uri}
    
    # Try to load from config file
    config_path = os.path.normpath(os.path.abspath(
        os.path.join('..', 'src', 'backend', 'config', 'dbconfig.json')
    ))
    logger.info(f"Config path: {config_path}")
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


def validate_component_schema(component: Dict[str, Any]) -> List[str]:
    """Validate a component against the ComponentModel schema"""
    errors = []
    
    # Required fields
    required_fields = [
        '_id', 'created', 'lastmodified', 'type', 'material', 
        'complexity', 'fragment', 'assembly', 'geometry', 
        'bbx', 'iframe', 'pca_frame', 'reserved', 'validated'
    ]
    
    for field in required_fields:
        if field not in component:
            errors.append(f"Missing required field: {field}")
    
    # Validate field types
    if 'complexity' in component and not isinstance(component['complexity'], int):
        errors.append("Field 'complexity' must be an integer")
    
    if 'fragment' in component and not isinstance(component['fragment'], bool):
        errors.append("Field 'fragment' must be a boolean")
    
    if 'assembly' in component and not isinstance(component['assembly'], bool):
        errors.append("Field 'assembly' must be a boolean")
    
    if 'validated' in component and not isinstance(component['validated'], bool):
        errors.append("Field 'validated' must be a boolean")
    
    # Validate geometry structure
    if 'geometry' in component:
        geometry = component['geometry']
        if not isinstance(geometry, dict):
            errors.append("Field 'geometry' must be an object")
        else:
            # Check for both mesh and meshes (should not have both)
            if 'mesh' in geometry and 'meshes' in geometry:
                errors.append("Geometry cannot have both 'mesh' and 'meshes' fields")
    
    # Validate bounding box format
    if 'bbx' in component:
        bbx = component['bbx']
        if isinstance(bbx, list) and len(bbx) == 3:
            if not all(isinstance(x, (int, float)) for x in bbx):
                errors.append("Bounding box must contain numeric values")
        else:
            errors.append("Bounding box must be a list of 3 numbers [X, Y, Z]")
    
    # Validate color format
    if 'color' in component:
        color = component['color']
        if isinstance(color, list) and len(color) == 3:
            if not all(isinstance(c, int) and 0 <= c <= 255 for c in color):
                errors.append("Color must be [R, G, B] integers (0-255)")
        else:
            errors.append("Color must be a list of 3 integers [R, G, B]")
    
    # Validate marker_points format
    if 'marker_points' in component:
        marker_points = component['marker_points']
        if not isinstance(marker_points, list):
            errors.append("Marker points must be a list")
        else:
            for i, point in enumerate(marker_points):
                if not isinstance(point, list) or len(point) != 3:
                    errors.append(f"Marker point {i} must be [x, y, z] coordinate triplet")
                elif not all(isinstance(coord, (int, float)) for coord in point):
                    errors.append(f"Marker point {i} must contain numeric coordinates")
    
    return errors


def convert_single_mesh_to_multi_mesh(geometry: Dict[str, Any]) -> Dict[str, Any]:
    """Convert single mesh geometry to multi-mesh format"""
    if 'mesh' in geometry and 'meshes' not in geometry:
        # Move single mesh to meshes array
        single_mesh = geometry['mesh']
        geometry['meshes'] = [single_mesh]
        del geometry['mesh']
        logger.info("Converted single mesh to multi-mesh format")
    return geometry


def migrate_component(component: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate a single component"""
    updates = {}
    component_id = component.get('_id', 'unknown')
    
    # Add marker_points if missing
    if 'marker_points' not in component:
        updates['marker_points'] = []
        logger.info(f"Component {component_id}: Added marker_points field")
    
    # Convert single mesh to multi-mesh if needed
    if 'geometry' in component:
        geometry = component['geometry']
        if isinstance(geometry, dict):
            # Check if it has single mesh but no meshes
            if 'mesh' in geometry and 'meshes' not in geometry:
                updated_geometry = convert_single_mesh_to_multi_mesh(geometry)
                updates['geometry'] = updated_geometry
                logger.info(f"Component {component_id}: Converted to multi-mesh format")
    
    return updates


def fix_common_issues(component: Dict[str, Any]) -> Dict[str, Any]:
    """Fix common schema issues in a component"""
    fixes = {}
    component_id = component.get('_id', 'unknown')
    
    # Fix missing validated field
    if 'validated' not in component:
        fixes['validated'] = False
        logger.info(f"Component {component_id}: Added missing 'validated' field")
    
    # Fix missing reserved field
    if 'reserved' not in component:
        fixes['reserved'] = ''
        logger.info(f"Component {component_id}: Added missing 'reserved' field")
    
    # Fix missing pca_frame field
    if 'pca_frame' not in component:
        if 'iframe' in component:
            fixes['pca_frame'] = component['iframe']
            logger.info(f"Component {component_id}: Used iframe as pca_frame")
        else:
            fixes['pca_frame'] = {
                'o': [0.0, 0.0, 0.0],
                'x': [1.0, 0.0, 0.0],
                'y': [0.0, 1.0, 0.0],
                'z': [0.0, 0.0, 1.0]
            }
            logger.info(f"Component {component_id}: Added default pca_frame")
    
    # Fix color format if needed
    if 'color' in component:
        color = component['color']
        if isinstance(color, list) and len(color) == 3:
            # Ensure all values are integers in 0-255 range
            fixed_color = []
            for c in color:
                if isinstance(c, float):
                    c = int(c)
                c = max(0, min(255, c))
                fixed_color.append(c)
            if fixed_color != color:
                fixes['color'] = fixed_color
                logger.info(f"Component {component_id}: Fixed color format")
    
    return fixes


def migrate_database():
    """Main migration function"""
    logger.info("Starting marker points and multi-mesh migration...")
    
    # Load configuration
    config = load_config()
    if not config:
        logger.error("Failed to load MongoDB configuration")
        return False
    
    try:
        # Connect to MongoDB
        client = MongoClient(config['uri'])
        
        # Get database
        db = client.get_default_database()
        if db is None:
            db_name = config['uri'].split('/')[-1].split('?')[0]
            db = client[db_name]
        
        components_collection = db.components
        
        logger.info(f"Connected to database: {db.name}")
        logger.info(f"Collection: {components_collection.name}")
        
        # Get total count
        total_components = components_collection.count_documents({})
        logger.info(f"Total components in database: {total_components}")
        
        # Find components that need migration
        migration_query = {
            "$or": [
                {"marker_points": {"$exists": False}},
                {"geometry.mesh": {"$exists": True}, "geometry.meshes": {"$exists": False}}
            ]
        }
        
        components_to_migrate = list(components_collection.find(migration_query))
        logger.info(f"Found {len(components_to_migrate)} components that need migration")
        
        if not components_to_migrate:
            logger.info("No components need migration.")
        else:
            # Process each component
            migrated_count = 0
            error_count = 0
            
            for component in components_to_migrate:
                try:
                    component_id = component.get('_id')
                    updates = migrate_component(component)
                    
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
                    else:
                        logger.info(f"Component {component_id}: No migration needed")
                        
                except Exception as e:
                    logger.error(f"Error migrating component {component.get('_id', 'unknown')}: {e}")
                    error_count += 1
            
            logger.info(f"Migration completed: {migrated_count} migrated, {error_count} errors")
        
        # Validate all components
        logger.info("Starting component validation...")
        validation_errors = []
        components_with_errors = 0
        fixed_components = 0
        
        for component in components_collection.find({}):
            try:
                errors = validate_component_schema(component)
                if errors:
                    components_with_errors += 1
                    component_id = component.get('_id', 'unknown')
                    logger.warning(f"Component {component_id} has {len(errors)} validation errors:")
                    for error in errors:
                        logger.warning(f"  - {error}")
                        validation_errors.append(f"{component_id}: {error}")
                    
                    # Try to fix common issues
                    fixes = fix_common_issues(component)
                    if fixes:
                        result = components_collection.update_one(
                            {'_id': component_id},
                            {'$set': fixes}
                        )
                        if result.modified_count > 0:
                            fixed_components += 1
                            logger.info(f"Fixed {len(fixes)} issues in component {component_id}")
                            
            except Exception as e:
                logger.error(f"Error validating component {component.get('_id', 'unknown')}: {e}")
        
        # Final validation
        logger.info("Running final validation...")
        final_errors = []
        for component in components_collection.find({}):
            try:
                errors = validate_component_schema(component)
                if errors:
                    final_errors.extend([f"{component.get('_id', 'unknown')}: {error}" for error in errors])
            except Exception as e:
                logger.error(f"Error in final validation: {e}")
        
        # Summary
        logger.info("=" * 60)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total components: {total_components}")
        logger.info(f"Components migrated: {migrated_count}")
        logger.info(f"Components with validation errors: {components_with_errors}")
        logger.info(f"Components fixed: {fixed_components}")
        logger.info(f"Remaining validation errors: {len(final_errors)}")
        logger.info("=" * 60)
        
        if final_errors:
            logger.warning("Remaining validation errors:")
            for error in final_errors[:10]:  # Show first 10
                logger.warning(f"  {error}")
            if len(final_errors) > 10:
                logger.warning(f"  ... and {len(final_errors) - 10} more errors")
        
        return len(final_errors) == 0
        
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
        
        db = client.get_default_database()
        if db is None:
            db_name = config['uri'].split('/')[-1].split('?')[0]
            db = client[db_name]
        
        components_collection = db.components
        
        # Check marker_points field
        missing_marker_points = components_collection.count_documents(
            {"marker_points": {"$exists": False}}
        )
        has_marker_points = components_collection.count_documents(
            {"marker_points": {"$exists": True}}
        )
        
        # Check multi-mesh format
        single_mesh_components = components_collection.count_documents(
            {"geometry.mesh": {"$exists": True}, "geometry.meshes": {"$exists": False}}
        )
        multi_mesh_components = components_collection.count_documents(
            {"geometry.meshes": {"$exists": True}}
        )
        
        # Check for both mesh and meshes (invalid)
        both_mesh_fields = components_collection.count_documents(
            {"geometry.mesh": {"$exists": True}, "geometry.meshes": {"$exists": True}}
        )
        
        logger.info(f"✓ {has_marker_points} components have marker_points field")
        logger.info(f"✓ {multi_mesh_components} components use multi-mesh format")
        logger.info(f"⚠ {single_mesh_components} components still use single-mesh format")
        logger.info(f"⚠ {both_mesh_fields} components have both mesh and meshes (invalid)")
        
        if missing_marker_points > 0:
            logger.warning(f"✗ {missing_marker_points} components missing marker_points field")
        
        return missing_marker_points == 0 and both_mesh_fields == 0
        
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False
    finally:
        if 'client' in locals():
            client.close()


if __name__ == "__main__":
    print("CSC Marker Points and Multi-Mesh Migration Script")
    print("=" * 60)
    
    # Run migration
    success = migrate_database()
    
    if success:
        print("\nMigration completed successfully!")
        
        # Ask user if they want to verify
        verify = input("\nWould you like to verify the migration? (y/n): ").lower().strip()
        if verify in ['y', 'yes']:
            verify_migration()
    else:
        print("\nMigration completed with issues. Check the logs for details.")
        sys.exit(1)
