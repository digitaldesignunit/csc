"""Prepare every stone of the EPFL dataset the way the Grasshopper client would send it (decision 8.146).

    python -I -X utf8 prepare.py [--data <folder>] [--out <out folder>] [--only A0,B7] [--limit N]
                                 [--jobs 4] [--force]

Per stone `<ID>`: the mesh (`remeshed_high_res_<ID>.ply`) and the point cloud (`pcd_high_res_<ID>.ply`) are
read (ASCII PLY exported by Rhino 7, with normals, scan colours and an extra `material` element), and
written to `<out>/stones/<ID>/` by the rules of `csc_gh.build` (decision 8.95):

- `preview.json`: the inline preview mesh (the mesh itself up to MESH_PRIMITIVE_THRESHOLD faces, else
  reduced to MESH_PRIMITIVE_TARGET faces) and the inline point cloud (evenly thinned to 5000 points);
- `reduced.ply`: the mesh reduced to MESH_REDUCED_TARGET faces, when it has more than
  MESH_REDUCED_THRESHOLD faces;
- `detailed.ply`: the original mesh, binary, with its colours, when it has more than MESH_PRIMITIVE_TARGET
  faces;
- `cloud.ply`: the full cloud, when it has more points than POINT_CLOUD_STAGING_THRESHOLD;
- `meta.json`: counts, bounding box, watertight, volume, file sizes, flags.

Then `<out>/prepare.json` (all stones) and `<out>/report.md`. Reductions are quadric decimation; colours
of a reduced mesh are those of the nearest original vertex. Nothing else is recomputed: a mesh that is not
watertight goes up as it is and is counted. UNITS: the meshes are in mm (the authors' script says "scale to
m", the data does not need it); the point clouds are in METRES in the published files, one thousandth of the
mesh, in the same position: each cloud is multiplied by 1000 to the mesh's unit, the factor is derived per
stone from the two bounding boxes, and a stone whose factor is neither 1 nor 1000 (within a factor of 2) keeps no cloud and is
flagged. Every stone whose extent is outside 20 mm .. 3000 mm is flagged.

Needs numpy, scipy, trimesh and fast-simplification (requirements-import.txt) and the Grasshopper client
library (`grasshopper_lib/csc_gh`, in this repository).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import epfl_common as epfl  # noqa: E402

common = epfl.common
sys.path.insert(0, str(common.REPO / 'grasshopper_lib'))
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from csc_gh.build import (  # noqa: E402
    POINT_CLOUD_INLINE_MAX, POINT_CLOUD_STAGING_THRESHOLD, inline_mesh, inline_point_cloud, mesh_levels)
from csc_gh.ply import write_ply_cloud, write_ply_mesh  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

METERS_TO_MM = 1000.0


# READING ------------------------------------------------------------------------------
def load_mesh(path):
    """``(vertices, faces, colors)`` of a stone's mesh; colors as (n, 3) uint8 or None."""
    mesh = trimesh.load(path, process=False, force='mesh')
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise ValueError(f'{Path(path).name}: no triangle mesh')
    colors = None
    if mesh.visual.kind == 'vertex':
        colors = np.asarray(mesh.visual.vertex_colors)[:, :3].astype(np.uint8)
    return np.asarray(mesh.vertices, dtype=np.float64), np.asarray(mesh.faces, dtype=np.int64), colors


def load_cloud(path):
    """``(points, colors)`` of a stone's point cloud; colors as (n, 3) uint8 or None."""
    cloud = trimesh.load(path, process=False)
    points = np.asarray(cloud.vertices, dtype=np.float64)
    if len(points) == 0:
        raise ValueError(f'{Path(path).name}: no points')
    colors = None
    raw = getattr(cloud, 'colors', None)
    if raw is not None and len(raw) == len(points):
        colors = np.asarray(raw)[:, :3].astype(np.uint8)
    return points, colors


# MEASURING ----------------------------------------------------------------------------
def extents_of(points) -> np.ndarray:
    points = np.asarray(points, dtype=np.float64)
    return points.max(axis=0) - points.min(axis=0)


