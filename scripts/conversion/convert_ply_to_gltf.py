#!/usr/bin/env python3
"""
Convert PLY files to GLTF format for fast loading in Three.js
"""

import os
import sys
import glob
from pathlib import Path
import trimesh
import json

# Component IDs to process
COMPONENT_IDS = [
    "0aad9436-ead8-4651-81a1-8b435012d799",
    "0dd38d21-87ea-4c1d-a0b8-7245b45cd633", 
    "153b9ae8-f858-4e8f-a7c2-bbec658c4a60",
    "eb011945-0315-449c-8117-c4e1e4292c9b",
    "c4dfa0c4-4691-4dbb-a834-62240e3e4972",
    "b9521122-5d01-4392-bd51-026b9cc5fbf0",
    "6dc08bb0-4ae3-42e6-8cd9-23b49f624706"
]

# Source and destination paths
SOURCE_DIR = r"D:\02_DATASETS\geometry-features-v1\meshes\original\components"
DEST_DIR = r"C:\Users\EFESTWIN\source\repos\csc\src\frontend\public\meshes"

def convert_ply_to_gltf(ply_path, output_path):
    """Convert a PLY file to GLTF format"""
    try:
        # Load the PLY file
        mesh = trimesh.load(ply_path)
        
        # Ensure it's a single mesh (not a scene)
        if hasattr(mesh, 'geometry'):
            mesh = mesh
        elif hasattr(mesh, 'meshes'):
            # If it's a scene, get the first mesh
            mesh = list(mesh.geometry.values())[0]
        
        # Normalize the mesh to fit in a unit cube for consistent scaling
        mesh.vertices = mesh.vertices - mesh.centroid
        scale = 1.0 / mesh.scale
        mesh.vertices = mesh.vertices * scale
        
        # Simplify the mesh to 33% of original polygons
        target_faces = int(len(mesh.faces) * 0.33)
        if target_faces > 0:
            mesh = mesh.simplify_quadric_decimation(face_count=target_faces)
        
        # Export as GLB (binary GLTF - self-contained)
        output_path = output_path.replace('.gltf', '.glb')
        mesh.export(output_path, file_type='glb')
        print(f"[OK] Converted: {os.path.basename(ply_path)} -> {os.path.basename(output_path)}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Error converting {ply_path}: {e}")
        return False

def main():
    """Main conversion function"""
    print("Converting PLY files to GLTF format...")
    print(f"Source: {SOURCE_DIR}")
    print(f"Destination: {DEST_DIR}")
    print("-" * 50)
    
    # Create destination directory
    os.makedirs(DEST_DIR, exist_ok=True)
    
    converted_count = 0
    total_count = len(COMPONENT_IDS)
    
    for component_id in COMPONENT_IDS:
        # Look for reduced PLY files directly in the components directory
        ply_pattern = os.path.join(SOURCE_DIR, f"{component_id}_reduced.ply")
        ply_files = [ply_pattern] if os.path.exists(ply_pattern) else []
        
        if not ply_files:
            print(f"[ERROR] No reduced PLY file found for {component_id}")
            continue
            
        ply_path = ply_files[0]  # Take the first match
        output_path = os.path.join(DEST_DIR, f"{component_id}_reduced.glb")
        
        if convert_ply_to_gltf(ply_path, output_path):
            converted_count += 1
    
    print("-" * 50)
    print(f"Conversion complete: {converted_count}/{total_count} files converted")
    
    # Create a manifest file with metadata
    manifest = {
        "meshes": [
            {
                "id": component_id,
                "filename": f"{component_id}_reduced.glb",
                "type": "reduced"
            }
            for component_id in COMPONENT_IDS
        ],
        "total_count": converted_count,
        "converted_at": str(Path().cwd())
    }
    
    manifest_path = os.path.join(DEST_DIR, "manifest.json")
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    print(f"[OK] Manifest created: {manifest_path}")

if __name__ == "__main__":
    main()
