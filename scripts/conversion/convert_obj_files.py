#!/usr/bin/env python3
"""
Convert OBJ files to new multi-mesh format.

This script processes component geometry folders and:
1. Removes all .mtl files
2. Removes all texture.jpg files
3. Converts .obj files to new format:
   - Remove MTL references
   - Add 'o object_0' notation
   - Ensure v X Y Z R G B format with integer-based (0-255) vertex colors
"""

from pathlib import Path
from typing import List, Tuple


def remove_files_by_extension(directory: Path, extensions: List[str]) -> int:
    """Remove files with specified extensions from directory."""
    removed_count = 0
    for ext in extensions:
        for file_path in directory.glob(f"*.{ext}"):
            try:
                file_path.unlink()
                print(f"  Removed: {file_path.name}")
                removed_count += 1
            except Exception as e:
                print(f"  Error removing {file_path.name}: {e}")
    return removed_count


def normalize_vertex_colors(vertices: List[str]) -> List[str]:
    """Ensure vertex colors are in 0-255 integer format."""
    normalized_vertices = []

    for vertex_line in vertices:
        parts = vertex_line.strip().split()
        if len(parts) >= 7:  # v x y z r g b
            try:
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                r, g, b = float(parts[4]), float(parts[5]), float(parts[6])

                # Normalize colors to 0-255 range if they're in 0-1 range
                if 0 <= r <= 1 and 0 <= g <= 1 and 0 <= b <= 1:
                    r, g, b = int(r * 255), int(g * 255), int(b * 255)
                else:
                    r, g, b = int(r), int(g), int(b)

                # Clamp to valid range
                r = max(0, min(255, r))
                g = max(0, min(255, g))
                b = max(0, min(255, b))

                normalized_line = f"v {x} {y} {z} {r} {g} {b}"
                normalized_vertices.append(normalized_line)
            except (ValueError, IndexError):
                print(f"    Warning: Could not parse vertex line: "
                      f"{vertex_line.strip()}")
                normalized_vertices.append(vertex_line)
        else:
            normalized_vertices.append(vertex_line)

    return normalized_vertices


def convert_obj_file(obj_path: Path) -> bool:
    """Convert a single OBJ file to new format."""
    print(f"  Converting: {obj_path.name}")

    try:
        # Read the file
        with open(obj_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Process lines
        has_object_declaration = False
        vertex_lines = []
        other_lines = []

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                other_lines.append(line)
                continue

            if line.startswith('mtllib') or line.startswith('usemtl'):
                # Skip MTL references
                continue
            elif line.startswith('o '):
                # Object declaration already exists
                has_object_declaration = True
                other_lines.append(line)
            elif (line.startswith('v ') and not line.startswith('vt ') and
                  not line.startswith('vn ')):
                # Vertex line - collect for processing
                vertex_lines.append(line)
            else:
                # All other lines (faces, normals, etc.)
                other_lines.append(line)

        # Normalize vertex colors
        normalized_vertices = normalize_vertex_colors(vertex_lines)

        # Build converted content
        converted_content = []

        # Add header comment
        converted_content.append("# OBJ file converted to multi-mesh format")
        converted_content.append("")

        # Add object declaration if not present
        if not has_object_declaration:
            converted_content.append("o object_0")
        else:
            # Find existing object declaration and replace with object_0
            for line in other_lines:
                if line.startswith('o '):
                    converted_content.append("o object_0")
                else:
                    converted_content.append(line)

        # Add normalized vertices
        converted_content.extend(normalized_vertices)

        # Add other lines (faces, normals, etc.)
        for line in other_lines:
            if not line.startswith('o '):  # Skip old object declarations
                converted_content.append(line)

        # Write back to file
        with open(obj_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(converted_content))

        print(f"    ✓ Converted {len(normalized_vertices)} vertices")
        return True

    except Exception as e:
        print(f"    ✗ Error converting {obj_path.name}: {e}")
        return False


def process_component_directory(component_dir: Path) -> Tuple[int, int, int]:
    """Process a single component directory."""
    print(f"Processing: {component_dir.name}")

    # Count files before processing
    mtl_files = list(component_dir.glob("*.mtl"))
    texture_files = list(component_dir.glob("texture.jpg"))
    obj_files = list(component_dir.glob("*.obj"))

    print(f"  Found: {len(mtl_files)} MTL files, {len(texture_files)} "
          f"texture files, {len(obj_files)} OBJ files")

    # Remove MTL files
    removed_mtl = remove_files_by_extension(component_dir, ['mtl'])

    # Remove texture files
    removed_textures = remove_files_by_extension(
        component_dir, ['jpg', 'jpeg', 'png'])

    # Convert OBJ files
    converted_objs = 0
    for obj_file in obj_files:
        if convert_obj_file(obj_file):
            converted_objs += 1

    return removed_mtl, removed_textures, converted_objs


def main():
    """Main conversion function."""
    # Get the component_geometry directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    geometry_dir = project_root / "component_geometry" / "250905"

    if not geometry_dir.exists():
        print(f"Error: Geometry directory not found: {geometry_dir}")
        return

    print(f"Converting OBJ files in: {geometry_dir}")
    print("=" * 60)

    total_mtl_removed = 0
    total_textures_removed = 0
    total_objs_converted = 0
    processed_dirs = 0

    # Process each component directory
    for component_dir in sorted(geometry_dir.iterdir()):
        if component_dir.is_dir():
            try:
                mtl_removed, textures_removed, objs_converted = (
                    process_component_directory(component_dir))
                total_mtl_removed += mtl_removed
                total_textures_removed += textures_removed
                total_objs_converted += objs_converted
                processed_dirs += 1
                print()
            except Exception as e:
                print(f"Error processing {component_dir.name}: {e}")
                print()

    # Summary
    print("=" * 60)
    print("CONVERSION SUMMARY")
    print("=" * 60)
    print(f"Processed directories: {processed_dirs}")
    print(f"MTL files removed: {total_mtl_removed}")
    print(f"Texture files removed: {total_textures_removed}")
    print(f"OBJ files converted: {total_objs_converted}")
    print()
    print("✓ Conversion complete!")


if __name__ == "__main__":
    main()
