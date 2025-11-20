#!/usr/bin/env python3
'''
Maintenance helper to rotate archived component geometry, recompute
PCA frames, and export corrected assets.
'''

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from src.py_modules.csc_robot_rubble_scan_processing.process_robot_scan import (  # noqa:E402
    MESH_PRIMITIVE_TARGET,
    MESH_PRIMITIVE_THRESHOLD,
    MESH_REDUCED_TARGET,
    MESH_REDUCED_THRESHOLD,
    compute_obb_3d,
    create_mesh_data,
    reduce_mesh_trimesh,
    triangulate_face,
)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


BACKUP_ROOT = Path(r'D:\01_PROJECT_WORKDATA\component_geometry_backup')
OUTPUT_ROOT = Path(r'D:\01_PROJECT_WORKDATA\component_geometry_corrected')


UUIDS_TO_PROCESS = [
    '2f6fb18a-ced0-4eed-8c04-7277f92e0da6',
    '4ac1eca2-7ee3-43c1-830f-1935de6af9a2',
    '5d94abb6-b510-4e6d-ad71-3e2b630c7059',
    '8aef8f4e-17b7-4070-b41c-8a58ce05513b',
    '8d5ca5b1-80cf-4838-9d65-91b227e23a27',
    '9a8867d5-8ea5-4a6a-81e4-68c098a9986d',
    '9b778345-4ff4-4f3e-898e-7a8daf4aaf59',
    '9d91815e-6850-460d-b2f3-cfde9ee4ea5c',
    '47b7a2e7-7e4b-4397-96b5-b62d9f8d0e8f',
    '86c9422b-8108-460a-8fad-d967806fae3a',
    '89f7758b-35b8-4977-9419-601de8877061',
    '690c1bf2-13c5-4a37-90d8-979c5a4f93ed',
    '9265e1dc-59a7-4156-9203-06b4d9db11d0',
    '82727cca-2ddb-45b9-8d2b-c56dddf28e14',
    'a7b1250e-0973-4229-9fe7-208e15d5ee7d',
    'b59185c4-df44-4c59-a369-c66a695ba35a',
    'c4cbb4e5-73c5-4a46-8c91-22b522fdb49f',
    'c8fed763-c72c-436b-8b3c-61176bf6f228',
    'c182b059-77b0-4367-b58c-1c5eb2361cae',
    'ca9026b9-ceec-40a8-a7ca-1fd47d9771ca',
    'da578850-0da9-4e6e-bfdc-1d84e63290aa',
    'db9b2961-32db-4b76-83b4-53c784f37c41',
    'df337ab4-5485-4e44-8f07-bc99e96364b3',
    'f9292ef6-b37a-41c7-81bb-0562151e958d',
]


ROTATION_MATRIX = np.array(
    [
        [1.0, 0.0, 0.0],
        [0.0, -1.0, 0.0],
        [0.0, 0.0, -1.0],
    ]
)


def parse_obj_without_axis_swaps(obj_path: str) -> Dict[str, Dict]:
    objects: Dict[str, Dict] = {}
    marker_points: List[List[float]] = []
    current_object = None
    global_vertices: List[List[float]] = []

    with open(obj_path, 'r', encoding='utf-8') as obj_file:
        for raw_line in obj_file:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith('o '):
                object_name = line[2:].strip()
                current_object = object_name
                if current_object not in objects:
                    objects[current_object] = {
                        'vertices': [],
                        'colors': [],
                        'faces': [],
                        'vertex_offset': len(global_vertices),
                    }
            elif line.startswith('v '):
                parts = line[2:].split()
                if len(parts) < 3:
                    continue
                x, y, z = map(float, parts[:3])
                vertex = [x, y, z]
                global_vertices.append(vertex)
                if len(parts) >= 6:
                    r, g, b = map(float, parts[3:6])
                    color = [r, g, b]
                else:
                    color = [1.0, 1.0, 1.0]
                if current_object and current_object in objects:
                    if current_object == 'marker_points':
                        marker_points.append(vertex)
                    else:
                        objects[current_object]['vertices'].append(vertex)
                        objects[current_object]['colors'].append(color)
            elif line.startswith('f '):
                if not current_object or current_object not in objects:
                    continue
                if current_object == 'marker_points':
                    continue
                face_tokens = line[2:].split()
                face: List[int] = []
                for token in face_tokens:
                    vertex_idx = int(token.split('/')[0]) - 1
                    offset = objects[current_object]['vertex_offset']
                    local_idx = vertex_idx - offset
                    face.append(local_idx)
                if len(face) >= 3:
                    objects[current_object]['faces'].append(face)

    return {'objects': objects, 'marker_points': marker_points}


