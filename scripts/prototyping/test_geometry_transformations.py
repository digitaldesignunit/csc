#!/usr/bin/env python3.9
"""
Test script for verifying geometry transformations using Polyscope.

This script allows visual verification of PCA frame transformations
by loading components from a MongoDB dump and their geometry.

Usage:
    python test_geometry_transformations.py [component_id]

If no component_id is provided, a random component will be selected.

Data locations:
    - MongoDB dump: D:\\02_DATASETS\\csc_components\\251026_csc.components.json
    - Geometry: D:\\02_DATASETS\\csc_component_geometry\\{uuid}\\

The script will:
1. Load component from MongoDB dump
2. Load corresponding geometry (OBJ or primitive)
3. Apply PCA frame transformation
4. Display before/after meshes with Polyscope
5. Show coordinate frames and mesh statistics
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os
import json
import random
import sys
from typing import Dict, Optional, List

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np
import trimesh
import polyscope as ps

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.descriptors.geometry import (
    load_mesh_from_primitive,
    load_mesh_from_obj,
    create_mesh_from_extrusion,
    load_primitive_mesh_for_descriptor,
    load_obj_mesh_for_descriptor,
    load_extrusion_mesh_for_descriptor
)


# CONFIGURATION ---------------------------------------------------------------

MONGODB_DUMP = r'D:\02_DATASETS\csc_components\251026_csc.components.json'
GEOMETRY_DIR = r'D:\02_DATASETS\csc_component_geometry'


# HELPER FUNCTIONS ------------------------------------------------------------

def load_components_from_dump(dump_file: str) -> List[Dict]:
    """
    Load all components from MongoDB dump file.

    Args:
        dump_file: Path to MongoDB JSON dump file

    Returns:
        List of component dictionaries
    """
    with open(dump_file, 'r', encoding='utf-8') as f:
        components = json.load(f)

    return components


def find_component_by_id(
    components: List[Dict],
    component_id: str
) -> Optional[Dict]:
    """Find component by ID."""
    for component in components:
        if component.get('_id') == component_id:
            return component
    return None


def get_geometry_paths(geometry_dir: str, component_id: str) -> Dict[str, str]:
    """Get paths to geometry files for a component."""
    comp_dir = os.path.join(geometry_dir, component_id)

    paths = {
        'mesh': None,
        'mesh_reduced': None
    }

    if not os.path.exists(comp_dir) or not os.path.isdir(comp_dir):
        return paths

    mesh_path = os.path.join(comp_dir, 'mesh.obj')
    if os.path.exists(mesh_path) and os.path.isfile(mesh_path):
        paths['mesh'] = mesh_path

    mesh_reduced_path = os.path.join(comp_dir, 'mesh_reduced.obj')
    if os.path.exists(mesh_reduced_path) and os.path.isfile(mesh_reduced_path):
        paths['mesh_reduced'] = mesh_reduced_path

    return paths


def load_mesh_without_pca(
    component: Dict,
    geometry_paths: Dict
) -> Optional[trimesh.Trimesh]:
    """
    Load mesh WITHOUT applying PCA transformation.

    Returns the mesh in its original centered state.
    """
    # Try OBJ files first
    if geometry_paths['mesh']:
        try:
            print('  Loading mesh.obj...')
            mesh = load_mesh_from_obj(geometry_paths['mesh'])
            return mesh
        except Exception as e:
            print(f'  Failed to load mesh.obj: {e}')

    if geometry_paths['mesh_reduced']:
        try:
            print('  Loading mesh_reduced.obj...')
            mesh = load_mesh_from_obj(geometry_paths['mesh_reduced'])
            return mesh
        except Exception as e:
            print(f'  Failed to load mesh_reduced.obj: {e}')

    # Fallback to primitive geometry
    try:
        geometry = component.get('geometry', {})

        if 'meshes' in geometry and geometry['meshes']:
            print('  Loading primitive mesh (meshes format)...')
            mesh_data = geometry['meshes'][0]
            vertices = mesh_data['v']
            faces = mesh_data['f']
            mesh = load_mesh_from_primitive(vertices, faces)
            return mesh

        elif 'mesh' in geometry and geometry['mesh']:
            print('  Loading primitive mesh (mesh format)...')
            mesh_data = geometry['mesh']
            vertices = mesh_data['v']
            faces = mesh_data['f']
            mesh = load_mesh_from_primitive(vertices, faces)
            return mesh

        elif 'extrusion' in geometry and geometry['extrusion']:
            print('  Loading extrusion geometry...')
            extrusion_data = geometry['extrusion']
            profile = extrusion_data['profile']
            height = extrusion_data['height']
            mesh = create_mesh_from_extrusion(profile, height)
            return mesh

    except Exception as e:
        print(f'  Failed to load primitive geometry: {e}')

    return None


def load_mesh_with_pca(
    component: Dict,
    geometry_paths: Dict
) -> Optional[trimesh.Trimesh]:
    """
    Load mesh WITH PCA transformation applied.

    Returns the mesh aligned with PCA axes.
    """
    pca_frame = component.get('pca_frame')

    # Try OBJ files first
    if geometry_paths['mesh']:
        try:
            mesh = load_obj_mesh_for_descriptor(
                geometry_paths['mesh'],
                pca_frame=pca_frame
            )
            return mesh
        except Exception as e:
            print(f'  Failed: {e}')

    if geometry_paths['mesh_reduced']:
        try:
            mesh = load_obj_mesh_for_descriptor(
                geometry_paths['mesh_reduced'],
                pca_frame=pca_frame
            )
            return mesh
        except Exception as e:
            print(f'  Failed: {e}')

    # Fallback to primitive geometry
    try:
        geometry = component.get('geometry', {})

        if 'meshes' in geometry and geometry['meshes']:
            mesh_data = geometry['meshes'][0]
            vertices = mesh_data['v']
            faces = mesh_data['f']
            mesh = load_primitive_mesh_for_descriptor(
                vertices, faces, pca_frame=pca_frame
            )
            return mesh

        elif 'mesh' in geometry and geometry['mesh']:
            mesh_data = geometry['mesh']
            vertices = mesh_data['v']
            faces = mesh_data['f']
            mesh = load_primitive_mesh_for_descriptor(
                vertices, faces, pca_frame=pca_frame
            )
            return mesh

        elif 'extrusion' in geometry and geometry['extrusion']:
            extrusion_data = geometry['extrusion']
            profile = extrusion_data['profile']
            height = extrusion_data['height']
            mesh = load_extrusion_mesh_for_descriptor(
                profile, height, pca_frame=pca_frame
            )
            return mesh

    except Exception as e:
        print(f'  Failed: {e}')

    return None


def print_mesh_info(mesh: trimesh.Trimesh, label: str):
    """Print mesh information."""
    bounds = mesh.bounds
    centroid = mesh.centroid
    extents = mesh.extents

    print(f'\n{label}:')
    print(f'  Vertices: {len(mesh.vertices)}')
    print(f'  Faces: {len(mesh.faces)}')
    print(f'  Centroid: [{centroid[0]:.4f}, {centroid[1]:.4f}, '
          f'{centroid[2]:.4f}]')
    print(f'  Extents (L×W×H): [{extents[0]:.4f}, {extents[1]:.4f}, '
          f'{extents[2]:.4f}]')
    print(f'  Bounds Min: [{bounds[0][0]:.4f}, {bounds[0][1]:.4f}, '
          f'{bounds[0][2]:.4f}]')
    print(f'  Bounds Max: [{bounds[1][0]:.4f}, {bounds[1][1]:.4f}, '
          f'{bounds[1][2]:.4f}]')


def visualize_with_polyscope(
    component: Dict,
    mesh_before: trimesh.Trimesh,
    mesh_after: trimesh.Trimesh
):
    """
    Visualize mesh before and after PCA transformation using Polyscope.

    Shows both meshes side by side with coordinate frames.
    """
    component_id = component.get('_id', 'unknown')
    component_name = component.get('name', 'Unnamed')
    component_type = component.get('type', 'unknown')
    pca_frame = component.get('pca_frame')

    print(f'\n{"="*80}')
    print(f'Component: {component_name}')
    print(f'ID: {component_id}')
    print(f'Type: {component_type}')
    print(f'{"="*80}')

    # Print mesh info
    print_mesh_info(mesh_before, 'BEFORE PCA Transformation')
    print_mesh_info(mesh_after, 'AFTER PCA Transformation')

    # Initialize Polyscope
    ps.init()
    ps.set_program_name('Geometry Transformation Test')
    ps.set_up_dir('z_up')
    ps.set_ground_plane_mode('none')

    # Calculate offset for side-by-side display
    max_extent = max(mesh_before.extents)
    offset = max_extent * 2.5

    # Add "BEFORE" mesh (left side)
    vertices_before = mesh_before.vertices.copy()
    vertices_before[:, 0] -= offset  # Offset to the left
    faces_before = mesh_before.faces

    mesh_before_ps = ps.register_surface_mesh(
        'Mesh BEFORE PCA',
        vertices_before,
        faces_before,
        color=(0.6, 0.6, 0.8),  # Light blue
        edge_width=1.0,
        material='clay',
        enabled=True
    )
    mesh_before_ps.set_transparency(0.9)
    mesh_before_ps.set_edge_width(0.5)

    # Add "AFTER" mesh (right side)
    vertices_after = mesh_after.vertices.copy()
    vertices_after[:, 0] += offset  # Offset to the right
    faces_after = mesh_after.faces

    mesh_after_ps = ps.register_surface_mesh(
        'Mesh AFTER PCA',
        vertices_after,
        faces_after,
        color=(0.8, 0.6, 0.6),  # Light red
        edge_width=1.0,
        material='clay',
        enabled=True
    )
    mesh_after_ps.set_transparency(0.9)
    mesh_after_ps.set_edge_width(0.5)

    # Add world coordinate frames
    axis_length = max_extent * 1.5

    # World frame for BEFORE mesh (left)
    world_frame_before = np.eye(4)
    world_frame_before[0, 3] = -offset  # Translate left
    ps.register_curve_network(
        'World Frame (BEFORE)',
        np.array([
            [-offset, 0, 0],
            [-offset + axis_length, 0, 0],
            [-offset, 0, 0],
            [-offset, axis_length, 0],
            [-offset, 0, 0],
            [-offset, 0, axis_length]
        ]),
        np.array([[0, 1], [2, 3], [4, 5]]),
        color=(0.5, 0.5, 0.5),
        radius=0.003
    )

    # World frame for AFTER mesh (right)
    ps.register_curve_network(
        'World Frame (AFTER)',
        np.array([
            [offset, 0, 0],
            [offset + axis_length, 0, 0],
            [offset, 0, 0],
            [offset, axis_length, 0],
            [offset, 0, 0],
            [offset, 0, axis_length]
        ]),
        np.array([[0, 1], [2, 3], [4, 5]]),
        color=(0.5, 0.5, 0.5),
        radius=0.003
    )

    # Add PCA frame for BEFORE mesh (if available)
    if pca_frame:
        origin = np.array(pca_frame['o'])
        x_axis = np.array(pca_frame['x'])
        y_axis = np.array(pca_frame['y'])
        z_axis = np.array(pca_frame['z'])

        # Offset origin to left
        origin_offset = origin.copy()
        origin_offset[0] -= offset

        ps.register_curve_network(
            'PCA Frame (BEFORE)',
            np.array([
                origin_offset,
                origin_offset + x_axis * axis_length,
                origin_offset,
                origin_offset + y_axis * axis_length,
                origin_offset,
                origin_offset + z_axis * axis_length
            ]),
            np.array([[0, 1], [2, 3], [4, 5]]),
            color=(1.0, 0.5, 0.0),  # Orange
            radius=0.003
        )

    # Add text info
    print('\n' + '='*80)
    print('POLYSCOPE VISUALIZATION')
    print('='*80)
    print('\nVisualization:')
    print('  LEFT (blue): BEFORE PCA transformation')
    print('  RIGHT (red): AFTER PCA transformation')
    print('  Gray lines: World coordinate frame (X, Y, Z)')
    if pca_frame:
        print('  Orange lines (left): PCA frame orientation')
    print('\nControls:')
    print('  Mouse drag: Rotate view')
    print('  Mouse wheel: Zoom')
    print('  Right drag: Pan')
    print('  ESC or close window: Exit')
    print('='*80 + '\n')

    # Calculate bounding box for both meshes to set camera view
    all_vertices = np.vstack([vertices_before, vertices_after])
    bbox_min = np.min(all_vertices, axis=0)
    bbox_max = np.max(all_vertices, axis=0)
    bbox_center = (bbox_min + bbox_max) / 2
    bbox_size = np.linalg.norm(bbox_max - bbox_min)

    # Set camera to look at the center of both meshes
    ps.look_at(bbox_center, bbox_center + np.array([0, -bbox_size, 0]))
    ps.set_automatically_compute_scene_extents(False)
    ps.set_length_scale(bbox_size / 2)

    # Show the visualization
    ps.show()


# MAIN TEST FUNCTION ----------------------------------------------------------

def test_component(component: Dict):
    """Test transformation for a single component."""
    component_id = component.get('_id', 'unknown')
    component_name = component.get('name', 'Unnamed')

    print('\n' + '#'*80)
    print(f'Testing Component: {component_name}')
    print(f'ID: {component_id}')
    print('#'*80)

    # Get geometry paths
    geometry_paths = get_geometry_paths(GEOMETRY_DIR, component_id)

    # Load mesh without PCA
    print('\nLoading mesh WITHOUT PCA transformation...')
    mesh_before = load_mesh_without_pca(component, geometry_paths)

    if mesh_before is None:
        print('ERROR: Failed to load mesh')
        return False

    # Load mesh with PCA
    print('\nLoading mesh WITH PCA transformation...')
    mesh_after = load_mesh_with_pca(component, geometry_paths)

    if mesh_after is None:
        print('ERROR: Failed to load mesh with PCA')
        return False

    # Visualize
    visualize_with_polyscope(component, mesh_before, mesh_after)

    return True


def main():
    """Main test function."""
    print('='*80)
    print('GEOMETRY TRANSFORMATION TEST SCRIPT (Polyscope)')
    print('='*80)

    # Check MongoDB dump file
    if not os.path.exists(MONGODB_DUMP):
        print(f'\nERROR: MongoDB dump not found: {MONGODB_DUMP}')
        return

    if not os.path.exists(GEOMETRY_DIR):
        print(f'\nWARNING: Geometry directory not found: {GEOMETRY_DIR}')
        print('Will use primitive geometry from JSON only.')

    # Load components
    print(f'\nLoading components from: {MONGODB_DUMP}')
    components = load_components_from_dump(MONGODB_DUMP)
    print(f'Loaded {len(components)} components')

    if not components:
        print('ERROR: No components found in dump file')
        return

    # Get component ID from command line or select random
    if len(sys.argv) > 1:
        component_id = sys.argv[1]
        print(f'\nSearching for component: {component_id}')
        component = find_component_by_id(components, component_id)

        if component is None:
            print(f'ERROR: Component not found: {component_id}')
            return
    else:
        # Filter for rubble type components
        rubble_components = [
            c for c in components
            if c.get('type') == 'rubble'
        ]

        if not rubble_components:
            print('WARNING: No rubble components found, using all components')
            rubble_components = components
        else:
            print(f'Found {len(rubble_components)} rubble components')

        # Select random rubble component
        component = random.choice(rubble_components)
        print(f'\nRandomly selected component: {component.get("_id")}')
        print(f'Type: {component.get("type")}')

    # Test the component
    try:
        test_component(component)
    except KeyboardInterrupt:
        print('\n\nTest interrupted by user')
    except Exception as e:
        print(f'\nERROR: Unexpected error: {e}')
        import traceback
        traceback.print_exc()

    print('\n' + '='*80)
    print('Testing complete!')
    print('='*80 + '\n')


if __name__ == '__main__':
    main()
