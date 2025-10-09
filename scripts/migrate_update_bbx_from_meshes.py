#!/usr/bin/env python3
"""
MongoDB Bounding Box Migration Script

This script reads mesh.obj files from component_geometry/csc_meshes/{component_id}/
and updates the MongoDB components with correct bounding box values:

1. Reads mesh.obj files from component_geometry/csc_meshes/{component_id}/mesh.obj
2. Computes bounding box dimensions (unsorted, as per new schema)
3. Computes bounding box origin (center of bounding box in PCA space)
4. Updates MongoDB components with new bbx and bbx_origin values
5. Preserves existing PCA frame and other component data

The script:
1. Connects to MongoDB
2. Finds all components that have corresponding mesh files
3. Computes bounding boxes from mesh.obj files
4. Updates the database with new bbx and bbx_origin values
5. Provides a summary of the migration

Usage:
    python scripts/migrate_update_bbx_from_meshes.py [--dry-run]

Options:
    --dry-run    Show what would be changed without making actual changes

Requirements:
    - pymongo
    - trimesh (for mesh processing)
    - MongoDB connection string in environment or config
"""

import os
import sys
import json
import argparse
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import logging
import trimesh

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


def compute_bounding_box_from_mesh(mesh_path: str) -> tuple:
    """
    Compute bounding box dimensions and origin from mesh.obj file.
    
    Note: OBJ files use a different coordinate system, so we swap Y and Z
    to match the expected coordinate system.
    
    Args:
        mesh_path: Path to the mesh.obj file
        
    Returns:
        tuple: (bbx_dimensions, bbx_origin) where:
            - bbx_dimensions: [width, height, depth] as list of floats (Y and Z swapped)
            - bbx_origin: [x, y, z] center of bounding box as list of floats (Y and Z swapped)
    """
    try:
        # Load mesh using trimesh
        mesh = trimesh.load(mesh_path)
        
        # Get bounding box
        bbox = mesh.bounds
        
        # Compute dimensions (unsorted, as per new schema)
        min_bounds = bbox[0]  # [min_x, min_y, min_z]
        max_bounds = bbox[1]  # [max_x, max_y, max_z]
        
        # Dimensions are the differences
        dimensions = max_bounds - min_bounds
        
        # Bounding box origin is the center
        bbx_origin = (min_bounds + max_bounds) / 2.0
        
        # Convert to lists for easier manipulation
        dimensions_list = dimensions.tolist()
        origin_list = bbx_origin.tolist()
        
        # Swap Y and Z coordinates to match expected coordinate system
        # OBJ: [x, y, z] -> Expected: [x, z, y]
        dimensions_swapped = [dimensions_list[0], dimensions_list[2], dimensions_list[1]]
        origin_swapped = [origin_list[0], -origin_list[2], origin_list[1]]
        
        logger.info(f"  Original dimensions: {dimensions_list}")
        logger.info(f"  Swapped dimensions: {dimensions_swapped}")
        logger.info(f"  Original origin: {origin_list}")
        logger.info(f"  Swapped origin: {origin_swapped}")
        
        return dimensions_swapped, origin_swapped
        
    except Exception as e:
        logger.error(f"Failed to compute bounding box for {mesh_path}: {e}")
        return None, None


def find_components_with_meshes(collection, mesh_base_path: str) -> list:
    """
    Find all components that have corresponding mesh files.
    
    Args:
        collection: MongoDB collection
        mesh_base_path: Base path to csc_meshes directory
        
    Returns:
        list: List of component documents that have mesh files
    """
    components_with_meshes = []
    
    # Get all components
    components = collection.find({})
    
    for component in components:
        component_id = component.get('_id')
        if not component_id:
            continue
            
        # Check if mesh file exists
        mesh_path = os.path.join(mesh_base_path, str(component_id), 'mesh.obj')
        
        if os.path.exists(mesh_path):
            components_with_meshes.append(component)
            logger.info(f"Found mesh for component {component_id}")
        else:
            logger.warning(f"No mesh found for component {component_id}")
    
    return components_with_meshes


