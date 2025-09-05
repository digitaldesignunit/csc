#!/usr/bin/env python3
"""
3D Scan Data Processing Script

This script processes 3D scan result data from the scans_to_process folder
and creates CSC components with proper geometry structure.

Usage:
    python scripts/process_scan_data.py

Requirements:
    - trimesh
    - numpy
"""

import os
import sys
import json
import uuid
from datetime import datetime
from typing import List, Dict, Tuple
import numpy as np
import logging

try:
    import trimesh
except ImportError:
    print("Error: trimesh library required. Install with: pip install trimesh")
    sys.exit(1)

# Setup logging
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
                    # Position
                    x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                    vertex = [x, y, z]
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
                        target_faces: int) -> Tuple[np.ndarray, np.ndarray]:
    """Reduce mesh using trimesh library"""
    try:
        # Create trimesh object
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces)

        # Calculate reduction ratio
        current_faces = len(faces)
        if current_faces <= target_faces:
            return vertices, faces

        # Simplify mesh
        simplified = mesh.simplify_quadric_decimation(
            face_count=target_faces
        )

        return simplified.vertices, simplified.faces

    except Exception as e:
        logger.warning(f"Mesh reduction failed: {e}, using original mesh")
        return vertices, faces


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
                    f.write(f"v {vertex[0]} {vertex[1]} {vertex[2]} "
                            f"{color[0]} {color[1]} {color[2]}\n")
                else:
                    f.write(f"v {vertex[0]} {vertex[1]} {vertex[2]} "
                            f"255 255 255\n")

            # Write faces (adjust for global vertex offset)
            for face in mesh_data['f']:
                face_str = " ".join(str(idx + 1 + vertex_offset)
                                    for idx in face)
                f.write(f"f {face_str}\n")

            vertex_offset += len(vertices)


