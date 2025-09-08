#!/usr/bin/env python3
"""
Robot Scan Data Processing Script

This script processes 3D scan data from the robot scanning and prepares it
for upload to the CSC (Catalogue of Second Chances) backend.

Features:
- Parses OBJ files with multiple objects and vertex colors
- Creates primitive meshes for fast rendering
- Generates reduced meshes for large datasets
- Handles coordinate system transformations
- Creates component JSON metadata
- Moves processed data to output folder

Usage:
    python process_robot_scan.py --single <scan_folder> <output_folder>
    python process_robot_scan.py <input_folder> <output_folder>
"""

import os
import sys
import json
import shutil
import uuid
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple
import numpy as np
import trimesh
from scipy.spatial import cKDTree

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


def move_processed_folder(
        source_folder: str,
        destination_folder: str,
        component_id: str
) -> bool:
    """Move processed scan folder to destination"""
    try:
        source_path = Path(source_folder)
        dest_path = Path(destination_folder) / component_id

        # Ensure destination directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Move the folder
        shutil.move(str(source_path), str(dest_path))
        logger.info(f"[FOLDER] Moved processed folder: {component_id}")
        logger.info(f"   From: {source_folder}")
        logger.info(f"   To: {dest_path}")
        return True

    except Exception as e:
        logger.error(f"[ERROR] Failed to move folder {component_id}: {e}")
        return False


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
        logger.info("📖 Loading metadata.json...")
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

            if len(faces_array) > 350:
                logger.info(
                    f"   [PROCESSING] Reducing from {len(faces_array)} "
                    f"to 350 faces..."
                )
                prim_vertices, prim_faces, prim_colors = reduce_mesh_trimesh(
                    vertices_array, faces_array, 350,
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
                            f"enough ({len(faces_array)} faces)")
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
                if len(faces_array) > 350:
                    logger.info(
                        f"   [PROCESSING] Reducing from {len(faces_array)} "
                        f"to 350 faces...")
                    prim_vertices, prim_faces, prim_colors = \
                        reduce_mesh_trimesh(
                            vertices_array, faces_array, 350,
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
                                f"({len(faces_array)} faces)")
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
        # Create reduced OBJ if needed (check if any mesh has > 5000 faces)
        face_counts = [len(mesh['f']) for mesh in meshes_data]
        needs_reduced = any(count > 5000 for count in face_counts)
        logger.info(f"[SEARCH] Face counts: {face_counts}")

        if needs_reduced:
            logger.info("[PROCESSING] Creating reduced mesh version "
                        "(>5000 faces detected)...")
            reduced_meshes = []
            for i, mesh_data in enumerate(meshes_data):
                mesh_faces = len(mesh_data['f'])
                if mesh_faces > 5000:
                    logger.info(
                        f"   [PROCESSING] Reducing mesh {i+1}: {mesh_faces} "
                        "-> 1000 faces")
                    # Create reduced version
                    vertices_array = np.array(mesh_data['v'])
                    faces_array = np.array(mesh_data['f'])
                    reduced_vertices, reduced_faces, reduced_colors = \
                        reduce_mesh_trimesh(
                            vertices_array, faces_array, 1000,
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
            logger.info("[OK] No reduction needed (all meshes < 5000 faces)")

        # Create component JSON
        logger.info("[FILE] Creating component JSON...")
        current_time = datetime.utcnow().isoformat() + 'Z'

        # Calculate bounding box from original meshes (not primitive)
        bounding_box = calculate_bounding_box(meshes_data)
        logger.info(f"[BOUNDING BOX] Bounding box: "
                    f"[{bounding_box[0]:.3f}, {bounding_box[1]:.3f}, "
                    f"{bounding_box[2]:.3f}]")

        # Swap marker points Y and Z axes like for primitive meshes
        marker_points = [[point[0], -point[1], -point[2]]
                         for point in marker_points]

        component_data = {
            "_id": component_id,
            "name": f"Scanned Component {component_id[:8]}",
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
                "o": [0.0, 0.0, 0.0],
                "x": [1.0, 0.0, 0.0],
                "y": [0.0, 1.0, 0.0],
                "z": [0.0, 0.0, 1.0]
            },
            "reserved": "",
            "attributes": {
                "3d_scan_metadata": metadata
            },
            "marker_points": marker_points,
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
        logger.info(f"   [BOUNDING BOX] Bounding box: {bounding_box}")
        logger.info("[PROCESSING] Reduced OBJ:"
                    f" {'Created' if needs_reduced else 'Not needed'}")
        logger.info("   [FOLDER] Output files:")
        logger.info("      [FILE] mesh.obj")
        if needs_reduced:
            logger.info("      [FILE] mesh_reduced.obj")
        logger.info(f"      [FILE] {component_id}.json")

        return True

    except Exception as e:
        logger.error(f"Error processing {component_id}: {e}")
        return False


def process_single_folder(scan_folder: str, output_folder: str) -> bool:
    """Process a single scan folder and move it to output folder"""
    scan_path = Path(scan_folder)

    if not scan_path.exists():
        logger.error(f"[ERROR] Scan folder does not exist: {scan_folder}")
        return False

    # Extract component ID from folder name
    component_id = scan_path.name

    if not validate_uuid(component_id):
        logger.error(f"[ERROR] Invalid UUID folder name: {component_id}")
        return False

    logger.info(f"[PROCESSING] Processing single scan folder: {component_id}")

    # Process the folder
    if not process_scan_folder(str(scan_path), component_id):
        logger.error(f"[ERROR] Failed to process scan folder: {component_id}")
        return False

    # Move to output folder
    if not move_processed_folder(str(scan_path), output_folder, component_id):
        logger.error(
            f"[ERROR] Failed to move processed folder: {component_id}"
        )
        return False

    logger.info(f"[OK] Successfully processed and moved: {component_id}")
    return True


def process_multiple_folders(input_folder: str, output_folder: str) -> bool:
    """Process all UUID folders in input directory and move them to output"""
    input_path = Path(input_folder)

    if not input_path.exists():
        logger.error(f"[ERROR] Input folder does not exist: {input_folder}")
        return False

    logger.info(f"[FOLDER] Scanning folder: {input_folder}")

    # Find UUID folders
    logger.info("[SEARCH] Searching for UUID-named directories...")
    all_items = list(input_path.iterdir())
    logger.info(f"📋 Found {len(all_items)} items in directory")

    uuid_folders = []
    for item in all_items:
        if item.is_dir():
            if validate_uuid(item.name):
                uuid_folders.append((str(item), item.name))
                logger.info(f"[OK] Valid UUID folder: {item.name}")
            else:
                logger.info(
                    f"[WARNING] Invalid UUID folder (skipping): {item.name}"
                )
        else:
            logger.info(f"[FILE] File (skipping): {item.name}")

    if not uuid_folders:
        logger.warning("[SEARCH] No UUID folders found in input directory")
        return True

    logger.info(f"[TARGET] Processing {len(uuid_folders)} scan folders")

    # Process each folder
    successful = 0
    failed = 0

    for i, (folder_path, component_id) in enumerate(uuid_folders, 1):
        logger.info(
            f"[UPLOAD] [{i}/{len(uuid_folders)}] Processing: {component_id}"
        )
        # Process the folder
        if process_scan_folder(folder_path, component_id):
            # Move to output folder
            if move_processed_folder(folder_path, output_folder, component_id):
                successful += 1
                logger.info(
                    f"[OK] [{i}/{len(uuid_folders)}] Success: {component_id}")
            else:
                failed += 1
                logger.error(
                    f"[ERROR] [{i}/{len(uuid_folders)}] Failed "
                    f"to move: {component_id}")
        else:
            failed += 1
            logger.error(
                f"[ERROR] [{i}/{len(uuid_folders)}] Failed "
                f"to process: {component_id}")

    # Summary
    logger.info("=" * 60)
    logger.info("[SUMMARY] PROCESSING SUMMARY")
    logger.info("=" * 60)
    logger.info(f"[FOLDER] Total folders found: {len(uuid_folders)}")
    logger.info(f"[OK] Successfully processed: {successful}")
    logger.info(f"[ERROR] Failed: {failed}")
    success_rate = (successful / len(uuid_folders) * 100) \
        if uuid_folders else 0
    logger.info(f"[STATS] Success rate: {success_rate:.1f}%")
    logger.info("=" * 60)

    return failed == 0


def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(
        description="Process 3D scan data and create CSC components",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python process_robot_scan.py /path/to/scans_to_process /path/to/scans_processed  # NOQA
  python process_robot_scan.py --single /path/to/specific_scan /path/to/scans_processed  # NOQA
        """
    )

    parser.add_argument('input_folder',
                        help='Input folder containing scan data '
                             '(or specific scan folder if --single)')
    parser.add_argument('output_folder',
                        help='Output folder for processed scans')
    parser.add_argument('--single', action='store_true',
                        help='Process a single scan folder instead of all '
                             'folders in input directory')

    args = parser.parse_args()

    logger.info("[START] Starting 3D scan data processing...")
    logger.info(f"[FOLDER] Input: {args.input_folder}")
    logger.info(f"[FOLDER] Output: {args.output_folder}")

    if args.single:
        success = process_single_folder(args.input_folder, args.output_folder)
    else:
        success = process_multiple_folders(
            args.input_folder,
            args.output_folder
        )

    return success


if __name__ == "__main__":
    print("CSC 3D Scan Data Processing Script")
    print("=" * 50)

    success = main()

    if success:
        print("\n[OK] Processing completed successfully!")
    else:
        print(
            "\n[ERROR] Processing completed with errors. "
            "Check logs for details."
        )
        sys.exit(1)