def size_flags(extents, low=epfl.MM_RANGE[0], high=epfl.MM_RANGE[1]):
    """A flag for an extent outside ``low .. high`` (mm). The data is never rescaled to make it fit."""
    return [f'extent {round(float(e), 1)} mm is outside {low:g}..{high:g} mm'
            for e in extents if not low <= float(e) <= high]


def cloud_scale(mesh_extents, cloud_extents):
    """The factor that brings the cloud to the mesh's unit: 1000 when the cloud is about 1/1000 of the mesh
    (metres against mm), 1 when the two agree, None when neither fits. "About" is within a factor of 2
    either way: a cloud with a few stray points is a little larger than its mesh (two stones of the dataset
    are 25 to 40 % larger), which must not decide the unit."""
    ratio = float(np.max(mesh_extents)) / max(float(np.max(cloud_extents)), 1e-12)
    for factor in (1.0, METERS_TO_MM):
        if 0.5 <= ratio / factor <= 2.0:
            return factor
    return None


# REDUCING -----------------------------------------------------------------------------
def decimate(vertices, faces, colors, target_faces: int):
    """The mesh reduced to about ``target_faces`` triangles by quadric decimation; the colour of a new
    vertex is that of the nearest original vertex. Returns ``(vertices, faces, colors or None)``."""
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    if len(mesh.faces) <= target_faces:
        return vertices, faces, colors
    small = mesh.simplify_quadric_decimation(face_count=int(target_faces))
    new_colors = None
    if colors is not None:
        _, nearest = cKDTree(vertices).query(np.asarray(small.vertices))
        new_colors = np.asarray(colors)[nearest]
    return np.asarray(small.vertices, dtype=np.float64), np.asarray(small.faces, dtype=np.int64), new_colors


def rounded(body, digits=3):
    """The inline body with coordinates rounded to ``10 ** -digits`` of the unit (0.001 mm): small files."""
    out = dict(body)
    for key in ('vertices', 'points'):
        if key in out:
            out[key] = [[round(c, digits) for c in row] for row in out[key]]
    return out


# ONE STONE ----------------------------------------------------------------------------
def prepare_stone(stone_id, mesh_path, cloud_path, out: Path):
    """Write the files of one stone into ``out / 'stones' / stone_id`` and return its meta (also written as
    ``meta.json``)."""
    started = time.time()
    folder = out / 'stones' / stone_id
    folder.mkdir(parents=True, exist_ok=True)
    vertices, faces, colors = load_mesh(mesh_path)
    points, point_colors = load_cloud(cloud_path)
    mesh_extents = extents_of(vertices)
    flags = size_flags(mesh_extents)
    probe = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    watertight = bool(probe.is_watertight)
    meta = {
        'id': stone_id, 'group': epfl.group_of(stone_id),
        'mesh_file': Path(mesh_path).name, 'cloud_file': Path(cloud_path).name,
        'vertices': int(len(vertices)), 'faces': int(len(faces)),
        'bbox_mm': [round(float(e), 2) for e in mesh_extents],
        'origin_mm': [round(float(v), 2) for v in vertices.min(axis=0)],
        'watertight': watertight,
        'volume_cm3': round(float(probe.volume) / 1000.0, 3) if watertight else None,
        'has_colors': colors is not None,
    }
    if not watertight:
        flags.append('mesh is not watertight (uploaded as it is)')
    files = {}

    # the mesh levels, by the client's rules ----------------------------------------------
    levels = mesh_levels(len(faces))
    if levels['preview_target']:
        pv, pf, pc = decimate(vertices, faces, colors, levels['preview_target'])
    else:
        pv, pf, pc = vertices, faces, colors
    preview = {'mesh': rounded(inline_mesh(pv, pf, pc))}
    meta['levels'] = {'preview_faces': int(len(pf)), 'reduced_faces': None, 'detailed': False}
    if levels['reduced_target']:
        rv, rf, rc = decimate(vertices, faces, colors, levels['reduced_target'])
        (folder / 'reduced.ply').write_bytes(write_ply_mesh(rv, rf, rc))
        meta['levels']['reduced_faces'] = int(len(rf))
        files['reduced.ply'] = (folder / 'reduced.ply').stat().st_size
    if levels['save_original']:
        (folder / 'detailed.ply').write_bytes(write_ply_mesh(vertices, faces, colors))
        meta['levels']['detailed'] = True
        files['detailed.ply'] = (folder / 'detailed.ply').stat().st_size

    # the cloud, in the mesh's unit -------------------------------------------------------
    factor = cloud_scale(mesh_extents, extents_of(points))
    cloud = {'points': int(len(points)), 'scale_to_mesh_unit': factor, 'inline_points': 0, 'staged': False}
    if factor is None:
        flags.append('point cloud and mesh sizes disagree: the cloud is left out')
    else:
        if factor != 1.0:
            flags.append(f'point cloud is in metres in the source: multiplied by {factor:g}')
        scaled = points * factor
        thin = inline_point_cloud(scaled, point_colors, POINT_CLOUD_INLINE_MAX)
        preview['cloud'] = rounded(thin)
        cloud['inline_points'] = int(len(thin['points']))
        cloud['bbox_mm'] = [round(float(e), 2) for e in extents_of(scaled)]
        if len(scaled) > POINT_CLOUD_STAGING_THRESHOLD:
            (folder / 'cloud.ply').write_bytes(write_ply_cloud(scaled, point_colors))
            cloud['staged'] = True
            files['cloud.ply'] = (folder / 'cloud.ply').stat().st_size
    meta['cloud'] = cloud

    # the colour of the stone: the mean of the scan -----------------------------------------
    source = point_colors if point_colors is not None else colors
    meta['mean_color'] = [int(round(float(c))) for c in np.asarray(source).mean(axis=0)] \
        if source is not None else None
    (folder / 'preview.json').write_text(json.dumps(preview, separators=(',', ':')), encoding='utf-8')
    files['preview.json'] = (folder / 'preview.json').stat().st_size
    meta['files'] = files
    meta['flags'] = flags
    meta['seconds'] = round(time.time() - started, 2)
    (folder / 'meta.json').write_text(json.dumps(meta, indent=1), encoding='utf-8')
    return meta