def process_scan_folder(scan_folder: str, component_id: str) -> bool:
    """Process a single scan folder"""
    logger.info(f"🔧 Processing scan folder: {component_id}")

    # Paths
    metadata_path = os.path.join(scan_folder, 'metadata.json')
    output_folder = os.path.join(scan_folder, 'output')
    aligned_mesh_path = os.path.join(output_folder, 'aligned_mesh.obj')
    transcode_folder = os.path.join(scan_folder, 'transcode')

    logger.info("📁 Folder structure:")
    logger.info(f"   📄 Metadata: {os.path.basename(metadata_path)}")
    logger.info(f"   📁 Output: {os.path.basename(output_folder)}")
    logger.info("   🎯 Target: transcode/")

    # Create transcode folder
    logger.info("📁 Creating transcode folder...")
    os.makedirs(transcode_folder, exist_ok=True)

    # Check required files
    logger.info("🔍 Checking required files...")
    if not os.path.exists(metadata_path):
        logger.error(f"❌ Missing metadata.json in {component_id}")
        return False
    logger.info("✅ Found metadata.json")

    if not os.path.exists(aligned_mesh_path):
        logger.error(f"❌ Missing aligned_mesh.obj in {component_id}")
        return False
    logger.info("✅ Found aligned_mesh.obj")

    try:
        # Load metadata
        logger.info("📖 Loading metadata.json...")
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        logger.info(f"✅ Metadata loaded: {len(metadata)} keys")

        # Parse OBJ file
        logger.info("🔍 Parsing aligned_mesh.obj...")
        obj_data = parse_obj_with_objects(aligned_mesh_path)
        objects = obj_data['objects']
        marker_points = obj_data['marker_points']

        logger.info("📊 OBJ parsing results:")
        logger.info(f"   🎯 Objects found: {list(objects.keys())}")
        logger.info(f"   📍 Marker points: {len(marker_points)}")

        # Check for required objects
        if 'object' not in objects:
            logger.error(f"❌ Missing 'object' in OBJ file for {component_id}")
            return False
        obj_verts = len(objects['object']['vertices'])
        obj_faces = len(objects['object']['faces'])
        logger.info(f"✅ Main object found: {obj_verts} vertices, "
                    f"{obj_faces} faces")

        if 'end_effector' not in objects:
            logger.warning(f"⚠️ Missing 'end_effector' in OBJ "
                           f"for {component_id}")
        else:
            ee_verts = len(objects['end_effector']['vertices'])
            ee_faces = len(objects['end_effector']['faces'])
            logger.info(f"✅ End effector found: {ee_verts} vertices, "
                        f"{ee_faces} faces")

        # Prepare meshes (object first, end_effector second)
        logger.info("🔄 Processing meshes...")
        meshes_data = []
        primitive_meshes = []

        # Process 'object' mesh (first)
        logger.info("🎯 Processing main object mesh...")
        obj_mesh = objects['object']
        if obj_mesh['vertices'] and obj_mesh['faces']:
            orig_verts = len(obj_mesh['vertices'])
            orig_faces = len(obj_mesh['faces'])
            logger.info(f"   📊 Original: {orig_verts} vertices, "
                        f"{orig_faces} faces")
            mesh_data = create_mesh_data(
                obj_mesh['vertices'],
                obj_mesh['colors'],
                obj_mesh['faces']
            )
            meshes_data.append(mesh_data)

            # Create primitive version
            logger.info("   🔧 Creating primitive version...")
            vertices_array = np.array(obj_mesh['vertices'])
            triangulated = [triangulate_face(f)[0] for f in obj_mesh['faces']
                            if len(f) >= 3]
            faces_array = np.array(triangulated)

            if len(faces_array) > 350:
                logger.info(f"   ⚡ Reducing from {len(faces_array)} "
                            f"to 350 faces...")
                prim_vertices, prim_faces = reduce_mesh_trimesh(
                    vertices_array, faces_array, 350
                )
                primitive_mesh = create_mesh_data(
                    prim_vertices.tolist(),
                    [[255, 255, 255]] * len(prim_vertices),
                    prim_faces.tolist()
                )
                logger.info(f"   ✅ Reduced to {len(prim_faces)} faces")
            else:
                logger.info(f"   ✅ Mesh already small "
                            f"enough ({len(faces_array)} faces)")
                primitive_mesh = mesh_data.copy()

            primitive_meshes.append(primitive_mesh)

        # Process 'end_effector' mesh (second)
        if 'end_effector' in objects:
            logger.info("🔧 Processing end_effector mesh...")
            ee_mesh = objects['end_effector']
            if ee_mesh['vertices'] and ee_mesh['faces']:
                logger.info(f"   📊 Original: {len(ee_mesh['vertices'])} "
                            f"vertices, {len(ee_mesh['faces'])} faces")
                mesh_data = create_mesh_data(
                    ee_mesh['vertices'],
                    ee_mesh['colors'],
                    ee_mesh['faces']
                )
                meshes_data.append(mesh_data)

                # Create primitive version
                logger.info("   🔧 Creating primitive version...")
                vertices_array = np.array(ee_mesh['vertices'])
                triangulated = [triangulate_face(f)[0]
                                for f in ee_mesh['faces'] if len(f) >= 3]
                faces_array = np.array(triangulated)

                if len(faces_array) > 350:
                    logger.info(f"   ⚡ Reducing from {len(faces_array)} "
                                f"to 350 faces...")
                    prim_vertices, prim_faces = reduce_mesh_trimesh(
                        vertices_array, faces_array, 350
                    )
                    primitive_mesh = create_mesh_data(
                        prim_vertices.tolist(),
                        [[255, 255, 255]] * len(prim_vertices),
                        prim_faces.tolist()
                    )
                    logger.info(f"   ✅ Reduced to {len(prim_faces)} faces")
                else:
                    logger.info(f"   ✅ Mesh already small enough "
                                f"({len(faces_array)} faces)")
                    primitive_mesh = mesh_data.copy()

                primitive_meshes.append(primitive_mesh)
            else:
                logger.info("   ⚠️ End effector has no geometry")

        if not meshes_data:
            logger.error(f"❌ No valid meshes found for {component_id}")
            return False

        logger.info(f"✅ Processed {len(meshes_data)} meshes total")

        # Save OBJ files
        logger.info("💾 Saving OBJ files...")
        mesh_obj_path = os.path.join(transcode_folder, 'mesh.obj')
        logger.info("   📄 Detailed mesh: mesh.obj")
        save_combined_obj_file(meshes_data, mesh_obj_path)

        # Create reduced OBJ if needed (check if any mesh has > 5000 faces)
        face_counts = [len(mesh['f']) for mesh in meshes_data]
        needs_reduced = any(count > 5000 for count in face_counts)
        logger.info(f"🔍 Face counts: {face_counts}")

        if needs_reduced:
            logger.info("⚡ Creating reduced mesh version "
                        "(>5000 faces detected)...")
            reduced_meshes = []
            for i, mesh_data in enumerate(meshes_data):
                mesh_faces = len(mesh_data['f'])
                if mesh_faces > 5000:
                    logger.info(f"   🔧 Reducing mesh {i+1}: {mesh_faces} "
                                "→ 1000 faces")
                    # Create reduced version
                    vertices_array = np.array(mesh_data['v'])
                    faces_array = np.array(mesh_data['f'])

                    reduced_vertices, reduced_faces = reduce_mesh_trimesh(
                        vertices_array, faces_array, 1000
                    )

                    color_count = len(reduced_vertices)
                    if len(mesh_data['c']) >= color_count:
                        colors = mesh_data['c'][:color_count]
                    else:
                        colors = [[255, 255, 255]] * color_count

                    reduced_mesh = create_mesh_data(
                        reduced_vertices.tolist(),
                        colors,
                        reduced_faces.tolist()
                    )
                    reduced_meshes.append(reduced_mesh)
                    logger.info(f"   ✅ Mesh {i+1} reduced "
                                f"to {len(reduced_faces)} faces")
                else:
                    logger.info(f"   ✅ Mesh {i+1} kept "
                                f"original ({mesh_faces} faces)")
                    reduced_meshes.append(mesh_data)

            mesh_reduced_path = os.path.join(transcode_folder,
                                             'mesh_reduced.obj')
            logger.info("   📄 Reduced mesh: mesh_reduced.obj")
            save_combined_obj_file(reduced_meshes, mesh_reduced_path)
        else:
            logger.info("✅ No reduction needed (all meshes < 5000 faces)")

        # Create component JSON
        logger.info("📝 Creating component JSON...")
        current_time = datetime.utcnow().isoformat() + 'Z'

        # Calculate bounding box from original meshes (not primitive)
        bounding_box = calculate_bounding_box(meshes_data)
        logger.info(f"📏 Bounding box: "
                    f"[{bounding_box[0]:.3f}, {bounding_box[1]:.3f}, "
                    f"{bounding_box[2]:.3f}]")

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
        logger.info(f"💾 Saving component JSON: {component_id}.json")
        with open(component_json_path, 'w') as f:
            json.dump(component_data, f, indent=2)

        # Summary
        logger.info(f"🎉 Successfully processed component: {component_id}")
        logger.info("📊 Summary:")
        logger.info(f"   🎯 Meshes processed: {len(meshes_data)}")
        logger.info(f"   🔧 Primitive meshes: {len(primitive_meshes)}")
        logger.info(f"   📍 Marker points: {len(marker_points)}")
        logger.info(f"   📏 Bounding box: {bounding_box}")
        logger.info("   ⚡ Reduced OBJ:"
                    f" {'Created' if needs_reduced else 'Not needed'}")
        logger.info("   📂 Output files:")
        logger.info("      📄 mesh.obj")
        if needs_reduced:
            logger.info("      📄 mesh_reduced.obj")
        logger.info(f"      📄 {component_id}.json")

        return True

    except Exception as e:
        logger.error(f"Error processing {component_id}: {e}")
        return False


