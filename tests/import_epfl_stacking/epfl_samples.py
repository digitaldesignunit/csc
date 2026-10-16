"""Tiny stones made here: a sphere as a mesh and as a cloud, written as the dataset's files are (ASCII PLY
exported by Rhino 7: vertex x y z nx ny nz red green blue, faces ``list uchar uint``, a trailing ``material``
element; the cloud in METRES, the mesh in mm). Nothing here comes from the dataset."""

from __future__ import annotations

from pathlib import Path

import numpy as np

MATERIAL_HEADER = (
    'element material 1\n'
    + ''.join(f'property uchar {n}\n' for n in (
        'ambient_red', 'ambient_green', 'ambient_blue', 'ambient_alpha',
        'diffuse_red', 'diffuse_green', 'diffuse_blue', 'diffuse_alpha',
        'emissive_red', 'emissive_green', 'emissive_blue', 'emissive_alpha',
        'specular_red', 'specular_green', 'specular_blue', 'specular_alpha'))
    + 'property double shine\nproperty double transparency\n')
MATERIAL_ROW = '0 0 0 255 250 250 250 255 0 0 0 255 255 255 255 255 0 0'


def sphere(subdivisions: int, radius: float):
    import trimesh
    mesh = trimesh.creation.icosphere(subdivisions=subdivisions, radius=radius)
    return np.asarray(mesh.vertices), np.asarray(mesh.faces)


def gradient_colors(vertices):
    """A colour per vertex that follows x, so a wrong carry-over of colours shows."""
    x = vertices[:, 0]
    r = np.interp(x, (x.min(), x.max()), (20, 235)).astype(np.uint8)
    return np.stack([r, np.full(len(r), 120, np.uint8), (255 - r).astype(np.uint8)], axis=1)


def write_mesh_ply(path: Path, vertices, faces, colors) -> Path:
    """An ASCII PLY as Rhino 7 writes it, with the extra material element."""
    lines = ['ply', 'format ascii 1.0', 'comment File exported by Rhinoceros Version 7.0',
             f'element vertex {len(vertices)}', 'property float x', 'property float y', 'property float z',
             'property float nx', 'property float ny', 'property float nz',
             'property uchar red', 'property uchar green', 'property uchar blue',
             f'element face {len(faces)}', 'property list uchar uint vertex_indices']
    header = '\n'.join(lines) + '\n' + MATERIAL_HEADER + 'end_header\n'
    rows = [f'{float(v[0])!r} {float(v[1])!r} {float(v[2])!r} 0.0 0.0 1.0 {c[0]} {c[1]} {c[2]}' for v, c in zip(vertices, colors)]
    rows += [f'3 {f[0]} {f[1]} {f[2]}' for f in faces]
    rows.append(MATERIAL_ROW)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(header + '\n'.join(rows) + '\n', encoding='ascii')
    return Path(path)


def write_cloud_ply(path: Path, points, colors) -> Path:
    lines = ['ply', 'format ascii 1.0', 'comment File exported by Rhinoceros Version 7.0',
             f'element vertex {len(points)}', 'property float x', 'property float y', 'property float z',
             'property float nx', 'property float ny', 'property float nz',
             'property uchar red', 'property uchar green', 'property uchar blue', 'end_header']
    rows = [f'{float(p[0])!r} {float(p[1])!r} {float(p[2])!r} 0.0 0.0 1.0 {c[0]} {c[1]} {c[2]}' for p, c in zip(points, colors)]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text('\n'.join(lines) + '\n' + '\n'.join(rows) + '\n', encoding='ascii')
    return Path(path)


def cloud_on_sphere(count: int, radius: float, seed: int = 1):
    """``count`` points on a sphere (deterministic), with colours that follow x."""
    rng = np.random.default_rng(seed)
    direction = rng.normal(size=(count, 3))
    direction /= np.linalg.norm(direction, axis=1, keepdims=True)
    points = direction * radius
    return points, gradient_colors(points)


def write_stone(root: Path, stone_id: str, *, subdivisions: int, radius_mm: float, cloud_points: int,
                cloud_unit: float = 0.001) -> None:
    """The two files of one stone under ``root/stones``: mesh in mm, cloud in ``cloud_unit`` x mm (metres by
    default, as in the dataset)."""
    vertices, faces = sphere(subdivisions, radius_mm)
    write_mesh_ply(root / 'stones' / 'mesh_high_res' / f'remeshed_high_res_{stone_id}.ply',
                   vertices, faces, gradient_colors(vertices))
    points, colors = cloud_on_sphere(cloud_points, radius_mm)
    write_cloud_ply(root / 'stones' / 'pcd_high_res' / f'pcd_high_res_{stone_id}.ply',
                    points * cloud_unit, colors)