def rotate_vertices(vertices: np.ndarray) -> np.ndarray:
    if vertices.size == 0:
        return vertices
    return (ROTATION_MATRIX @ vertices.T).T


def rotate_for_viewer(vertices: np.ndarray) -> np.ndarray:
    """
    Apply +90° X rotation to compensate for viewer's -90° X rotation.
    Viewer applies rotateX(-Math.PI/2), so we pre-apply rotateX(+Math.PI/2).
    Rotation matrix for +90° about X: [[1,0,0], [0,0,-1], [0,1,0]]
    """
    if vertices.size == 0:
        return vertices
    viewer_compensation = np.array([
        [1.0, 0.0, 0.0],
        [0.0, 0.0, -1.0],
        [0.0, 1.0, 0.0],
    ])
    return (viewer_compensation @ vertices.T).T


def build_mesh_data(mesh_obj: Dict) -> Dict:
    mesh_data = create_mesh_data(
        mesh_obj['vertices'],
        mesh_obj['colors'],
        mesh_obj['faces'],
    )
    return mesh_data


def convert_mesh_for_viewer(mesh_data: Dict) -> Dict:
    vertices = np.array(mesh_data['v'], dtype=float)
    if vertices.size == 0:
        return mesh_data
    converted = mesh_data.copy()
    vertices[:, [1, 2]] = vertices[:, [2, 1]]
    vertices[:, 2] = -vertices[:, 2]
    converted['v'] = vertices.tolist()
    return converted


def build_primitive_mesh(mesh_obj: Dict) -> Dict:
    vertices_array = np.array(mesh_obj['vertices'])
    triangulated = [
        triangulate_face(face)[0]
        for face in mesh_obj['faces']
        if len(face) >= 3
    ]
    if not triangulated:
        viewer_vertices = rotate_for_viewer(vertices_array)
        temp_mesh = mesh_obj.copy()
        temp_mesh['vertices'] = viewer_vertices.tolist()
        return build_mesh_data(temp_mesh)
    faces_array = np.array(triangulated)
    if len(faces_array) <= MESH_PRIMITIVE_THRESHOLD:
        viewer_vertices = rotate_for_viewer(vertices_array)
        temp_mesh = mesh_obj.copy()
        temp_mesh['vertices'] = viewer_vertices.tolist()
        return build_mesh_data(temp_mesh)
    primitive_vertices, primitive_faces, primitive_colors = reduce_mesh_trimesh(
        vertices_array,
        faces_array,
        MESH_PRIMITIVE_TARGET,
        np.array(mesh_obj['colors']),
    )
    viewer_vertices = rotate_for_viewer(primitive_vertices)
    return create_mesh_data(
        viewer_vertices.tolist(),
        primitive_colors.tolist(),
        primitive_faces.tolist(),
    )


def compute_pca_for_mesh(vertices: List[List[float]]) -> Tuple[List[float], np.ndarray, List[float], np.ndarray]:
    if not vertices:
        return (
            [1.0, 1.0, 1.0],
            np.eye(3),
            [0.0, 0.0, 0.0],
            np.zeros(3),
        )
    pca_vertices = np.array(vertices)
    centroid = np.mean(pca_vertices, axis=0)
    centered_vertices = pca_vertices - centroid
    dimensions, principal_components, bbx_origin = compute_obb_3d(centered_vertices)
    return (
        dimensions,
        principal_components,
        bbx_origin,
        centroid,
    )


def ensure_output_folder(component_id: str) -> Path:
    target_folder = OUTPUT_ROOT / component_id
    target_folder.mkdir(parents=True, exist_ok=True)
    return target_folder


def create_reduced_meshes(meshes_data: List[Dict]) -> List[Dict]:
    reduced_meshes = []
    for mesh_data in meshes_data:
        face_count = len(mesh_data['f'])
        if face_count <= MESH_REDUCED_THRESHOLD:
            reduced_meshes.append(mesh_data)
            continue
        vertices_array = np.array(mesh_data['v'])
        faces_array = np.array(mesh_data['f'])
        reduced_vertices, reduced_faces, reduced_colors = reduce_mesh_trimesh(
            vertices_array,
            faces_array,
            MESH_REDUCED_TARGET,
            np.array(mesh_data['c']),
        )
        reduced_meshes.append(
            create_mesh_data(
                reduced_vertices.tolist(),
                reduced_colors.tolist(),
                reduced_faces.tolist(),
            )
        )
    return reduced_meshes