def _work(args):
    stone_id, mesh_path, cloud_path, out = args
    try:
        return prepare_stone(stone_id, Path(mesh_path), Path(cloud_path), Path(out))
    except Exception as error:                      # noqa: BLE001 - reported, the others go on
        return {'id': stone_id, 'error': f'{type(error).__name__}: {error}'}


# THE REPORT ---------------------------------------------------------------------------
def report(metas, errors) -> str:
    done = [m for m in metas if 'error' not in m]
    bad = [m['id'] for m in done if not m['watertight']]
    lines = ['# EPFL stones: prepared', '',
             f'Stones prepared: {len(done)}; failed: {len(errors)}; not watertight: {len(bad)}.', '']
    if bad:
        lines += ['Not watertight (uploaded as they are): ' + ', '.join(bad), '']
    groups = {}
    for m in done:
        groups.setdefault(m['group'], []).append(m)
    lines += ['| group | stones | faces (min / median / max) | not watertight |', '|---|---|---|---|']
    for g, items in sorted(groups.items()):
        faces = sorted(i['faces'] for i in items)
        lines.append(f'| {g} | {len(items)} | {faces[0]} / {faces[len(faces) // 2]} / {faces[-1]} | '
                     f'{sum(not i["watertight"] for i in items)} |')
    if done:
        extents = np.array([m['bbox_mm'] for m in done])
        lines += ['', f'Bounding boxes (mm): longest side {extents.max():.0f}, shortest side '
                  f'{extents.min():.0f}; every stone checked against {epfl.MM_RANGE[0]:g}..'
                  f'{epfl.MM_RANGE[1]:g} mm.']
        scales = {}
        for m in done:
            scales[m['cloud']['scale_to_mesh_unit']] = scales.get(m['cloud']['scale_to_mesh_unit'], 0) + 1
        lines += ['', 'Point cloud unit: ' + ', '.join(
            f'x{k:g} for {v} stone(s)' if k else f'unusable for {v} stone(s)' for k, v in sorted(
                scales.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))) +
            ' (the cloud is multiplied by the factor to the mesh unit, mm).']
        levels = {}
        for m in done:
            key = ('reduced' if m['levels']['reduced_faces'] else 'preview only'
                   if not m['levels']['detailed'] else 'detailed')
            levels[key] = levels.get(key, 0) + 1
        total = sum(sum(m['files'].values()) for m in done)
        lines += ['', 'Levels: ' + ', '.join(f'{v} {k}' for k, v in sorted(levels.items())) +
                  f'; files {total / 1e6:.0f} MB; staged clouds {sum(m["cloud"]["staged"] for m in done)}.']
    flagged = [m for m in done if [f for f in m['flags'] if 'multiplied by' not in f
                                   and 'not watertight' not in f]]
    lines += ['', '## Flags', ''] + ([f'- {m["id"]}: ' + '; '.join(
        f for f in m['flags'] if 'multiplied by' not in f and 'not watertight' not in f) for m in flagged]
        or ['- none beyond the unit of the clouds and the meshes that are not watertight'])
    lines += ['', '## Failed', ''] + ([f'- {e["id"]}: {e["error"]}' for e in errors] or ['- none'])
    return '\n'.join(lines) + '\n'


