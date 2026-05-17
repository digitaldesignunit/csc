"""
CSC geometry coordinate helpers for maintenance scripts (OBJ -> PLY).

Not part of the FastAPI backend. Used by ``scripts/db_maintenance/`` export
tools. Run with the ``csc`` conda env::

    conda run -n csc python scripts/db_maintenance/m5_obj_to_ply_export.py ...

Coordinate contract
-------------------

* **CSC canonical = Rhino Z-up** for PLY bytes (same as ``geometry.meshes``).
* Legacy OBJ is Y-up; converted once on read::

    OBJ (x, y, z)  ->  Rhino (x, -z, y)

One ``o`` / ``g`` object in the OBJ file becomes one ``Trimesh`` and one PLY
at ``meshes/<snapshot_id>/<primitive_index>/{reduced|detailed}.ply``. Object
order in the file must match ``geometry.meshes[0]``, ``geometry.meshes[1]``,
… (e.g. Grasshopper ``o object_0``, ``o object_1`` in a single ``mesh.obj``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
import trimesh

CANONICAL_FRAME = 'rhino_z_up'
LEGACY_OBJ_FRAME = 'y_up_obj'

MESH_RESOLUTION_REDUCED = 'reduced'
MESH_RESOLUTION_DETAILED = 'detailed'

_DEFAULT_RGB = (255, 255, 255)


def mesh_ply_relative_path(*, primitive_index: int, resolution: str) -> str:
    """Relative path under ``meshes/<snapshot_id>/`` (POSIX-style segments)."""
    if primitive_index < 0:
        raise ValueError('primitive_index must be >= 0')
    return f'{primitive_index}/{resolution}.ply'


def obj_positions_to_rhino(positions: np.ndarray) -> np.ndarray:
    """Map Nx3 vertices from legacy OBJ layout to Rhino Z-up."""
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError('positions must be Nx3')
    out = np.zeros_like(positions)
    out[:, 0] = positions[:, 0]
    out[:, 1] = -positions[:, 2]
    out[:, 2] = positions[:, 1]
    return out


def count_legacy_obj_objects(filepath: str) -> int:
    """
    Count ``o`` / ``g`` objects in a legacy CSC OBJ.

    If the file has vertices or faces but no object declarations, returns 1.
    """
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f'OBJ file not found: {filepath}')

    object_count = 0
    saw_geometry = False
    with path.open('r', encoding='utf-8', errors='replace') as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('o ') or line.startswith('g '):
                object_count += 1
            elif line.startswith('v ') or line.startswith('f '):
                saw_geometry = True

    if object_count == 0 and saw_geometry:
        return 1
    return object_count


@dataclass
class _ParsedObject:
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    colors: List[Optional[Tuple[int, int, int]]] = field(default_factory=list)
    faces: List[List[int]] = field(default_factory=list)


def _parse_rgb(parts: Sequence[str]) -> Tuple[int, int, int]:
    r, g, b = float(parts[4]), float(parts[5]), float(parts[6])
    if max(r, g, b) > 1.0:
        return (
            int(max(0, min(255, round(r)))),
            int(max(0, min(255, round(g)))),
            int(max(0, min(255, round(b)))),
        )
    return (
        int(max(0, min(255, round(r * 255)))),
        int(max(0, min(255, round(g * 255)))),
        int(max(0, min(255, round(b * 255)))),
    )


def _triangulate_face(indices: List[int]) -> List[List[int]]:
    if len(indices) < 3:
        return []
    if len(indices) == 3:
        return [indices]
    if len(indices) == 4:
        return [
            [indices[0], indices[1], indices[2]],
            [indices[0], indices[2], indices[3]],
        ]
    tris: List[List[int]] = []
    for i in range(1, len(indices) - 1):
        tris.append([indices[0], indices[i], indices[i + 1]])
    return tris


def _resolve_face_index(
    token: str,
    vertex_count: int,
) -> Optional[int]:
    if not token:
        return None
    idx = int(token.split('/')[0])
    if idx > 0:
        return idx - 1
    if idx < 0:
        return vertex_count + idx
    return None


def _resolve_gh_duplicate_colors(obj: _ParsedObject) -> None:
    """
    Grasshopper may emit N position-only ``v`` lines
    then N colored ``v`` lines;
    faces reference only the first block. Copy RGB from the second block.
    """
    n = len(obj.vertices)
    if n < 2 or not obj.faces:
        return
    max_idx = max(max(face) for face in obj.faces)
    half = n // 2
    if n % 2 != 0 or max_idx >= half:
        return
    second_has_color = any(obj.colors[i] is not None for i in range(half, n))
    if not second_has_color:
        return
    for i in range(half):
        if obj.colors[i] is None and obj.colors[i + half] is not None:
            obj.colors[i] = obj.colors[i + half]


def _compact_object(obj: _ParsedObject) -> _ParsedObject:
    if not obj.faces:
        return _ParsedObject()

    used = sorted({idx for face in obj.faces for idx in face})
    remap = {old: new for new, old in enumerate(used)}
    vertices = [obj.vertices[i] for i in used]
    colors: List[Optional[Tuple[int, int, int]]] = []
    for i in used:
        rgb = obj.colors[i] if i < len(obj.colors) else None
        colors.append(rgb)
    faces = [[remap[i] for i in face] for face in obj.faces]
    return _ParsedObject(vertices=vertices, colors=colors, faces=faces)


def _build_object_from_global_faces(
    global_vertices: List[Tuple[float, float, float]],
    global_colors: List[Optional[Tuple[int, int, int]]],
    face_indices: List[List[int]],
) -> Optional[_ParsedObject]:
    """
    Slice one ``o``/``g`` object from file-wide vertex indices (CSC GH export).
    """
    if not face_indices:
        return None

    n_global = len(global_vertices)
    valid_faces: List[List[int]] = []
    for tri in face_indices:
        if all(0 <= idx < n_global for idx in tri):
            valid_faces.append(tri)
    if not valid_faces:
        return None

    used = sorted({idx for tri in valid_faces for idx in tri})
    remap = {global_idx: local for local, global_idx in enumerate(used)}
    vertices = [global_vertices[i] for i in used]
    colors = [
        global_colors[i] if i < len(global_colors) else None
        for i in used
    ]
    faces = [[remap[i] for i in tri] for tri in valid_faces]
    obj = _ParsedObject(vertices=vertices, colors=colors, faces=faces)
    _resolve_gh_duplicate_colors(obj)
    compact = _compact_object(obj)
    if compact.vertices and compact.faces:
        return compact
    return None


def _parse_legacy_obj_objects(filepath: str) -> List[_ParsedObject]:
    """
    Parse CSC legacy OBJ into one mesh per ``o`` / ``g`` block.

    Grasshopper writes a single global vertex list; each object's ``f`` lines
    use 1-based indices into that list (not a per-object local list from zero).
    """
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f'OBJ file not found: {filepath}')

    global_vertices: List[Tuple[float, float, float]] = []
    global_colors: List[Optional[Tuple[int, int, int]]] = []
    objects: List[_ParsedObject] = []
    current_faces: List[List[int]] = []

    def flush_object() -> None:
        nonlocal current_faces
        if not current_faces:
            return
        built = _build_object_from_global_faces(
            global_vertices,
            global_colors,
            current_faces,
        )
        if built is not None:
            objects.append(built)
        current_faces = []

    with path.open('r', encoding='utf-8', errors='replace') as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if not parts:
                continue
            tag = parts[0]

            if tag in ('o', 'g'):
                flush_object()
                continue

            if tag == 'v' and len(parts) >= 4:
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                global_vertices.append((x, y, z))
                if len(parts) >= 7:
                    global_colors.append(_parse_rgb(parts))
                else:
                    global_colors.append(None)
                continue

            if tag == 'f' and len(parts) >= 4:
                indices: List[int] = []
                for token in parts[1:]:
                    resolved = _resolve_face_index(
                        token,
                        len(global_vertices),
                    )
                    if resolved is None:
                        continue
                    if 0 <= resolved < len(global_vertices):
                        indices.append(resolved)
                for tri in _triangulate_face(indices):
                    current_faces.append(tri)

    flush_object()

    if not objects:
        raise ValueError(f'OBJ contains no usable geometry: {filepath}')
    return objects


def _object_to_trimesh_rhino(obj: _ParsedObject) -> trimesh.Trimesh:
    verts = np.asarray(obj.vertices, dtype=np.float64)
    faces = np.asarray(obj.faces, dtype=np.int64)
    rhino_vertices = obj_positions_to_rhino(verts)
    mesh = trimesh.Trimesh(
        vertices=rhino_vertices,
        faces=faces,
        process=False,
    )

    rgba = np.zeros((len(obj.vertices), 4), dtype=np.uint8)
    rgba[:, 3] = 255
    for i, rgb in enumerate(obj.colors):
        if rgb is not None:
            rgba[i, 0], rgba[i, 1], rgba[i, 2] = rgb
        else:
            rgba[i, 0], rgba[i, 1], rgba[i, 2] = _DEFAULT_RGB

    mesh.visual.vertex_colors = rgba
    return mesh


def load_legacy_obj_meshes_rhino(filepath: str) -> List[trimesh.Trimesh]:
    """
    Load a legacy CSC OBJ; return one mesh per ``o`` / ``g`` object.

    Each mesh is in Rhino Z-up with per-vertex RGB (``v x y z r g b`` and the
    Grasshopper duplicate-vertex color block are both supported).
    """
    return [
        _object_to_trimesh_rhino(obj)
        for obj in _parse_legacy_obj_objects(filepath)
    ]


def load_legacy_obj_mesh_rhino(filepath: str) -> trimesh.Trimesh:
    """Load a single-object OBJ, or the only object when there is just one."""
    meshes = load_legacy_obj_meshes_rhino(filepath)
    if len(meshes) != 1:
        raise ValueError(
            f'OBJ has {len(meshes)} objects; '
            'use load_legacy_obj_meshes_rhino: '
            f'{filepath}'
        )
    return meshes[0]


def export_mesh_ply_rhino(mesh: trimesh.Trimesh, dest_path: str) -> None:
    """Write binary PLY in Rhino Z-up; include vertex colors when set."""
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(str(dest), file_type='ply')
