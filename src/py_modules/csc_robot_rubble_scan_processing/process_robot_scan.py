#!/usr/bin/env python3
"""
Robot Scan Data Processing Module

Processes aligned 3D scan meshes into a CSC CreateComponentRequest:

* Identity ``_id`` is the UUID folder name
* Geometry becomes the version-0 snapshot (inline primitives + staged PLY)

Programmatic Usage:
    from process_robot_scan import process_scan_by_path
    success = process_scan_by_path('/path/to/uuid-folder')
"""

import os
import sys
import json
import uuid
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Limit native thread pools before importing numpy/scipy/trimesh.
# Unbounded OpenMP/MKL workers can crash this script in constrained shells.
for _thread_env in (
    'OMP_NUM_THREADS',
    'MKL_NUM_THREADS',
    'OPENBLAS_NUM_THREADS',
    'NUMEXPR_NUM_THREADS',
    'VECLIB_MAXIMUM_THREADS',
    'BLIS_NUM_THREADS',
):
    os.environ.setdefault(_thread_env, '1')

import numpy as np
import trimesh
from scipy.spatial import cKDTree
from PIL import Image

# MESH REDUCTION SETTINGS
# If mesh has face count above this but below reduced threshold,
# only the primitive version will be computed
MESH_PRIMITIVE_THRESHOLD = 8000
# If mesh has face count above this, reduced and primitive versions
# will be created
MESH_REDUCED_THRESHOLD = 15000
# Target face count for reduced mesh
MESH_REDUCED_TARGET = 10000
# Target face count for primitive mesh (inline snapshot geometry)
MESH_PRIMITIVE_TARGET = 500

# DATASET / IDENTITY DEFAULTS
DATASET_NAME = "ddu_build_with_debris"
COMPONENT_TYPE = "rubble"
COMPONENT_MATERIAL = "concrete"
COMPONENT_COLOR = [110, 110, 110]
COMPONENT_LOCATION = {"lat": 49.861444, "lon": 8.676556}

# OBJ object names written by scan postprocess
MESH_OBJECT_STONE = "object"
MESH_OBJECT_EFFECTOR = "end_effector"
LEGACY_MARKER_OBJECT = "marker_points"
MARKER_OBJECT_PREFIX = "marker_"

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
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass


def validate_uuid(uuid_string: str) -> bool:
    """Validate if string is a valid UUID"""
    try:
        uuid_obj = uuid.UUID(uuid_string)
        return str(uuid_obj) == uuid_string.lower()
    except ValueError:
        return False


def identity_frame() -> Dict[str, List[float]]:
    """World-aligned frame at the origin (create-time iframe default)."""
    return {
        'o': [0.0, 0.0, 0.0],
        'x': [1.0, 0.0, 0.0],
        'y': [0.0, 1.0, 0.0],
        'z': [0.0, 0.0, 1.0],
    }


def obj_yup_to_rhino_zup(vertex: List[float]) -> List[float]:
    """Map a legacy Y-up OBJ vertex to Rhino Z-up (CSC canonical)."""
    x, y, z = vertex
    return [x, -z, y]


def normalize_colors_to_integers(colors: np.ndarray) -> np.ndarray:
    """Convert color values to integer RGB (0-255)."""
    if colors.size == 0:
        return colors.astype(int)
    if colors.max() > 1.0:
        return np.clip(colors, 0, 255).astype(int)
    return np.clip(colors * 255, 0, 255).astype(int)


def _is_marker_object(name: str) -> bool:
    if not name:
        return False
    if name == LEGACY_MARKER_OBJECT:
        return True
    return name.startswith(MARKER_OBJECT_PREFIX)


def _obj_index(raw: int, count: int) -> int:
    """Convert a 1-based (or negative relative) OBJ index to 0-based."""
    if raw < 0:
        return count + raw
    return raw - 1


def _parse_map_kd(mtl_path: str) -> Optional[str]:
    """Return the first map_Kd texture filename from an MTL file."""
    if not os.path.isfile(mtl_path):
        return None
    with open(mtl_path, 'r', encoding='utf-8', errors='replace') as handle:
        for raw in handle:
            stripped = raw.strip()
            if stripped.lower().startswith('map_kd '):
                value = stripped.split(None, 1)[1].strip().strip('"')
                return value or None
    return None