def main():
    """Main processing function"""
    logger.info("🚀 Starting 3D scan data processing...")

    # Define paths
    scans_folder = os.path.abspath(
        os.path.join('..', 'component_geometry', 'scans_to_process'))

    logger.info(f"📂 Scanning folder: {scans_folder}")

    if not os.path.exists(scans_folder):
        logger.error(f"❌ Scans folder does not exist: {scans_folder}")
        return False

    # Find UUID folders
    logger.info("🔍 Searching for UUID-named directories...")
    all_items = os.listdir(scans_folder)
    logger.info(f"📋 Found {len(all_items)} items in directory")

    uuid_folders = []
    for item in all_items:
        item_path = os.path.join(scans_folder, item)
        if os.path.isdir(item_path):
            if validate_uuid(item):
                uuid_folders.append((item_path, item))
                logger.info(f"✅ Valid UUID folder: {item}")
            else:
                logger.info(f"⚠️ Invalid UUID folder (skipping): {item}")
        else:
            logger.info(f"📄 File (skipping): {item}")

    if not uuid_folders:
        logger.warning("🔍 No UUID folders found in scans_to_process")
        return True

    logger.info(f"🎯 Processing {len(uuid_folders)} scan folders")

    # Process each folder
    successful = 0
    failed = 0

    for i, (folder_path, component_id) in enumerate(uuid_folders, 1):
        logger.info(f"📦 [{i}/{len(uuid_folders)}] Processing: {component_id}")
        if process_scan_folder(folder_path, component_id):
            successful += 1
            logger.info(f"✅ [{i}/{len(uuid_folders)}] Success: {component_id}")
        else:
            failed += 1
            logger.error(f"❌ [{i}/{len(uuid_folders)}] Failed: {component_id}")

    # Summary
    logger.info("=" * 60)
    logger.info("🏁 PROCESSING SUMMARY")
    logger.info("=" * 60)
    logger.info(f"📂 Total folders found: {len(uuid_folders)}")
    logger.info(f"✅ Successfully processed: {successful}")
    logger.info(f"❌ Failed: {failed}")
    success_rate = (successful / len(uuid_folders) * 100) \
        if uuid_folders else 0
    logger.info(f"📊 Success rate: {success_rate:.1f}%")
    logger.info("=" * 60)

    return failed == 0


if __name__ == "__main__":
    print("CSC 3D Scan Data Processing Script")
    print("=" * 50)

    success = main()

    if success:
        print("\nProcessing completed successfully!")
    else:
        print("\nProcessing completed with errors. Check logs for details.")
        sys.exit(1)