def update_component_bbx(collection, component_id: str, bbx_dimensions: list, 
                        bbx_origin: list, existing_bbx: list = None, 
                        existing_bbx_origin: list = None, dry_run: bool = False) -> tuple:
    """
    Update component with new bounding box values.
    
    Args:
        collection: MongoDB collection
        component_id: Component ID to update
        bbx_dimensions: New bounding box dimensions [width, height, depth]
        bbx_origin: New bounding box origin [x, y, z]
        existing_bbx: Current bbx values for comparison
        existing_bbx_origin: Current bbx_origin values for comparison
        dry_run: If True, don't actually update the database
        
    Returns:
        tuple: (success: bool, has_changes: bool) where:
            - success: True if successful, False otherwise
            - has_changes: True if values are different, False if identical
    """
    try:
        # Log comparison of existing vs new values
        logger.info(f"Component {component_id} bounding box comparison:")
        logger.info(f"  {'='*60}")
        
        if existing_bbx:
            logger.info(f"  Existing bbx: {existing_bbx}")
        else:
            logger.info(f"  Existing bbx: None")
        logger.info(f"  New bbx:      {bbx_dimensions}")
        
        if existing_bbx_origin:
            logger.info(f"  Existing bbx_origin: {existing_bbx_origin}")
        else:
            logger.info(f"  Existing bbx_origin: None")
        logger.info(f"  New bbx_origin:      {bbx_origin}")
        
        # Calculate differences if both exist
        if existing_bbx and bbx_dimensions:
            try:
                bbx_diff = [new - old for new, old in zip(bbx_dimensions, existing_bbx)]
                logger.info(f"  bbx difference:     {bbx_diff}")
            except:
                logger.info(f"  bbx difference:     Cannot calculate (different lengths)")
        
        if existing_bbx_origin and bbx_origin:
            try:
                origin_diff = [new - old for new, old in zip(bbx_origin, existing_bbx_origin)]
                logger.info(f"  bbx_origin diff:    {origin_diff}")
            except:
                logger.info(f"  bbx_origin diff:    Cannot calculate (different lengths)")
        
        logger.info(f"  {'='*60}")
        
        # Check if values have changed
        bbx_changed = existing_bbx != bbx_dimensions
        origin_changed = existing_bbx_origin != bbx_origin
        has_changes = bbx_changed or origin_changed
        
        if has_changes:
            logger.info(f"  CHANGES DETECTED: bbx={bbx_changed}, bbx_origin={origin_changed}")
        else:
            logger.info(f"  NO CHANGES: Values are identical")
        
        if dry_run:
            logger.info(f"[DRY RUN] Would update component {component_id}")
            return True, has_changes
        
        # Update the component
        result = collection.update_one(
            {'_id': component_id},
            {
                '$set': {
                    'bbx': bbx_dimensions,
                    'bbx_origin': bbx_origin
                }
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"Successfully updated component {component_id}")
            return True, has_changes
        else:
            logger.warning(f"No changes made to component {component_id}")
            return False, has_changes
            
    except Exception as e:
        logger.error(f"Failed to update component {component_id}: {e}")
        return False, False


def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(description='Migrate bounding box data from mesh files')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be changed without making actual changes')
    args = parser.parse_args()
    
    logger.info("Starting bounding box migration from mesh files...")
    
    # Load MongoDB configuration
    config = load_config()
    if not config or 'uri' not in config:
        logger.error("Failed to load MongoDB configuration")
        return 1
    
    # Connect to MongoDB
    try:
        client = MongoClient(config['uri'])
        db = client.get_default_database()
        collection = db.components
        logger.info("Connected to MongoDB successfully")
    except PyMongoError as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        return 1
    
    # Set up mesh base path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mesh_base_path = os.path.join(script_dir, '..', 'component_geometry', 'csc_meshes')
    mesh_base_path = os.path.normpath(mesh_base_path)
    
    if not os.path.exists(mesh_base_path):
        logger.error(f"Mesh base path does not exist: {mesh_base_path}")
        return 1
    
    logger.info(f"Using mesh base path: {mesh_base_path}")
    
    # Find components with meshes
    logger.info("Finding components with corresponding mesh files...")
    components_with_meshes = find_components_with_meshes(collection, mesh_base_path)
    
    if not components_with_meshes:
        logger.warning("No components with mesh files found")
        return 0
    
    logger.info(f"Found {len(components_with_meshes)} components with mesh files")
    
    # Process each component
    successful_updates = 0
    failed_updates = 0
    components_with_changes = 0
    components_without_changes = 0
    
    for component in components_with_meshes:
        component_id = component.get('_id')
        mesh_path = os.path.join(mesh_base_path, str(component_id), 'mesh.obj')
        
        logger.info(f"Processing component {component_id}...")
        
        # Get existing values for comparison
        existing_bbx = component.get('bbx')
        existing_bbx_origin = component.get('bbx_origin')
        
        # Compute bounding box from mesh
        bbx_dimensions, bbx_origin = compute_bounding_box_from_mesh(mesh_path)
        
        if bbx_dimensions is None or bbx_origin is None:
            logger.error(f"Failed to compute bounding box for component {component_id}")
            failed_updates += 1
            continue
        
        # Update component in database
        success, has_changes = update_component_bbx(
            collection, component_id, bbx_dimensions, bbx_origin, 
            existing_bbx, existing_bbx_origin, args.dry_run
        )
        
        if success:
            successful_updates += 1
            if has_changes:
                components_with_changes += 1
            else:
                components_without_changes += 1
        else:
            failed_updates += 1
    
    # Summary
    logger.info("=" * 50)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 50)
    logger.info(f"Total components processed: {len(components_with_meshes)}")
    logger.info(f"Successful updates: {successful_updates}")
    logger.info(f"  - Components with changes: {components_with_changes}")
    logger.info(f"  - Components without changes: {components_without_changes}")
    logger.info(f"Failed updates: {failed_updates}")
    
    if args.dry_run:
        logger.info("DRY RUN COMPLETED - No actual changes were made")
    else:
        logger.info("MIGRATION COMPLETED")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
