#!/usr/bin/env python3
"""
Robot Scan Data Processing Module

Processes 3D scan data and creates CSC components.

Programmatic Usage:
    from process_robot_scan import process_scan_by_path
    success = process_scan_by_path('/path/to/uuid-folder')
"""

import os
import sys
import json
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from sklearn.decomposition import PCA

# MESH REDUCTION SETTINGS
# If mesh has face count above this but below reduced threshold,
# only the primitive version will be computed
MESH_PRIMITIVE_THRESHOLD = 8000
# If mesh has face count above this, reduced and primitive versions
# will be created
MESH_REDUCED_THRESHOLD = 15000
# Target face count for reduced mesh
MESH_REDUCED_TARGET = 10000
# Target face count for primitive mesh
MESH_PRIMITIVE_TARGET = 500

# DATASET NAME
DATASET_NAME = "ddu_build_width_debris"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scan_processing.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def validate_uuid(uuid_string: str) -> bool:
    """Validate if string is a valid UUID"""
    try:
        uuid_obj = uuid.UUID(uuid_string)
        return str(uuid_obj) == uuid_string
    except ValueError:
        return False


def normalize_colors_to_integers(colors: np.ndarray) -> np.ndarray:
    """Convert normalized color values (0.0-1.0) to integer values (0-255)"""
    # Check if colors are already in 0-255 range
    if colors.max() > 1.0:
        # Already in 0-255 range, just convert to int
        return np.clip(colors, 0, 255).astype(int)
    else:
        # Normalize from 0-1 to 0-255
        return np.clip(colors * 255, 0, 255).astype(int)


def parse_obj_with_objects(obj_path: str) -> Dict[str, Dict]:
    """Parse OBJ file and extract separate objects and marker points"""
    objects = {}
    marker_points = []
    current_object = None
    global_vertices = []

    with open(obj_path, 'r') as f:
        for line in f:
            line = line.strip()

            if line.startswith('o '):
                # Object declaration
                object_name = line[2:].strip()
                current_object = object_name
                if current_object not in objects:
                    objects[current_object] = {
                        'vertices': [],
                        'colors': [],
                        'faces': [],
                        'vertex_offset': len(global_vertices)
                    }

            elif line.startswith('v '):
                # Vertex with possible color
                parts = line[2:].split()
                if len(parts) >= 3:
                    # Position - swap Y and Z and negate Z to
                    # match coordinate system
                    x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                    vertex = [x, -z, y]  # Swap Y and Z, negate Z
                    global_vertices.append(vertex)

                    # Color (if present)
                    if len(parts) >= 6:
                        r = float(parts[3])
                        g = float(parts[4])
                        b = float(parts[5])
                        color = [r, g, b]
                    else:
                        color = [1.0, 1.0, 1.0]  # Default white

                    # Add to current object if one is active
                    if current_object and current_object in objects:
                        if current_object == 'marker_points':
                            marker_points.append(vertex)
                        else:
                            objects[current_object]['vertices'].append(vertex)
                            objects[current_object]['colors'].append(color)

            elif line.startswith('f '):
                # Face
                if (current_object and current_object in objects and
                        current_object != 'marker_points'):
                    face_parts = line[2:].split()
                    face = []
                    for part in face_parts:
                        # Handle face format (vertex/texture/normal or vertex)
                        vertex_idx = int(part.split('/')[0]) - 1  # 0-based
                        # Adjust for object's vertex offset
                        offset = objects[current_object]['vertex_offset']
                        local_idx = vertex_idx - offset
                        face.append(local_idx)

                    if len(face) >= 3:
                        objects[current_object]['faces'].append(face)

    return {
        'objects': objects,
        'marker_points': marker_points
    }


def triangulate_face(face: List[int]) -> List[List[int]]:
    """Convert n-gon face to triangles"""
    if len(face) == 3:
        return [face]
    elif len(face) == 4:
        # Quad to two triangles
        return [[face[0], face[1], face[2]], [face[0], face[2], face[3]]]
    else:
        # N-gon to triangle fan
        triangles = []
        for i in range(1, len(face) - 1):
            triangles.append([face[0], face[i], face[i + 1]])
        return triangles