def save_obj_without_axis_swaps(meshes_data: List[Dict], filepath: Path) -> None:
    with filepath.open('w', encoding='utf-8') as obj_file:
        vertex_offset = 0
        for index, mesh_data in enumerate(meshes_data):
            obj_file.write(f'o object_{index}\n')
            vertices = mesh_data['v']
            colors = mesh_data['c']
            for vertex_index, vertex in enumerate(vertices):
                if vertex_index < len(colors):
                    color = colors[vertex_index]
                else:
                    color = [255, 255, 255]
                obj_file.write(
                    f'v {vertex[0]} {vertex[1]} {vertex[2]} '
                    f'{color[0]} {color[1]} {color[2]}\n'
                )
            for face in mesh_data['f']:
                indices = ' '.join(str(idx + 1 + vertex_offset) for idx in face)
                obj_file.write(f'f {indices}\n')
            vertex_offset += len(vertices)


def process_component(component_id: str) -> bool:
    source_folder = BACKUP_ROOT / component_id
    obj_path = source_folder / 'mesh.obj'
    if not obj_path.exists():
        logger.error('[%s] Missing mesh.obj at %s', component_id, obj_path)
        return False
    logger.info('[%s] Loading %s', component_id, obj_path)
    obj_data = parse_obj_without_axis_swaps(str(obj_path))
    objects = obj_data['objects']
    if not objects:
        logger.error('[%s] No mesh objects found', component_id)
        return False
    marker_points = []
    for mesh in objects.values():
        raw_vertices = np.array(mesh['vertices'])
        rotated_vertices = rotate_vertices(raw_vertices)
        mesh['vertices'] = rotated_vertices.tolist()
    ordered_mesh_items = list(objects.items())
    meshes_data = []
    primitive_meshes = []
    for name, mesh in ordered_mesh_items:
        if not mesh['vertices'] or not mesh['faces']:
            logger.warning('[%s] Mesh "%s" has no geometry, skipping', component_id, name)
            continue
        meshes_data.append(build_mesh_data(mesh))
        primitive_meshes.append(build_primitive_mesh(mesh))
    if not meshes_data:
        logger.error('[%s] No valid meshes after rotation', component_id)
        return False
    pca_source_vertices = ordered_mesh_items[0][1]['vertices']
    pca_source_array = np.array(pca_source_vertices)
    viewer_adjusted_vertices = rotate_for_viewer(pca_source_array)
    bbox_dims, principal_components, bbx_origin, translation = compute_pca_for_mesh(
        viewer_adjusted_vertices.tolist(),
    )
    output_folder = ensure_output_folder(component_id)
    detailed_obj_path = output_folder / 'mesh.obj'
    save_obj_without_axis_swaps(meshes_data, detailed_obj_path)
    reduced_needed = any(len(mesh['f']) > MESH_REDUCED_THRESHOLD for mesh in meshes_data)
    if reduced_needed:
        reduced_meshes = create_reduced_meshes(meshes_data)
        reduced_obj_path = output_folder / 'mesh_reduced.obj'
        save_obj_without_axis_swaps(reduced_meshes, reduced_obj_path)
    component_json = {
        '_id': component_id,
        'geometry': {
            'meshes': primitive_meshes,
        },
        'bbx': bbox_dims,
        'bbx_origin': bbx_origin,
        'pca_frame': {
            'o': translation.tolist(),
            'x': principal_components[0].tolist(),
            'y': principal_components[1].tolist(),
            'z': principal_components[2].tolist(),
        },
    }
    component_json_path = output_folder / f'{component_id}.json'
    with component_json_path.open('w', encoding='utf-8') as f:
        json.dump(component_json, f, indent=2)
    logger.info('[%s] Corrected assets saved to %s', component_id, output_folder)
    return True


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    success_count = 0
    for component_id in UUIDS_TO_PROCESS:
        try:
            success = process_component(component_id.strip())
        except Exception as exc:
            logger.exception('[%s] Failed with error: %s', component_id, exc)
            success = False
        if success:
            success_count += 1
    logger.info('Completed %s/%s components', success_count, len(UUIDS_TO_PROCESS))


if __name__ == '__main__':
    main()