def resolve_diffuse_texture_path(
    obj_path: str,
    mtllib_files: List[str],
) -> Optional[str]:
    """Find the diffuse texture next to the OBJ / referenced MTL."""
    obj_dir = os.path.dirname(os.path.abspath(obj_path))
    candidates: List[str] = []
    for mtl_name in mtllib_files:
        mtl_path = (
            mtl_name if os.path.isabs(mtl_name)
            else os.path.join(obj_dir, mtl_name)
        )
        map_kd = _parse_map_kd(mtl_path)
        if map_kd:
            tex_path = (
                map_kd if os.path.isabs(map_kd)
                else os.path.join(os.path.dirname(mtl_path), map_kd)
            )
            candidates.append(tex_path)
    for name in ('mesh.jpg', 'mesh.jpeg', 'mesh.png'):
        candidates.append(os.path.join(obj_dir, name))
    seen = set()
    for path in candidates:
        normalized = os.path.normpath(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        if os.path.isfile(normalized):
            return normalized
    return None


def bake_vertex_colors_from_uv(
    vertex_count: int,
    texcoords: List[List[float]],
    faces: List[List[int]],
    face_uvs: List[List[Optional[int]]],
    texture: np.ndarray,
    base_colors: Optional[np.ndarray] = None,
    skip_mask: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, int]:
    """Average MTL texture samples onto vertices (OBJ UV, V=0 at bottom).

    Returns (N, 3) RGB in 0-255 and the number of vertices that received
    at least one texture sample.
    """
    height, width = texture.shape[0], texture.shape[1]
    if base_colors is not None and len(base_colors) == vertex_count:
        colors = np.asarray(base_colors, dtype=np.float64).copy()
    else:
        colors = np.tile(
            np.asarray(COMPONENT_COLOR, dtype=np.float64),
            (vertex_count, 1),
        )
    sums = np.zeros((vertex_count, 3), dtype=np.float64)
    counts = np.zeros(vertex_count, dtype=np.int32)
    n_uv = len(texcoords)
    for face, uvs in zip(faces, face_uvs):
        for vi, ti in zip(face, uvs):
            if ti is None or vi < 0 or vi >= vertex_count:
                continue
            if skip_mask is not None and skip_mask[vi]:
                continue
            if ti < 0 or ti >= n_uv:
                continue
            u = texcoords[ti][0]
            v = texcoords[ti][1]
            u = u - np.floor(u)
            v = v - np.floor(v)
            x = int(u * width)
            y = int((1.0 - v) * height)
            x = 0 if x < 0 else (width - 1 if x >= width else x)
            y = 0 if y < 0 else (height - 1 if y >= height else y)
            sums[vi] += texture[y, x, :3]
            counts[vi] += 1
    sampled = counts > 0
    n_sampled = int(np.count_nonzero(sampled))
    if n_sampled:
        colors[sampled] = sums[sampled] / counts[sampled][:, None]
    return colors, n_sampled


def parse_obj_with_objects(
    obj_path: str,
    convert_yup_to_zup: bool = False,
) -> Dict:
    """
    Parse an aligned scan OBJ into mesh objects and marker points.

    Current Metashape/postprocess export (``output/mesh.obj``):
      * ``o end_effector`` / ``o object`` triangle meshes
      * Alignment markers as ``v`` + ``o marker_blue_N`` / ``o marker_green_x``
        + ``p <index>`` (vertex may be declared *before* the ``o`` line)
      * Vertex colors come from ``map_Kd`` (mesh.jpg / mesh.jpeg) via ``vt``

    Legacy files used a single ``o marker_points`` object and Y-up vertices.
    """
    objects: Dict[str, Dict] = {}
    marker_points: List[List[float]] = []
    marker_labels: List[str] = []
    current_object: Optional[str] = None
    pending_vertex_indices: List[int] = []
    global_vertices: List[List[float]] = []
    global_colors: List[List[float]] = []
    explicit_color: List[bool] = []
    texcoords: List[List[float]] = []
    mtllib_files: List[str] = []

    def _ensure_object(name: str) -> Dict:
        if name not in objects:
            objects[name] = {
                'faces': [],
                'face_uvs': [],
                'point_indices': [],
                'pending_vertices': [],
            }
        return objects[name]

    with open(obj_path, 'r', encoding='utf-8', errors='replace') as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue

            if line.startswith('mtllib '):
                name = line[7:].strip().strip('"')
                if name:
                    mtllib_files.append(name)
                continue

            if line.startswith('o ') or line.startswith('g '):
                object_name = line[2:].strip()
                current_object = object_name
                obj = _ensure_object(current_object)
                if (_is_marker_object(current_object)
                        and pending_vertex_indices):
                    obj['pending_vertices'].extend(
                        pending_vertex_indices
                    )
                pending_vertex_indices = []
                continue

            if line.startswith('vt '):
                parts = line[3:].split()
                if len(parts) >= 2:
                    texcoords.append([float(parts[0]), float(parts[1])])
                continue

            if line.startswith('v '):
                parts = line[2:].split()
                if len(parts) < 3:
                    continue
                vertex = [
                    float(parts[0]),
                    float(parts[1]),
                    float(parts[2]),
                ]
                if convert_yup_to_zup:
                    vertex = obj_yup_to_rhino_zup(vertex)
                has_rgb = len(parts) >= 6
                if has_rgb:
                    color = [
                        float(parts[3]),
                        float(parts[4]),
                        float(parts[5]),
                    ]
                else:
                    color = [
                        COMPONENT_COLOR[0] / 255.0,
                        COMPONENT_COLOR[1] / 255.0,
                        COMPONENT_COLOR[2] / 255.0,
                    ]
                vertex_idx = len(global_vertices)
                global_vertices.append(vertex)
                global_colors.append(color)
                explicit_color.append(has_rgb)
                pending_vertex_indices.append(vertex_idx)
                continue

            if line.startswith('f '):
                pending_vertex_indices = []
                if not current_object or _is_marker_object(current_object):
                    continue
                obj = _ensure_object(current_object)
                face = []
                face_uv: List[Optional[int]] = []
                for part in line[2:].split():
                    bits = part.split('/')
                    vertex_idx = _obj_index(
                        int(bits[0]), len(global_vertices)
                    )
                    face.append(vertex_idx)
                    if len(bits) >= 2 and bits[1]:
                        face_uv.append(
                            _obj_index(int(bits[1]), len(texcoords))
                        )
                    else:
                        face_uv.append(None)
                if len(face) >= 3:
                    obj['faces'].append(face)
                    obj['face_uvs'].append(face_uv)
                continue

            if line.startswith('p '):
                pending_vertex_indices = []
                label = current_object or LEGACY_MARKER_OBJECT
                for part in line[2:].split():
                    vertex_idx = _obj_index(
                        int(part.split('/')[0]), len(global_vertices)
                    )
                    if 0 <= vertex_idx < len(global_vertices):
                        marker_points.append(global_vertices[vertex_idx])
                        marker_labels.append(label)
                        if current_object:
                            _ensure_object(current_object)[
                                'point_indices'
                            ].append(vertex_idx)

    if not marker_points:
        for name, obj in objects.items():
            if not _is_marker_object(name):
                continue
            source_indices = obj['point_indices'] or obj['pending_vertices']
            for vertex_idx in source_indices:
                if 0 <= vertex_idx < len(global_vertices):
                    marker_points.append(global_vertices[vertex_idx])
                    marker_labels.append(name)

    texture_path = resolve_diffuse_texture_path(obj_path, mtllib_files)
    if texture_path and texcoords:
        logger.info(
            f"[COLOR] Baking vertex colors from texture: "
            f"{os.path.basename(texture_path)}"
        )
        texture = np.asarray(Image.open(texture_path).convert('RGB'))
        all_faces: List[List[int]] = []
        all_uvs: List[List[Optional[int]]] = []
        for name, obj in objects.items():
            if _is_marker_object(name):
                continue
            all_faces.extend(obj['faces'])
            all_uvs.extend(obj.get('face_uvs') or [])
        skip = np.asarray(explicit_color, dtype=bool)
        base = np.asarray(global_colors, dtype=np.float64)
        if base.size and base.max() <= 1.0:
            base = base * 255.0
        baked, n_sampled = bake_vertex_colors_from_uv(
            len(global_vertices),
            texcoords,
            all_faces,
            all_uvs,
            texture,
            base_colors=base,
            skip_mask=skip,
        )
        logger.info(
            f"[COLOR] Textured vertices: {n_sampled}/{len(global_vertices)}"
        )
        global_colors = baked.tolist()
    elif not any(explicit_color):
        logger.warning(
            "[COLOR] No vertex colors or diffuse texture found; "
            "using default gray"
        )

    meshes = {}
    for name, obj in objects.items():
        if _is_marker_object(name) or not obj['faces']:
            continue
        extracted = _extract_indexed_mesh(
            global_vertices, global_colors, obj['faces']
        )
        if extracted is not None:
            meshes[name] = extracted

    return {
        'objects': meshes,
        'marker_points': marker_points,
        'marker_labels': marker_labels,
    }


def _extract_indexed_mesh(
    vertices: List[List[float]],
    colors: List[List[float]],
    faces: List[List[int]],
) -> Optional[Dict]:
    """Compact a mesh to the vertices actually referenced by faces."""
    used = []
    seen = set()
    for face in faces:
        for idx in face:
            if idx not in seen and 0 <= idx < len(vertices):
                seen.add(idx)
                used.append(idx)
    if not used:
        return None
    remap = {old: new for new, old in enumerate(used)}
    return {
        'vertices': [vertices[i] for i in used],
        'colors': [colors[i] for i in used],
        'faces': [
            [remap[idx] for idx in face if idx in remap]
            for face in faces
            if sum(1 for idx in face if idx in remap) >= 3
        ],
    }


def triangulate_face(face: List[int]) -> List[List[int]]:
    """Convert n-gon face to triangles"""
    if len(face) == 3:
        return [face]
    if len(face) == 4:
        return [[face[0], face[1], face[2]], [face[0], face[2], face[3]]]
    triangles = []
    for i in range(1, len(face) - 1):
        triangles.append([face[0], face[i], face[i + 1]])
    return triangles


def triangulate_faces(faces: List[List[int]]) -> List[List[int]]:
    """Triangulate a list of polygon faces."""
    triangles = []
    for face in faces:
        if len(face) >= 3:
            triangles.extend(triangulate_face(face))
    return triangles


def _subsample_mesh(
    vertices: np.ndarray,
    faces: np.ndarray,
    colors: np.ndarray,
    target_faces: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Deterministic face stride fallback when quadric decimation fails."""
    if len(faces) <= target_faces:
        return vertices, faces, colors
    stride = max(1, len(faces) // target_faces)
    sample = np.asarray(faces[::stride][:target_faces], dtype=np.int64)
    used = np.unique(sample)
    remap = {int(old): new for new, old in enumerate(used)}
    remapped = np.array(
        [[remap[int(idx)] for idx in face] for face in sample],
        dtype=np.int64,
    )
    sampled_colors = colors
    if colors is not None and len(colors) > 0:
        sampled_colors = colors[used]
    return vertices[used], remapped, sampled_colors


def reduce_mesh_trimesh(
    vertices: np.ndarray,
    faces: np.ndarray,
    target_faces: int,
    colors: np.ndarray = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Reduce mesh using trimesh, with stride-sample fallback."""
    empty_colors = colors if colors is not None else np.array([])
    current_faces = len(faces)
    if current_faces <= target_faces:
        return vertices, faces, empty_colors
    try:
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        simplified = mesh.simplify_quadric_decimation(face_count=target_faces)
        if colors is not None and len(colors) > 0:
            tree = cKDTree(vertices)
            _, indices = tree.query(simplified.vertices)
            mapped_colors = colors[indices]
            return simplified.vertices, simplified.faces, mapped_colors
        return simplified.vertices, simplified.faces, np.array([])
    except Exception as exc:
        logger.warning(
            f"Mesh reduction failed: {exc}; stride-sampling to "
            f"{target_faces} faces"
        )
        return _subsample_mesh(vertices, faces, empty_colors, target_faces)


def _gram_matrix_3x3(points: np.ndarray) -> List[List[float]]:
    """3x3 Gram matrix via scalar sums (no BLAS)."""
    xx = xy = xz = yy = yz = zz = 0.0
    for x, y, z in points:
        xx += x * x
        xy += x * y
        xz += x * z
        yy += y * y
        yz += y * z
        zz += z * z
    return [
        [xx, xy, xz],
        [xy, yy, yz],
        [xz, yz, zz],
    ]


def _jacobi_eigh_3x3(matrix: List[List[float]]):
    """
    Eigen-decomposition of a 3x3 symmetric matrix (Jacobi rotations).

    Returns eigenvalues (desc) and eigenvectors as row vectors.
    Avoids LAPACK so the scan workstation does not depend on MKL/OpenBLAS.
    """
    a = [row[:] for row in matrix]
    v = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]
    for _ in range(50):
        p, q = 0, 1
        max_off = abs(a[0][1])
        for i, j in ((0, 2), (1, 2)):
            if abs(a[i][j]) > max_off:
                max_off = abs(a[i][j])
                p, q = i, j
        if max_off < 1e-12:
            break
        app = a[p][p]
        aqq = a[q][q]
        apq = a[p][q]
        tau = (aqq - app) / (2.0 * apq)
        sign = 1.0 if tau >= 0.0 else -1.0
        t = sign / (abs(tau) + (1.0 + tau * tau) ** 0.5)
        c = 1.0 / (1.0 + t * t) ** 0.5
        s = t * c
        a[p][p] = app - t * apq
        a[q][q] = aqq + t * apq
        a[p][q] = 0.0
        a[q][p] = 0.0
        for r in range(3):
            if r == p or r == q:
                continue
            arp = a[r][p]
            arq = a[r][q]
            a[r][p] = a[p][r] = c * arp - s * arq
            a[r][q] = a[q][r] = s * arp + c * arq
        for r in range(3):
            vrp = v[r][p]
            vrq = v[r][q]
            v[r][p] = c * vrp - s * vrq
            v[r][q] = s * vrp + c * vrq

    evals = [a[0][0], a[1][1], a[2][2]]
    order = sorted(range(3), key=lambda i: evals[i], reverse=True)
    components = np.array(
        [[v[0][i], v[1][i], v[2][i]] for i in order],
        dtype=np.float64,
    )
    return components


def compute_obb_3d(
    points: np.ndarray
) -> Tuple[List[float], np.ndarray, List[float]]:
    """
    Compute object oriented bounding box for 3D points using SVD/PCA.

    Matches the catalog orientation contract: unsorted PCA-axis dimensions
    and bounding-box origin in PCA space. Sign of the third axis is flipped
    when needed so the frame is right-handed.
    """
    centered = np.asarray(points, dtype=np.float64)
    if centered.ndim != 2 or centered.shape[1] != 3:
        raise ValueError('points must be an (N, 3) array')
    if centered.shape[0] < 3:
        raise ValueError(
            f'Need at least 3 points for 3D OBB/PCA, got {centered.shape[0]}'
        )

    principal_components = _jacobi_eigh_3x3(_gram_matrix_3x3(centered))
    det = (
        principal_components[0, 0] * (
            principal_components[1, 1] * principal_components[2, 2]
            - principal_components[1, 2] * principal_components[2, 1]
        )
        - principal_components[0, 1] * (
            principal_components[1, 0] * principal_components[2, 2]
            - principal_components[1, 2] * principal_components[2, 0]
        )
        + principal_components[0, 2] * (
            principal_components[1, 0] * principal_components[2, 1]
            - principal_components[1, 1] * principal_components[2, 0]
        )
    )
    if det < 0:
        principal_components[2] = -principal_components[2]

    min_bounds = [float('inf')] * 3
    max_bounds = [float('-inf')] * 3
    for x, y, z in centered:
        px = (principal_components[0, 0] * x
              + principal_components[0, 1] * y
              + principal_components[0, 2] * z)
        py = (principal_components[1, 0] * x
              + principal_components[1, 1] * y
              + principal_components[1, 2] * z)
        pz = (principal_components[2, 0] * x
              + principal_components[2, 1] * y
              + principal_components[2, 2] * z)
        if px < min_bounds[0]:
            min_bounds[0] = px
        if py < min_bounds[1]:
            min_bounds[1] = py
        if pz < min_bounds[2]:
            min_bounds[2] = pz
        if px > max_bounds[0]:
            max_bounds[0] = px
        if py > max_bounds[1]:
            max_bounds[1] = py
        if pz > max_bounds[2]:
            max_bounds[2] = pz
    dimensions = [
        max_bounds[0] - min_bounds[0],
        max_bounds[1] - min_bounds[1],
        max_bounds[2] - min_bounds[2],
    ]
    bbx_origin = [
        (min_bounds[0] + max_bounds[0]) / 2.0,
        (min_bounds[1] + max_bounds[1]) / 2.0,
        (min_bounds[2] + max_bounds[2]) / 2.0,
    ]
    return (
        [float(v) for v in dimensions],
        principal_components,
        [float(v) for v in bbx_origin],
    )


def _as_int_colors(colors: np.ndarray, vertex_count: int) -> np.ndarray:
    """Return (N, 3) uint8 RGB, falling back to COMPONENT_COLOR."""
    if colors is None or colors.size == 0:
        return np.tile(
            np.asarray(COMPONENT_COLOR, dtype=np.uint8),
            (vertex_count, 1),
        )
    return normalize_colors_to_integers(colors).astype(np.uint8)


def create_snapshot_mesh(
    vertices: np.ndarray,
    colors: np.ndarray,
    faces: np.ndarray,
) -> Dict:
    """Create a SnapshotMesh dict (vertices/faces/colors, Rhino Z-up)."""
    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    int_colors = _as_int_colors(
        np.asarray(colors, dtype=np.float64) if colors is not None else None,
        len(vertices),
    )
    return {
        'vertices': vertices.astype(float).tolist(),
        'faces': faces.astype(int).tolist(),
        'colors': int_colors.tolist(),
    }


def save_mesh_ply_binary(
    vertices: np.ndarray,
    faces: np.ndarray,
    colors: np.ndarray,
    filepath: str,
) -> None:
    """Write binary little-endian PLY (Rhino Z-up) with per-vertex RGB."""
    vertices = np.asarray(vertices, dtype=np.float32)
    faces = np.asarray(faces, dtype=np.int32)
    colors = _as_int_colors(
        np.asarray(colors, dtype=np.float64) if colors is not None else None,
        len(vertices),
    )
    if faces.ndim != 2 or faces.shape[1] < 3:
        raise ValueError('faces must be an (N, 3+) index array')
    tris = faces[:, :3]

    header = (
        'ply\n'
        'format binary_little_endian 1.0\n'
        f'element vertex {len(vertices)}\n'
        'property float x\n'
        'property float y\n'
        'property float z\n'
        'property uchar red\n'
        'property uchar green\n'
        'property uchar blue\n'
        f'element face {len(tris)}\n'
        'property list uchar int vertex_indices\n'
        'end_header\n'
    )

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    vertex_dtype = np.dtype([
        ('x', '<f4'),
        ('y', '<f4'),
        ('z', '<f4'),
        ('red', 'u1'),
        ('green', 'u1'),
        ('blue', 'u1'),
    ])
    vertex_out = np.empty(len(vertices), dtype=vertex_dtype)
    vertex_out['x'] = vertices[:, 0]
    vertex_out['y'] = vertices[:, 1]
    vertex_out['z'] = vertices[:, 2]
    vertex_out['red'] = colors[:, 0]
    vertex_out['green'] = colors[:, 1]
    vertex_out['blue'] = colors[:, 2]

    face_dtype = np.dtype([
        ('n', 'u1'),
        ('i0', '<i4'),
        ('i1', '<i4'),
        ('i2', '<i4'),
    ])
    face_out = np.empty(len(tris), dtype=face_dtype)
    face_out['n'] = 3
    face_out['i0'] = tris[:, 0]
    face_out['i1'] = tris[:, 1]
    face_out['i2'] = tris[:, 2]

    with open(filepath, 'wb') as handle:
        handle.write(header.encode('ascii'))
        vertex_out.tofile(handle)
        face_out.tofile(handle)


def mesh_arrays(mesh: Dict) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return vertices, colors, triangulated faces as numpy arrays."""
    vertices = np.asarray(mesh['vertices'], dtype=np.float64)
    colors = np.asarray(mesh['colors'], dtype=np.float64)
    raw_faces = mesh['faces']
    if raw_faces and all(len(face) == 3 for face in raw_faces):
        faces = np.asarray(raw_faces, dtype=np.int64)
    else:
        faces = np.asarray(triangulate_faces(raw_faces), dtype=np.int64)
    return vertices, colors, faces


def resolve_aligned_mesh_path(scan_folder: str) -> Tuple[Optional[str], bool]:
    """
    Prefer ``output/mesh.obj`` (aligned, Rhino Z-up).

    Fall back to legacy ``output/aligned_mesh.obj`` (Y-up, needs conversion).
    """
    output_folder = os.path.join(scan_folder, 'output')
    mesh_path = os.path.join(output_folder, 'mesh.obj')
    if os.path.exists(mesh_path):
        return mesh_path, False
    legacy_path = os.path.join(output_folder, 'aligned_mesh.obj')
    if os.path.exists(legacy_path):
        return legacy_path, True
    return None, False


def prepare_mesh_versions(
    vertices: np.ndarray,
    colors: np.ndarray,
    faces: np.ndarray,
    primitive_index: int,
    transcode_folder: str,
) -> Tuple[Dict, List[Dict]]:
    """
    Build the inline primitive and stage detailed/reduced PLY files.

    Returns (primitive SnapshotMesh, list of staged file descriptors).
    """
    vertices = np.asarray(vertices, dtype=np.float64)
    colors = np.asarray(colors, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    face_count = len(faces)
    logger.info(
        f"   [OBJ] Primitive {primitive_index}: {len(vertices)} "
        f"vertices, {face_count} faces"
    )

    primitive_vertices = vertices
    primitive_colors = colors
    primitive_faces = faces
    reduced_vertices = None
    reduced_colors = None
    reduced_faces = None

    if face_count > MESH_REDUCED_THRESHOLD:
        logger.info(
            f"   [PROCESSING] Reducing from {face_count} to "
            f"{MESH_REDUCED_TARGET} (reduced) and "
            f"{MESH_PRIMITIVE_TARGET} (primitive) faces..."
        )
        reduced_vertices, reduced_faces, reduced_colors = reduce_mesh_trimesh(
            vertices, faces, MESH_REDUCED_TARGET, colors
        )
        primitive_vertices, primitive_faces, primitive_colors = (
            reduce_mesh_trimesh(
                vertices, faces, MESH_PRIMITIVE_TARGET, colors
            )
        )
        logger.info(
            f"   [OK] Reduced={len(reduced_faces)} "
            f"primitive={len(primitive_faces)}"
        )
    elif face_count > MESH_PRIMITIVE_THRESHOLD:
        logger.info(
            f"   [PROCESSING] Reducing from {face_count} to "
            f"{MESH_PRIMITIVE_TARGET} faces (primitive)..."
        )
        primitive_vertices, primitive_faces, primitive_colors = (
            reduce_mesh_trimesh(
                vertices, faces, MESH_PRIMITIVE_TARGET, colors
            )
        )
        logger.info(f"   [OK] Primitive={len(primitive_faces)} faces")
    else:
        logger.info(
            f"   [OK] Mesh already small enough ({face_count} faces, "
            f"<{MESH_PRIMITIVE_THRESHOLD})"
        )

    primitive_mesh = create_snapshot_mesh(
        primitive_vertices, primitive_colors, primitive_faces
    )

    staged = []
    primitive_dir = os.path.join(
        transcode_folder, 'meshes', str(primitive_index)
    )
    save_detailed = face_count > MESH_PRIMITIVE_TARGET
    save_reduced = (
        face_count > MESH_REDUCED_THRESHOLD and reduced_faces is not None
    )
    if save_detailed:
        path = os.path.join(primitive_dir, 'detailed.ply')
        logger.info(f"   [FILE] detailed.ply primitive {primitive_index}")
        save_mesh_ply_binary(vertices, faces, colors, path)
        staged.append({
            'primitive_index': primitive_index,
            'resolution': 'detailed',
            'path': Path(
                os.path.relpath(path, transcode_folder)
            ).as_posix(),
        })
    if save_reduced:
        path = os.path.join(primitive_dir, 'reduced.ply')
        logger.info(f"   [FILE] reduced.ply primitive {primitive_index}")
        save_mesh_ply_binary(
            reduced_vertices, reduced_faces, reduced_colors, path
        )
        staged.append({
            'primitive_index': primitive_index,
            'resolution': 'reduced',
            'path': Path(
                os.path.relpath(path, transcode_folder)
            ).as_posix(),
        })
    return primitive_mesh, staged


def process_scan_folder(scan_folder: str, component_id: str) -> bool:
    """Process a single scan folder into identity + v0 snapshot payload."""
    logger.info(f"[PROCESSING] Processing scan folder: {component_id}")

    metadata_path = os.path.join(scan_folder, 'metadata.json')
    transcode_folder = os.path.join(scan_folder, 'transcode')
    aligned_mesh_path, convert_yup_to_zup = resolve_aligned_mesh_path(
        scan_folder
    )

    logger.info("[FOLDER] Folder structure:")
    logger.info(f"   [FILE] Metadata: {os.path.basename(metadata_path)}")
    if aligned_mesh_path:
        logger.info(
            f"   [FILE] Mesh: {os.path.relpath(aligned_mesh_path, scan_folder)}"
            f"{' (legacy Y-up)' if convert_yup_to_zup else ' (Rhino Z-up)'}"
        )
    logger.info("   [TARGET] Target: transcode/")

    logger.info("[FOLDER] Creating transcode folder...")
    os.makedirs(transcode_folder, exist_ok=True)

    logger.info("[SEARCH] Checking required files...")
    if not os.path.exists(metadata_path):
        logger.error(f"[ERROR] Missing metadata.json in {component_id}")
        return False
    logger.info("[OK] Found metadata.json")

    if not aligned_mesh_path:
        logger.error(
            f"[ERROR] Missing output/mesh.obj (or aligned_mesh.obj) "
            f"in {component_id}"
        )
        return False
    logger.info(f"[OK] Found {os.path.basename(aligned_mesh_path)}")

    try:
        logger.info("[PROCESSING] Loading metadata.json...")
        with open(metadata_path, 'r', encoding='utf-8') as handle:
            metadata = json.load(handle)
        logger.info(f"[OK] Metadata loaded: {len(metadata)} keys")

        logger.info("[SEARCH] Parsing aligned mesh OBJ...")
        obj_data = parse_obj_with_objects(
            aligned_mesh_path,
            convert_yup_to_zup=convert_yup_to_zup,
        )
        objects = obj_data['objects']
        marker_points = obj_data['marker_points']
        marker_labels = obj_data.get('marker_labels') or []
        del obj_data

        logger.info("[OBJ] OBJ parsing results:")
        logger.info(f"   [TARGET] Mesh objects: {list(objects.keys())}")
        logger.info(f"   [MARKER POINTS] Marker points: {len(marker_points)}")
        if marker_labels:
            logger.info(f"   [MARKER POINTS] Labels: {marker_labels}")

        if MESH_OBJECT_STONE not in objects:
            logger.error(
                f"[ERROR] Missing '{MESH_OBJECT_STONE}' in OBJ file "
                f"for {component_id}"
            )
            return False
        stone = objects[MESH_OBJECT_STONE]
        logger.info(
            f"[OK] Main object found: {len(stone['vertices'])} vertices, "
            f"{len(stone['faces'])} faces"
        )

        effector = objects.get(MESH_OBJECT_EFFECTOR)
        if effector is None:
            logger.warning(
                f"[WARNING] Missing '{MESH_OBJECT_EFFECTOR}' in OBJ "
                f"for {component_id}"
            )
        else:
            logger.info(
                f"[OK] End effector found: {len(effector['vertices'])} "
                f"vertices, {len(effector['faces'])} faces"
            )

        stone_vertices, stone_colors, stone_faces = mesh_arrays(stone)
        del stone
        objects.pop(MESH_OBJECT_STONE, None)

        mesh_payloads = [(
            MESH_OBJECT_STONE, stone_vertices, stone_colors, stone_faces
        )]
        if effector is not None:
            ee_vertices, ee_colors, ee_faces = mesh_arrays(effector)
            del effector
            objects.pop(MESH_OBJECT_EFFECTOR, None)
            mesh_payloads.append((
                MESH_OBJECT_EFFECTOR, ee_vertices, ee_colors, ee_faces
            ))
        del objects

        logger.info(
            "[ORIGIN] Keeping marker-plane alignment "
            "(no additional centering)"
        )
        centroid = np.mean(stone_vertices, axis=0)
        logger.info("[PCA] Computing PCA for rubble mesh only...")
        pca_dimensions, principal_components, bbx_origin = compute_obb_3d(
            stone_vertices - centroid
        )
        logger.info(
            f"[PCA] PCA dimensions: [{pca_dimensions[0]:.3f}, "
            f"{pca_dimensions[1]:.3f}, {pca_dimensions[2]:.3f}]"
        )
        logger.info(
            f"[PCA] Frame origin (rubble centroid): "
            f"[{centroid[0]:.3f}, {centroid[1]:.3f}, {centroid[2]:.3f}]"
        )

        logger.info("[PROCESSING] Processing meshes...")
        primitive_meshes = []
        staged_files = []
        for index, (_name, vertices, colors, faces) in enumerate(
                mesh_payloads):
            primitive, staged = prepare_mesh_versions(
                vertices, colors, faces, index, transcode_folder
            )
            primitive_meshes.append(primitive)
            staged_files.extend(staged)

        if not primitive_meshes:
            logger.error(f"[ERROR] No valid meshes found for {component_id}")
            return False
        logger.info(f"[OK] Processed {len(primitive_meshes)} meshes total")

        geometry = {'meshes': primitive_meshes}
        if marker_points:
            geometry['marker_points'] = [
                [float(c) for c in point] for point in marker_points
            ]

        pca_frame = {
            'o': [float(v) for v in centroid],
            'x': principal_components[0].astype(float).tolist(),
            'y': principal_components[1].astype(float).tolist(),
            'z': principal_components[2].astype(float).tolist(),
        }

        component_data = {
            "_id": component_id,
            "name": f"Scanned Rubble Component {component_id[:8]}",
            "type": COMPONENT_TYPE,
            "material": COMPONENT_MATERIAL,
            "dataset": DATASET_NAME,
            "complexity": 2,
            "fragment": True,
            "assembly": False,
            "geometry": geometry,
            "color": list(COMPONENT_COLOR),
            "bbx": [float(v) for v in pca_dimensions],
            "bbx_origin": [float(v) for v in bbx_origin],
            "location": dict(COMPONENT_LOCATION),
            "descriptors": {},
            "processes": {},
            "iframe": identity_frame(),
            "pca_frame": pca_frame,
            "validated": False,
            "reserved": "",
            "attributes": {
                "3d_scan_metadata": metadata
            },
        }

        component_json_path = os.path.join(
            transcode_folder, f"{component_id}.json"
        )
        logger.info(
            f"[FILE] Saving CreateComponentRequest: {component_id}.json"
        )
        with open(component_json_path, 'w', encoding='utf-8') as handle:
            json.dump(component_data, handle, indent=2)

        manifest = {}
        for entry in staged_files:
            key = str(entry['primitive_index'])
            manifest.setdefault(key, []).append(entry['resolution'])
        manifest_path = os.path.join(transcode_folder, 'ply_manifest.json')
        with open(manifest_path, 'w', encoding='utf-8') as handle:
            json.dump({'meshes': manifest, 'files': staged_files}, handle,
                      indent=2)

        logger.info(f"[OK] Successfully processed component: {component_id}")
        logger.info("[SUMMARY] Summary:")
        logger.info(f"   [TARGET] Mesh primitives: {len(primitive_meshes)}")
        logger.info(f"   [MARKER POINTS] Marker points: {len(marker_points)}")
        logger.info(f"   [BOUNDING BOX] PCA bounding box: {pca_dimensions}")
        logger.info("   [FOLDER] Output files:")
        logger.info(f"      [FILE] {component_id}.json")
        logger.info("      [FILE] ply_manifest.json")
        for entry in staged_files:
            logger.info(f"      [FILE] {entry['path']}")

        return True

    except Exception as exc:
        logger.exception(f"Error processing {component_id}: {exc}")
        return False


def process_scan_by_path(scan_folder_path: str) -> bool:
    """
    Process a single scan folder by its path (programmatic interface).

    Args:
        scan_folder_path (str): Path to the UUID-named scan folder to process

    Returns:
        bool: True if processing was successful, False otherwise
    """
    scan_path = Path(scan_folder_path)

    if not scan_path.exists():
        logger.error(f"[ERROR] Scan folder does not exist: {scan_folder_path}")
        return False

    component_id = scan_path.name
    if not validate_uuid(component_id):
        logger.error(f"[ERROR] Invalid UUID folder name: {component_id}")
        return False

    logger.info(f"[PROCESSING] Processing scan folder: {component_id}")
    return process_scan_folder(str(scan_path), component_id)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python process_robot_scan.py <scan_folder_path>")
        sys.exit(1)

    success = process_scan_by_path(sys.argv[1])
    if not success:
        sys.exit(1)