def reduce_mesh_trimesh(vertices: np.ndarray, faces: np.ndarray,
                        target_faces: int, colors: np.ndarray = None) -> \
        Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Reduce mesh using trimesh library with color preservation"""
    try:
        # Create trimesh object
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces)

        # Calculate reduction ratio
        current_faces = len(faces)
        if current_faces <= target_faces:
            return (vertices, faces,
                    colors if colors is not None else np.array([]))

        # Simplify mesh
        simplified = mesh.simplify_quadric_decimation(
            face_count=target_faces
        )

        # Map colors to new vertices if colors were provided
        if colors is not None and len(colors) > 0:
            # Find which original vertices are closest to each new vertex
            tree = cKDTree(vertices)
            _, indices = tree.query(simplified.vertices)
            mapped_colors = colors[indices]
            return (simplified.vertices, simplified.faces, mapped_colors)
        else:
            return simplified.vertices, simplified.faces, np.array([])

    except Exception as e:
        logger.warning(f"Mesh reduction failed: {e}, using original mesh")
        return (vertices, faces,
                colors if colors is not None else np.array([]))


def compute_obb_3d(
    points: np.ndarray
) -> Tuple[List[float], np.ndarray, List[float]]:
    """
    Compute object oriented bounding box for 3D points using PCA.
    Returns unsorted dimensions and bounding box origin.
    """
    # Apply PCA to find principal axes
    pca = PCA(n_components=3)
    pca.fit(points)
    # Get principal components (eigenvectors)
    principal_components = pca.components_
    # Ensure right-handed coordinate system
    # Check if determinant is positive (right-handed)
    det = np.linalg.det(principal_components)
    if det < 0:
        # Flip the third component to ensure right-handedness
        principal_components[2] = -principal_components[2]
    # Transform points to PCA space using original component order
    pca_points = np.dot(points, principal_components.T)
    # Find bounds in PCA space
    min_bounds = np.min(pca_points, axis=0)
    max_bounds = np.max(pca_points, axis=0)
    # Compute unsorted dimensions (keep original PCA axis order)
    dimensions = max_bounds - min_bounds
    # Find bounding box center in PCA space
    # Since component is centered at origin, bbx_origin is just the
    # bounding box center in PCA space
    bbx_origin = (min_bounds + max_bounds) / 2.0
    # return results
    return dimensions.tolist(), principal_components, bbx_origin.tolist()


def calculate_bounding_box(meshes_data: List[Dict]) -> List[float]:
    """Calculate bounding box from multiple meshes"""
    if not meshes_data:
        return [1.0, 1.0, 1.0]

    all_vertices = []
    for mesh in meshes_data:
        all_vertices.extend(mesh['v'])

    if not all_vertices:
        return [1.0, 1.0, 1.0]

    vertices_array = np.array(all_vertices)
    min_coords = vertices_array.min(axis=0)
    max_coords = vertices_array.max(axis=0)
    dimensions = max_coords - min_coords

    # Ensure no dimension is zero
    dimensions = np.maximum(dimensions, 0.001)

    return dimensions.tolist()


def create_mesh_data(vertices: List, colors: List, faces: List) -> Dict:
    """Create mesh data structure for component JSON"""
    # Convert colors to integers (0-255)
    colors_array = np.array(colors)
    int_colors = normalize_colors_to_integers(colors_array)

    # Triangulate faces
    triangulated_faces = []
    for face in faces:
        triangles = triangulate_face(face)
        triangulated_faces.extend(triangles)

    return {
        'v': vertices,
        'f': triangulated_faces,
        'c': int_colors.tolist()
    }


def save_combined_obj_file(meshes_data: List[Dict], filepath: str):
    """Save multiple meshes as combined OBJ file"""
    with open(filepath, 'w') as f:
        vertex_offset = 0

        for i, mesh_data in enumerate(meshes_data):
            object_name = f"object_{i}"
            f.write(f"o {object_name}\n")

            # Write vertices with colors
            vertices = mesh_data['v']
            colors = mesh_data['c']

            for j, vertex in enumerate(vertices):
                if j < len(colors):
                    color = colors[j]
                    # negate Z again to make coordinate system match
                    f.write(f"v {vertex[0]} {-vertex[1]} {-vertex[2]} "
                            f"{color[0]} {color[1]} {color[2]}\n")
                else:
                    f.write(f"v {vertex[0]} {-vertex[1]} {-vertex[2]} "
                            f"255 255 255\n")

            # Write faces (adjust for global vertex offset)
            for face in mesh_data['f']:
                face_str = " ".join(str(idx + 1 + vertex_offset)
                                    for idx in face)
                f.write(f"f {face_str}\n")

            vertex_offset += len(vertices)


def process_scan_folder(scan_folder: str, component_id: str) -> bool:
    """Process a single scan folder"""
    logger.info(f"[PROCESSING] Processing scan folder: {component_id}")

    # Paths
    metadata_path = os.path.join(scan_folder, 'metadata.json')
    output_folder = os.path.join(scan_folder, 'output')
    aligned_mesh_path = os.path.join(output_folder, 'aligned_mesh.obj')
    transcode_folder = os.path.join(scan_folder, 'transcode')

    logger.info("[FOLDER] Folder structure:")
    logger.info(f"   [FILE] Metadata: {os.path.basename(metadata_path)}")
    logger.info(f"   [FOLDER] Output: {os.path.basename(output_folder)}")
    logger.info("   [TARGET] Target: transcode/")

    # Create transcode folder
    logger.info("[FOLDER] Creating transcode folder...")
    os.makedirs(transcode_folder, exist_ok=True)

    # Check required files
    logger.info("[SEARCH] Checking required files...")
    if not os.path.exists(metadata_path):
        logger.error(f"[ERROR] Missing metadata.json in {component_id}")
        return False
    logger.info("[OK] Found metadata.json")

    if not os.path.exists(aligned_mesh_path):
        logger.error(f"[ERROR] Missing aligned_mesh.obj in {component_id}")
        return False
    logger.info("[OK] Found aligned_mesh.obj")

    try:
        # Load metadata
        logger.info("[PROCESSING] Loading metadata.json...")
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        logger.info(f"[OK] Metadata loaded: {len(metadata)} keys")

        # Parse OBJ file
        logger.info("[SEARCH] Parsing aligned_mesh.obj...")
        obj_data = parse_obj_with_objects(aligned_mesh_path)
        objects = obj_data['objects']
        marker_points = obj_data['marker_points']

        logger.info("[OBJ] OBJ parsing results:")
        logger.info(f"   [TARGET] Objects found: {list(objects.keys())}")
        logger.info(f"   [MARKER POINTS] Marker points: {len(marker_points)}")

        # Check for required objects
        if 'object' not in objects:
            logger.error(
                f"[ERROR] Missing 'object' in OBJ file for {component_id}"
            )
            return False
        obj_verts = len(objects['object']['vertices'])
        obj_faces = len(objects['object']['faces'])
        logger.info(f"[OK] Main object found: {obj_verts} vertices, "
                    f"{obj_faces} faces")

        if 'end_effector' not in objects:
            logger.warning(f"[WARNING] Missing 'end_effector' in OBJ "
                           f"for {component_id}")
        else:
            ee_verts = len(objects['end_effector']['vertices'])
            ee_faces = len(objects['end_effector']['faces'])
            logger.info(f"[OK] End effector found: {ee_verts} vertices, "
                        f"{ee_faces} faces")

        # Prepare meshes (object first, end_effector second)
        logger.info("[PROCESSING] Processing meshes...")
        meshes_data = []
        primitive_meshes = []

        # Process 'object' mesh (first)
        logger.info("[TARGET] Processing main object mesh...")
        obj_mesh = objects['object']
        if obj_mesh['vertices'] and obj_mesh['faces']:
            orig_verts = len(obj_mesh['vertices'])
            orig_faces = len(obj_mesh['faces'])
            logger.info(f"   [OBJ] Original: {orig_verts} vertices, "
                        f"{orig_faces} faces")
            mesh_data = create_mesh_data(
                obj_mesh['vertices'],
                obj_mesh['colors'],
                obj_mesh['faces']
            )
            meshes_data.append(mesh_data)
            # Create primitive version
            logger.info("[PROCESSING] Creating primitive version...")
            vertices_array = np.array(obj_mesh['vertices'])
            triangulated = [triangulate_face(f)[0] for f in obj_mesh['faces']
                            if len(f) >= 3]
            faces_array = np.array(triangulated)

            if len(faces_array) > MESH_PRIMITIVE_THRESHOLD:
                logger.info(
                    f"   [PROCESSING] Reducing from {len(faces_array)} "
                    f"to {MESH_PRIMITIVE_TARGET} faces..."
                )
                prim_vertices, prim_faces, prim_colors = reduce_mesh_trimesh(
                    vertices_array, faces_array, MESH_PRIMITIVE_TARGET,
                    np.array(obj_mesh['colors'])
                )
                # Swap Y and Z axes for coordinate system consistency
                prim_vertices = np.array(prim_vertices)
                prim_vertices[:, [1, 2]] = prim_vertices[:, [2, 1]]
                prim_vertices[:, 2] = -prim_vertices[:, 2]
                # Create Mesh Data
                primitive_mesh = create_mesh_data(
                    prim_vertices.tolist(),
                    prim_colors.tolist(),
                    prim_faces.tolist()
                )
                logger.info(f"   [OK] Reduced to {len(prim_faces)} faces")
            else:
                logger.info(f"   [OK] Mesh already small "
                            f"enough ({len(faces_array)} faces, "
                            f"<{MESH_PRIMITIVE_THRESHOLD})")
                primitive_mesh = mesh_data.copy()

            primitive_meshes.append(primitive_mesh)

        # Process 'end_effector' mesh (second)
        if 'end_effector' in objects:
            logger.info("[PROCESSING] Processing end_effector mesh...")
            ee_mesh = objects['end_effector']
            if ee_mesh['vertices'] and ee_mesh['faces']:
                logger.info(f"   [OBJ] Original: {len(ee_mesh['vertices'])} "
                            f"vertices, {len(ee_mesh['faces'])} faces")
                mesh_data = create_mesh_data(
                    ee_mesh['vertices'],
                    ee_mesh['colors'],
                    ee_mesh['faces']
                )
                meshes_data.append(mesh_data)
                # Create primitive version
                logger.info("   [PROCESSING] Creating primitive version...")
                vertices_array = np.array(ee_mesh['vertices'])
                triangulated = [triangulate_face(f)[0]
                                for f in ee_mesh['faces'] if len(f) >= 3]
                faces_array = np.array(triangulated)
                # Reduce mesh
                if len(faces_array) > MESH_PRIMITIVE_THRESHOLD:
                    logger.info(
                        f"   [PROCESSING] Reducing from {len(faces_array)} "
                        f"to {MESH_PRIMITIVE_TARGET} faces...")
                    prim_vertices, prim_faces, prim_colors = \
                        reduce_mesh_trimesh(
                            vertices_array, faces_array, MESH_PRIMITIVE_TARGET,
                            np.array(ee_mesh['colors'])
                        )
                    # Swap Y and Z axes for coordinate system consistency
                    prim_vertices = np.array(prim_vertices)
                    prim_vertices[:, [1, 2]] = prim_vertices[:, [2, 1]]
                    prim_vertices[:, 2] = -prim_vertices[:, 2]
                    # Create Mesh Data
                    primitive_mesh = create_mesh_data(
                        prim_vertices.tolist(),
                        prim_colors.tolist(),
                        prim_faces.tolist()
                    )
                    logger.info(f"   [OK] Reduced to {len(prim_faces)} faces")
                else:
                    logger.info(f"   [OK] Mesh already small enough "
                                f"({len(faces_array)} faces, "
                                f"<{MESH_PRIMITIVE_THRESHOLD})")
                    primitive_mesh = mesh_data.copy()

                primitive_meshes.append(primitive_mesh)
            else:
                logger.info("   [WARNING] End effector has no geometry")

        if not meshes_data:
            logger.error(f"[ERROR] No valid meshes found for {component_id}")
            return False
        logger.info(f"[OK] Processed {len(meshes_data)} meshes total")
        # Save OBJ files
        logger.info("[FILE] Saving OBJ files...")
        mesh_obj_path = os.path.join(transcode_folder, 'mesh.obj')
        logger.info("   [FILE] Detailed mesh: mesh.obj")
        save_combined_obj_file(meshes_data, mesh_obj_path)
        # Create reduced OBJ if needed (check if any mesh has > threshold)
        face_counts = [len(mesh['f']) for mesh in meshes_data]
        needs_reduced = any(count > MESH_REDUCED_THRESHOLD
                            for count in face_counts)
        logger.info(f"[SEARCH] Face counts: {face_counts}")

        if needs_reduced:
            logger.info("[PROCESSING] Creating reduced mesh version "
                        f"(>{MESH_REDUCED_THRESHOLD} faces detected)...")
            reduced_meshes = []
            for i, mesh_data in enumerate(meshes_data):
                mesh_faces = len(mesh_data['f'])
                if mesh_faces > MESH_REDUCED_THRESHOLD:
                    logger.info(
                        f"   [PROCESSING] Reducing mesh {i+1}: {mesh_faces} "
                        f"-> {MESH_REDUCED_TARGET} faces")
                    # Create reduced version
                    vertices_array = np.array(mesh_data['v'])
                    faces_array = np.array(mesh_data['f'])
                    reduced_vertices, reduced_faces, reduced_colors = \
                        reduce_mesh_trimesh(
                            vertices_array, faces_array, MESH_REDUCED_TARGET,
                            np.array(mesh_data['c'])
                        )
                    reduced_mesh = create_mesh_data(
                        reduced_vertices.tolist(),
                        reduced_colors.tolist(),
                        reduced_faces.tolist()
                    )
                    reduced_meshes.append(reduced_mesh)
                    logger.info(f"   [OK] Mesh {i+1} reduced "
                                f"to {len(reduced_faces)} faces")
                else:
                    logger.info(f"   [OK] Mesh {i+1} kept "
                                f"original ({mesh_faces} faces)")
                    reduced_meshes.append(mesh_data)

            mesh_reduced_path = os.path.join(transcode_folder,
                                             'mesh_reduced.obj')
            logger.info("   [FILE] Reduced mesh: mesh_reduced.obj")
            save_combined_obj_file(reduced_meshes, mesh_reduced_path)
        else:
            logger.info(f"[OK] No reduction needed (all meshes "
                        f"< {MESH_REDUCED_THRESHOLD} faces)")

        # Compute PCA for the 'object' mesh only
        logger.info("[PCA] Computing PCA for 'object' mesh...")
        if 'object' in objects and objects['object']['vertices']:
            # Get vertices directly from the parsed object mesh
            object_mesh_vertices = np.array(objects['object']['vertices'])
            logger.info(f"[PCA] Object mesh vertices: "
                        f"{len(object_mesh_vertices)}")

            # Apply coordinate system transformation (swap Y/Z axes) for PCA
            # computation
            # This matches the coordinate system used for primitive geometry
            pca_vertices = object_mesh_vertices.copy()
            pca_vertices[:, [1, 2]] = pca_vertices[:, [2, 1]]  # Swap Y and Z
            pca_vertices[:, 2] = -pca_vertices[:, 2]  # Negate Z
            logger.info("[PCA] Applied Y/Z axis swap for Rhino coordinate "
                        "system")

            # Center the transformed object mesh at origin
            centroid = np.mean(pca_vertices, axis=0)
            translation_vector = centroid
            centered_vertices = pca_vertices - centroid

            # Compute PCA for the centered and transformed object mesh
            pca_dimensions, principal_components, bbx_origin = \
                compute_obb_3d(centered_vertices)
            logger.info(f"[PCA] PCA dimensions: "
                        f"[{pca_dimensions[0]:.3f}, {pca_dimensions[1]:.3f}, "
                        f"{pca_dimensions[2]:.3f}]")
            logger.info(f"[PCA] Bounding box origin: "
                        f"[{bbx_origin[0]:.3f}, {bbx_origin[1]:.3f}, "
                        f"{bbx_origin[2]:.3f}]")
        else:
            # Fallback values if no meshes
            pca_dimensions = [1.0, 1.0, 1.0]
            principal_components = np.eye(3)
            bbx_origin = [0.0, 0.0, 0.0]
            translation_vector = np.array([0.0, 0.0, 0.0])
            logger.warning("[PCA] No meshes found, using default PCA values")

        # Create component JSON
        logger.info("[FILE] Creating component JSON...")
        current_time = datetime.utcnow().isoformat() + 'Z'

        # Use PCA dimensions as bounding box
        bounding_box = pca_dimensions
        logger.info(f"[BOUNDING BOX] PCA bounding box: "
                    f"[{bounding_box[0]:.3f}, {bounding_box[1]:.3f}, "
                    f"{bounding_box[2]:.3f}]")

        # Transform marker points to compensate for rotateX(-Math.PI/2) in
        # ComponentViewer. To get final result [x, -y, -z] after rotation
        # [x, y, z] -> [x, z, -y], we need [x, y, z] -> [x, z, -y]
        marker_points = [[point[0], point[2], -point[1]]
                         for point in marker_points]

        component_data = {
            "_id": component_id,
            "name": f"Scanned Rubble Component {component_id[:8]}",
            "type": "rubble",
            "material": "concrete",
            "created": current_time,
            "lastmodified": current_time,
            "complexity": 2,
            "fragment": True,
            "assembly": False,
            "geometry": {
                "meshes": primitive_meshes
            },
            "color": [110, 110, 110],
            "bbx": bounding_box,
            "bbx_origin": bbx_origin,
            "location": {
                "lat": 49.861444,
                "lon": 8.676556
            },
            "descriptors": {},
            "processes": {},
            "iframe": {
                "o": [0.0, 0.0, 0.0],
                "x": [1.0, 0.0, 0.0],
                "y": [0.0, 1.0, 0.0],
                "z": [0.0, 0.0, 1.0]
            },
            "pca_frame": {
                "o": translation_vector.tolist(),
                "x": principal_components[0].tolist(),
                "y": principal_components[1].tolist(),
                "z": principal_components[2].tolist()
            },
            "reserved": "",
            "attributes": {
                "3d_scan_metadata": metadata
            },
            "marker_points": marker_points,
            "dataset": DATASET_NAME,
            "validated": False
        }

        # Save component JSON
        component_json_path = os.path.join(transcode_folder,
                                           f"{component_id}.json")
        logger.info(f"[FILE] Saving component JSON: {component_id}.json")
        with open(component_json_path, 'w') as f:
            json.dump(component_data, f, indent=2)

        # Summary
        logger.info(f"[OK] Successfully processed component: {component_id}")
        logger.info("[SUMMARY] Summary:")
        logger.info(f"   [TARGET] Meshes processed: {len(meshes_data)}")
        logger.info(
            f"   [PROCESSING] Primitive meshes: {len(primitive_meshes)}"
        )
        logger.info(f"   [MARKER POINTS] Marker points: {len(marker_points)}")
        logger.info(f"   [BOUNDING BOX] PCA bounding box: {bounding_box}")
        logger.info(f"   [PCA] PCA frame origin: "
                    f"{translation_vector.tolist()}")
        logger.info(f"   [PCA] Bounding box origin: {bbx_origin}")
        reduced_status = (f'Created (>{MESH_REDUCED_THRESHOLD} faces)'
                          if needs_reduced
                          else f'Not needed (<{MESH_REDUCED_THRESHOLD} faces)')
        logger.info(f"[PROCESSING] Reduced OBJ: {reduced_status}")
        logger.info("   [FOLDER] Output files:")
        logger.info("      [FILE] mesh.obj")
        if needs_reduced:
            logger.info("      [FILE] mesh_reduced.obj")
        logger.info(f"      [FILE] {component_id}.json")

        return True

    except Exception as e:
        logger.error(f"Error processing {component_id}: {e}")
        return False


def process_scan_by_path(scan_folder_path: str) -> bool:
    """
    Process a single scan folder by its path (programmatic interface).

    This function provides a programmatic interface for processing scan data
    without requiring command-line arguments or folder watching.

    Args:
        scan_folder_path (str): Path to the UUID-named scan folder to process

    Returns:
        bool: True if processing was successful, False otherwise

    Example:
        success = process_scan_by_path('/path/to/scan/folder/uuid-12345')
    """
    scan_path = Path(scan_folder_path)

    if not scan_path.exists():
        logger.error(f"[ERROR] Scan folder does not exist: {scan_folder_path}")
        return False

    # Extract component ID from folder name
    component_id = scan_path.name

    if not validate_uuid(component_id):
        logger.error(f"[ERROR] Invalid UUID folder name: {component_id}")
        return False

    logger.info(f"[PROCESSING] Processing scan folder: {component_id}")

    # Process the folder (without moving it)
    return process_scan_folder(str(scan_path), component_id)


if __name__ == "__main__":
    # Simple CLI for testing
    import sys
    if len(sys.argv) != 2:
        print("Usage: python process_robot_scan.py <scan_folder_path>")
        sys.exit(1)

    success = process_scan_by_path(sys.argv[1])
    if not success:
        sys.exit(1)