def main(args) -> int:
    root = epfl.find_root(args.data)
    out = common.out_dir(args.out)
    every = epfl.stone_files(root)
    stones = every
    if args.only:
        wanted = [s.strip() for s in args.only.split(',') if s.strip()]
        unknown = [s for s in wanted if s not in stones]
        if unknown:
            sys.exit(f'no such stone: {", ".join(unknown)}')
        stones = {s: stones[s] for s in wanted}
    if args.limit:
        stones = dict(list(stones.items())[:args.limit])
    todo = []
    for stone_id, (mesh_path, cloud_path) in stones.items():
        meta_file = out / 'stones' / stone_id / 'meta.json'
        if meta_file.is_file() and not args.force:
            continue
        todo.append((stone_id, str(mesh_path), str(cloud_path), str(out)))
    print(f'{len(stones)} stones, {len(todo)} to prepare ({args.jobs} jobs) from {root}', flush=True)
    started = time.time()
    if args.jobs > 1 and len(todo) > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            results = []
            for n, result in enumerate(pool.map(_work, todo), 1):
                results.append(result)
                if n % 25 == 0 or n == len(todo):
                    print(f'  {n} / {len(todo)} ({time.time() - started:.0f} s)', flush=True)
    else:
        results = [_work(t) for t in todo]
    errors = [r for r in results if 'error' in r]
    metas = []
    for stone_id in every:                      # prepare.json always lists every stone done, not only this run's
        meta_file = out / 'stones' / stone_id / 'meta.json'
        if meta_file.is_file():
            metas.append(json.loads(meta_file.read_text(encoding='utf-8')))
    (out / 'prepare.json').write_text(json.dumps({
        'run': epfl.RUN, 'source': epfl.DOI_URL, 'stones': metas, 'errors': errors}, indent=1), encoding='utf-8')
    (out / 'report.md').write_text(report(metas, errors), encoding='ascii', errors='replace')
    print(f'{len(metas)} stones prepared, {len(errors)} failed, '
          f'{sum(not m["watertight"] for m in metas)} not watertight, {time.time() - started:.0f} s')
    for e in errors[:10]:
        print(f'  failed {e["id"]}: {e["error"]}')
    return 1 if errors else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Prepare the EPFL stones as the Grasshopper client would send them.')
    parser.add_argument('--data', type=Path, default=epfl.DEFAULT_DATA,
                        help='the unpacked dataset (or the folder fetch.py wrote); default: the local rehearsal')
    parser.add_argument('--out', type=Path, default=epfl.DEFAULT_OUT, help='folder for the prepared files')
    parser.add_argument('--only', help='comma-separated stone ids, e.g. A0,B7')
    parser.add_argument('--limit', type=int, help='only the first N stones')
    parser.add_argument('--jobs', type=int, default=4, help='processes (default 4)')
    parser.add_argument('--force', action='store_true', help='prepare stones again that already have a meta.json')
    sys.exit(main(parser.parse_args()))
