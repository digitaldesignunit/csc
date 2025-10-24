#!/usr/bin/env python3.9
"""
Descriptor computation maintenance script.

This script runs as a cronjob to compute missing descriptors for components.
It processes one component at a time to manage computational resources.

Usage:
    python main_computedescriptors.py [--dry-run]

The script will:
1. Find one component with missing descriptors
2. Load geometry (OBJ files preferred, fallback to primitive)
3. Compute missing descriptors (boxscore, etc.)
4. Update the component in the database
5. Exit (to be run again by cron)
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import asyncio
import os
import sys
from typing import Optional, Dict, List
from datetime import datetime, timezone

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pymongo import AsyncMongoClient
import trimesh

# LOCAL MODULE IMPORTS --------------------------------------------------------
from utility import (
    sanitize_path,
    get_db_connectionstring,
    get_geometry_directory,
    create_logging_timestamp as logts
)

# Import descriptor computation modules
from apps.descriptors.geometry import (
    load_primitive_mesh_for_descriptor,
    load_obj_mesh_for_descriptor,
    load_extrusion_mesh_for_descriptor
)
from apps.descriptors.boxscore import (
    compute_boxscore,
    compute_boxscore_with_metadata
)
from apps.descriptors.spherescore import (
    compute_spherescore,
    compute_spherescore_with_metadata
)

# ENVIRONMENT SETTINGS --------------------------------------------------------

_HERE = os.path.dirname(sanitize_path(__file__))
"""str: Path to directory of this particular file."""

_CONFIG_DIR = sanitize_path(os.path.join(_HERE, 'config'))

_CONFIGFILE = sanitize_path(os.path.join(_CONFIG_DIR, 'dbconfig.json'))
"""str: Default configuration file."""


# DESCRIPTOR CONFIGURATION ----------------------------------------------------

DESCRIPTORS_TO_COMPUTE = ['boxscore']
"""List of descriptor names to compute if missing."""

DESCRIPTOR_PARAMS = {
    'boxscore': {
        'factor': 100.0
    },
    'spherescore': {
        'factor': 100.0
    }
}
"""Parameters for each descriptor computation."""


# HELPER FUNCTIONS ------------------------------------------------------------

def log(message: str, prefix: str = 'DESCRIPTORS'):
    """Print timestamped log message."""
    ts = logts()
    print(f'[{prefix}] {ts} {message}')


async def find_component_with_missing_descriptors(
    mongodb_components,
    descriptor_names: List[str]
) -> Optional[Dict]:
    """
    Find one component that is missing any of the specified descriptors.

    Args:
        mongodb_components: MongoDB collection
        descriptor_names: List of descriptor field names to check

    Returns:
        Component document or None if all components have descriptors
    """
    # Build query to find components missing any descriptor
    # A component is missing a descriptor if:
    # - The descriptors field doesn't exist
    # - The descriptors field exists but the specific descriptor is missing
    # - The descriptors field exists but the specific descriptor is null

    or_conditions = []

    # Check if descriptors field doesn't exist
    or_conditions.append({'descriptors': {'$exists': False}})

    # Check for each specific descriptor
    for desc_name in descriptor_names:
        field_path = f'descriptors.{desc_name}'
        or_conditions.append({field_path: {'$exists': False}})
        or_conditions.append({field_path: None})

    query = {'$or': or_conditions}

    # Find one component matching the query
    component = await mongodb_components.find_one(query)

    return component


def get_geometry_paths(geometry_dir: str, component_id: str) -> Dict[str, str]:
    """
    Get paths to geometry files for a component.

    Args:
        geometry_dir: Base geometry directory
        component_id: Component UUID

    Returns:
        Dictionary with 'mesh' and 'mesh_reduced' keys (values may be None)
    """
    comp_dir = os.path.join(geometry_dir, component_id)

    paths = {
        'mesh': None,
        'mesh_reduced': None
    }

    if not os.path.exists(comp_dir) or not os.path.isdir(comp_dir):
        return paths

    # Check for mesh.obj (highest priority)
    mesh_path = os.path.join(comp_dir, 'mesh.obj')
    if os.path.exists(mesh_path) and os.path.isfile(mesh_path):
        paths['mesh'] = mesh_path

    # Check for mesh_reduced.obj (fallback)
    mesh_reduced_path = os.path.join(comp_dir, 'mesh_reduced.obj')
    if os.path.exists(mesh_reduced_path) and os.path.isfile(mesh_reduced_path):
        paths['mesh_reduced'] = mesh_reduced_path

    return paths


def load_geometry_for_descriptor(
    component: Dict,
    geometry_paths: Dict[str, str],
    geometry_dir: str
) -> Optional[trimesh.Trimesh]:
    """
    Load geometry for descriptor computation.

    Priority:
    1. mesh.obj (if available)
    2. mesh_reduced.obj (if available)
    3. Primitive geometry from component JSON

    Args:
        component: Component document from database
        geometry_paths: Dictionary with geometry file paths
        geometry_dir: Base geometry directory

    Returns:
        trimesh.Trimesh object ready for descriptor computation, or None
    """
    component_id = str(component['_id'])
    pca_frame = component.get('pca_frame')

    # Try mesh.obj first (highest quality)
    if geometry_paths['mesh']:
        try:
            log(f'Loading mesh.obj for component {component_id}')
            mesh = load_obj_mesh_for_descriptor(
                geometry_paths['mesh'],
                pca_frame=pca_frame
            )
            log(f'Successfully loaded mesh.obj '
                f'({len(mesh.vertices)} vertices, {len(mesh.faces)} faces)')
            return mesh
        except Exception as e:
            log(f'Failed to load mesh.obj: {e}', prefix='WARNING')

    # Try mesh_reduced.obj (medium quality)
    if geometry_paths['mesh_reduced']:
        try:
            log(f'Loading mesh_reduced.obj for component {component_id}')
            mesh = load_obj_mesh_for_descriptor(
                geometry_paths['mesh_reduced'],
                pca_frame=pca_frame
            )
            log(f'Successfully loaded mesh_reduced.obj '
                f'({len(mesh.vertices)} vertices, {len(mesh.faces)} faces)')
            return mesh
        except Exception as e:
            log(f'Failed to load mesh_reduced.obj: {e}', prefix='WARNING')

    # Fallback to primitive geometry from JSON
    try:
        log(f'Using primitive geometry for component {component_id}')

        # Get geometry from component
        geometry = component.get('geometry', {})

        # Handle both 'meshes' (new format) and 'mesh' (old format)
        if 'meshes' in geometry and geometry['meshes']:
            # Use first mesh from meshes array
            mesh_data = geometry['meshes'][0]
            vertices = mesh_data['v']
            faces = mesh_data['f']
            mesh = load_primitive_mesh_for_descriptor(
                vertices=vertices,
                faces=faces,
                pca_frame=pca_frame
            )
            log(f'Successfully loaded primitive mesh geometry '
                f'({len(mesh.vertices)} vertices, {len(mesh.faces)} faces)')
            return mesh

        elif 'mesh' in geometry and geometry['mesh']:
            # Old single mesh format
            mesh_data = geometry['mesh']
            vertices = mesh_data['v']
            faces = mesh_data['f']
            mesh = load_primitive_mesh_for_descriptor(
                vertices=vertices,
                faces=faces,
                pca_frame=pca_frame
            )
            log(f'Successfully loaded primitive mesh geometry '
                f'({len(mesh.vertices)} vertices, {len(mesh.faces)} faces)')
            return mesh

        elif 'extrusion' in geometry and geometry['extrusion']:
            # Extrusion geometry (for sheet components)
            extrusion_data = geometry['extrusion']
            profile = extrusion_data['profile']
            height = extrusion_data['height']
            mesh = load_extrusion_mesh_for_descriptor(
                profile=profile,
                height=height,
                pca_frame=pca_frame
            )
            log(f'Successfully loaded extrusion geometry '
                f'({len(mesh.vertices)} vertices, {len(mesh.faces)} faces)')
            return mesh

        else:
            log(f'No geometry found in component {component_id}',
                prefix='ERROR')
            return None

    except Exception as e:
        log(f'Failed to load primitive geometry: {e}', prefix='ERROR')
        return None


def compute_descriptors_for_mesh(
    mesh: trimesh.Trimesh,
    descriptor_names: List[str]
) -> Dict[str, float]:
    """
    Compute all specified descriptors for a mesh.

    Args:
        mesh: trimesh.Trimesh object
        descriptor_names: List of descriptor names to compute

    Returns:
        Dictionary of descriptor_name: value pairs
    """
    results = {}

    for desc_name in descriptor_names:
        try:
            if desc_name == 'boxscore':
                params = DESCRIPTOR_PARAMS.get('boxscore', {})
                log(f'Computing boxscore with parameters: {params}')
                bxscore_data = compute_boxscore_with_metadata(mesh, **params)
                score = bxscore_data['score']
                vbox = bxscore_data['vbox']
                vhull = bxscore_data['vhull']
                factor = bxscore_data['factor']
                print(f'vbox: {vbox}')
                print(f'vhull: {vhull}')
                print(f'factor: {factor}')
                print(f'score: {score}')
                results['boxscore'] = float(score)
                log(f'Computed boxscore: {score:.6f}')

            elif desc_name == 'spherescore':
                params = DESCRIPTOR_PARAMS.get('spherescore', {})
                log(f'Computing spherescore with parameters: {params}')
                spherescore_data = compute_spherescore_with_metadata(mesh, **params)
                score = spherescore_data['score']
                vsphere = spherescore_data['vsphere']
                vhull = spherescore_data['vhull']
                factor = spherescore_data['factor']
                print(f'vsphere: {vsphere}')
                print(f'vhull: {vhull}')
                print(f'factor: {factor}')
                print(f'score: {score}')
                results['spherescore'] = float(score)
                log(f'Computed spherescore: {score:.6f}')

        except Exception as e:
            log(f'Failed to compute {desc_name}: {e}', prefix='ERROR')
            results[desc_name] = None

    return results


async def update_component_descriptors(
    mongodb_components,
    component_id: str,
    descriptors: Dict[str, float]
) -> bool:
    """
    Update component descriptors in database.

    Args:
        mongodb_components: MongoDB collection
        component_id: Component UUID
        descriptors: Dictionary of descriptor values to update

    Returns:
        True if successful, False otherwise
    """
    try:
        # Get current component to preserve existing descriptors
        component = await mongodb_components.find_one({'_id': component_id})

        if not component:
            log(f'Component {component_id} not found', prefix='ERROR')
            return False

        # Merge new descriptors with existing ones
        current_descriptors = component.get('descriptors', {})
        updated_descriptors = {**current_descriptors, **descriptors}

        # Update lastmodified timestamp
        now = datetime.now(timezone.utc).isoformat() + 'Z'

        # Update in database
        result = await mongodb_components.update_one(
            {'_id': component_id},
            {
                '$set': {
                    'descriptors': updated_descriptors,
                    'lastmodified': now
                }
            }
        )

        if result.modified_count > 0:
            log(f'Updated descriptors for component {component_id}')
            return True
        else:
            log(f'No changes made to component {component_id}',
                prefix='WARNING')
            return False

    except Exception as e:
        log(f'Failed to update component {component_id}: {e}', prefix='ERROR')
        return False


# MAIN COMPUTATION LOGIC ------------------------------------------------------

async def compute_descriptors(dry_run: bool = False) -> bool:
    """
    Main descriptor computation function.

    Finds one component with missing descriptors, computes them, and updates
    the database.

    Args:
        dry_run: If True, only log what would be done without updating database

    Returns:
        True if a component was processed, False if no work was done
    """
    log('Starting descriptor computation...')
    if dry_run:
        log('DRY RUN MODE - No database updates will be made')
    log('-' * 80)

    # Connect to MongoDB
    connection_string = get_db_connectionstring(_CONFIGFILE)
    client = AsyncMongoClient(
        connection_string,
        serverSelectionTimeoutMS=5000
    )

    try:
        await client.aconnect()
        await client.admin.command('ping')
        log('Connected to MongoDB')

        db = client['csc']
        mongodb_components = db['components']

        # Get geometry directory
        geometry_dir = get_geometry_directory(_CONFIGFILE)
        log(f'Geometry directory: {geometry_dir}')

        # Find component with missing descriptors
        log(f'Looking for components missing descriptors: '
            f'{", ".join(DESCRIPTORS_TO_COMPUTE)}')

        component = await find_component_with_missing_descriptors(
            mongodb_components,
            DESCRIPTORS_TO_COMPUTE
        )

        if not component:
            log('No components with missing descriptors found')
            return False

        component_id = str(component['_id'])
        component_name = component.get('name', 'Unnamed Component')
        log(f'Found component: {component_id}')
        log(f'  Name: {component_name}')
        log(f'  Type: {component.get("type", "unknown")}')

        # Check which descriptors are missing
        current_descriptors = component.get('descriptors', {})
        missing_descriptors = [
            desc for desc in DESCRIPTORS_TO_COMPUTE
            if desc not in current_descriptors or
            current_descriptors.get(desc) is None
        ]
        log(f'Missing descriptors: {", ".join(missing_descriptors)}')

        # Get geometry paths
        geometry_paths = get_geometry_paths(geometry_dir, component_id)

        # Load geometry
        log('Loading geometry...')
        mesh = load_geometry_for_descriptor(
            component,
            geometry_paths,
            geometry_dir
        )

        if mesh is None:
            log(f'Failed to load geometry for component {component_id}',
                prefix='ERROR')
            return False

        # Compute descriptors
        log('Computing descriptors...')
        descriptors = compute_descriptors_for_mesh(mesh, missing_descriptors)

        if not descriptors:
            log('No descriptors were computed', prefix='WARNING')
            return False

        # Update database
        if dry_run:
            log(f'DRY RUN: Would update component {component_id} '
                f'with descriptors: {descriptors}')
            return True
        else:
            success = await update_component_descriptors(
                mongodb_components,
                component_id,
                descriptors
            )
            return success

    except Exception as e:
        log(f'Error during descriptor computation: {e}', prefix='ERROR')
        import traceback
        traceback.print_exc()
        return False

    finally:
        await client.close()
        log('Closed MongoDB connection')


# MAIN EXECUTION --------------------------------------------------------------

if __name__ == '__main__':
    # Check for dry-run flag
    dry_run = '--dry-run' in sys.argv

    # Run the computation
    success = asyncio.run(compute_descriptors(dry_run=dry_run))

    # Exit with appropriate code
    if success:
        log('Descriptor computation completed successfully')
        sys.exit(0)
    else:
        log('No work done or computation failed')
        sys.exit(1)
