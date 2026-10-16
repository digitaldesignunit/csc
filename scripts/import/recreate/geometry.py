"""Compute one watertight mesh per ReCreate product (decision 1 of the README).

    python -I -X utf8 geometry.py [--out <out folder>]

Needs manifold3d, trimesh, shapely, numpy (requirements-import.txt). Reads `<out>/parsed.json` (parse.py) and writes `<out>/meshes/<pilot>/<type>/<product>.ply` plus
`<out>/geometry.json` (per product: file, volume, bounding box, notes) and `<out>/geometry.md`.

Conventions of the data collection guidelines (section 3.3.1): x = length, z = height, y = thickness, mm;
three orthographic views, each a closed polygon in global coordinates: front (x, z), side (y, z), plan (x, y).
The element is the intersection of the three views extruded through each other; voids (windows, doors) are the
convex hulls of their corner points (8 per void, front and back face) and are subtracted; corbels are the
intersection of their two given views and are added. A mirrored product (`Mirrored`) is reflected about the
vertical mid-plane x = L / 2 (the guidelines say "about an axis" without naming it; for facade panels in a
corner this is the reflection that fits). Hollow-core slabs are parametric: x = length, y = width, z = height,
elliptical cores along x, equal internal webs, an optional structural topping. Radii / bevels are ignored (all
zero in this data; a non-zero one is reported).

Nothing here touches CSC: the PLY files are uploaded later like any captured mesh.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifold3d as m3d  # noqa: E402
import numpy as np  # noqa: E402
import recreate_common as common  # noqa: E402
import trimesh  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402
from shapely.geometry.polygon import orient  # noqa: E402

VIEWS = {
    'front': ('x', 'z', ('GENERAL / FRONT CROSS-SECTION [list]', 'GENERAL / ELEVATION [list]')),
    'side': ('y', 'z', ('GENERAL / SIDE CROSS-SECTION [list]', 'GENERAL / CROSS-SECTION [list]')),
    'plan': ('x', 'y', ('GENERAL / PLAN CROSS-SECTION [list]', 'GENERAL / PLAN [list]')),
}
CORBEL_VIEWS = {
    'front': ('x', 'z', ('CORBEL GEOMETRY / FRONT VIEW [list]',)),
    'side': ('y', 'z', ('CORBEL GEOMETRY / SIDE VIEW [list]',)),
    'plan': ('x', 'y', ('CORBEL GEOMETRY / PLAN VIEW [list]',)),
}
# the axis a view is extruded along
NORMAL = {('x', 'z'): 'y', ('y', 'z'): 'x', ('x', 'y'): 'z'}


def field(rec, name):
    """A record value by the last part of its header (e.g. 'Product ID')."""
    for key, value in rec.items():
        if not key.endswith(' []') and key.split(' / ')[-1] == name:
            return value
    return None


def column(rec, key):
    values = rec.get(key + ' []')
    if values is None:
        values = [rec.get(key)]
    return [v for v in values if v is not None]


def polygon(rec, prefixes, a, b):
    """The closed polygon of a view, or None when the view is empty / all zero."""
    for prefix in prefixes:
        xs = column(rec, f'{prefix} / {a.upper()}')
        ys = column(rec, f'{prefix} / {b.upper()}')
        if xs and ys:
            n = min(len(xs), len(ys))
            pts = [(float(xs[i]), float(ys[i])) for i in range(n)]
            poly = Polygon(pts)
            if poly.area > 0:
                radii = [r for k in rec if k.startswith(prefix) and 'Radius' in k
                         for r in column(rec, k.removesuffix(' []')) if r]
                return orient(poly, 1.0), bool(radii)
    return None, False


def prism(poly: Polygon, plane, lo, hi) -> m3d.Manifold:
    """Extrude a polygon of plane (a, b) along the third axis from lo to hi."""
    cs = m3d.CrossSection([list(poly.exterior.coords)[:-1]], m3d.FillRule.Positive)
    solid = m3d.Manifold.extrude(cs, hi - lo)          # (a, b, w), w in [0, hi - lo]
    w = NORMAL[plane]
    if plane == ('x', 'y'):                            # (x, y, z)
        return solid.translate((0, 0, lo))
    if plane == ('y', 'z'):                            # (u, v, w) -> (w, u, v): cyclic, det +1
        return solid.transform([[0, 0, 1, lo], [1, 0, 0, 0], [0, 1, 0, 0]])
    # ('x', 'z'): (u, v, w) -> (u, -w, v) has det +1; then shift y into [lo, hi]
    return solid.transform([[1, 0, 0, 0], [0, 0, -1, hi], [0, 1, 0, 0]])


def bounds_of(polys):
    lo = {'x': math.inf, 'y': math.inf, 'z': math.inf}
    hi = {'x': -math.inf, 'y': -math.inf, 'z': -math.inf}
    for plane, poly in polys:
        x0, y0, x1, y1 = poly.bounds
        for axis, (a0, a1) in zip(plane, ((x0, x1), (y0, y1))):
            lo[axis], hi[axis] = min(lo[axis], a0), max(hi[axis], a1)
    return lo, hi


def extent(poly, plane, axis):
    x0, y0, x1, y1 = poly.bounds
    return (x1 - x0) if plane[0] == axis else (y1 - y0)


def swap_checked(polys, notes, what):
    """A view whose two axes were entered the wrong way round (the German interior
    walls give the plan as x 0..150, y 0..4810 for a 4810 mm long, 150 mm thick wall):
    when swapping its coordinates makes both its extents agree with the other views,
    swap them and say so."""
    out = []
    for plane, poly in polys:
        others = [(p, q) for p, q in polys if p != plane]

        def agrees(pl, pg):
            for axis in pl:
                theirs = [extent(q, p, axis) for p, q in others if axis in p]
                if theirs and abs(extent(pg, pl, axis) - theirs[0]) > 0.05 * max(theirs[0], 1):
                    return False
            return True
        if not agrees(plane, poly):
            swapped = Polygon([(b, a) for a, b in poly.exterior.coords])
            if agrees(plane, swapped):
                notes.append(f'{what}: {"/".join(plane)} view entered with its axes swapped; swapped back')
                poly = orient(swapped, 1.0)
        out.append((plane, poly))
    return out


def views_solid(rec, views, notes, what):
    polys, rounded = [], False
    for name, (a, b, prefixes) in views.items():
        poly, has_radius = polygon(rec, prefixes, a, b)
        rounded |= has_radius
        if poly is not None:
            polys.append(((a, b), poly))
    if len(polys) < 2:
        return None
    if rounded:
        notes.append(f'{what}: radius / bevel given and ignored')
    polys = swap_checked(polys, notes, what)
    lo, hi = bounds_of(polys)
    solid = None
    for plane, poly in polys:
        w = NORMAL[plane]
        part = prism(poly, plane, lo[w] - 1.0, hi[w] + 1.0)
        solid = part if solid is None else solid ^ part     # ^ = intersection
    return solid


def voids_of(rec, notes):
    xs = column(rec, 'WALL VOIDS / Void Corners [list] / X')
    zs = column(rec, 'WALL VOIDS / Void Corners [list] / Z')
    ys = column(rec, 'WALL VOIDS / Void Corners [list] / Y')
    n = min(len(xs), len(ys), len(zs))
    if n == 0:
        return []
    if n % 8:
        notes.append(f'void corners: {n} points, not a multiple of 8; voids skipped')
        return []
    out = []
    for i in range(0, n, 8):
        pts = np.array([[xs[j], ys[j], zs[j]] for j in range(i, i + 8)], dtype=float)
        # through the full thickness: stretch the two faces 1 mm outwards
        y0, y1 = pts[:, 1].min(), pts[:, 1].max()
        pts[pts[:, 1] == y0, 1] -= 1.0
        pts[pts[:, 1] == y1, 1] += 1.0
        out.append(m3d.Manifold.hull_points(pts.tolist()))
    declared = rec.get('WALL VOIDS / Count')
    if declared is not None and declared != len(out):
        notes.append(f'void count {declared}, corner sets {len(out)} (corner sets used)')
    return out


def element_solid(rec, notes):
    solid = views_solid(rec, VIEWS, notes, 'element')
    if solid is None:
        raise ValueError('fewer than two views')
    for void in voids_of(rec, notes):
        solid = solid - void
    corbels = rec.get('CORBEL GEOMETRY / Count')
    if corbels:
        corbel = views_solid(rec, CORBEL_VIEWS, notes, 'corbel')
        if corbel is None:
            notes.append('corbel count given but fewer than two corbel views; corbel skipped')
        else:
            solid = solid + corbel
    if rec.get('Mirrored') or rec.get('Mirrored [boolean]'):
        bb = solid.bounding_box()
        length = bb[3] + bb[0]
        solid = solid.transform([[-1, 0, 0, length], [0, 1, 0, 0], [0, 0, 1, 0]])
        # a reflection flips the orientation: manifold keeps it consistent
        notes.append('mirrored about x = L / 2')
    return solid


def hcs_solid(rec, notes):
    h = float(field(rec, 'Height (mm)'))
    length = float(field(rec, 'Length (mm)'))
    width = float(field(rec, 'Width (mm)'))
    n = int(rec.get('GEOMETRY / Voids / Count') or 0)
    dx = float(rec.get('GEOMETRY / Voids / Diameter X (mm)') or 0)
    dz = float(rec.get('GEOMETRY / Voids / Diameter Y (mm)') or 0)
    bottom = float(rec.get('GEOMETRY / Voids / Bottom Cover (mm)') or 0)
    web = float(rec.get('GEOMETRY / Voids / Web Thickness [External] (mm)') or 0)
    solid = m3d.Manifold.cube((length, width, h))
    if n and dx and dz:
        inner = (width - 2 * web - n * dx) / (n - 1) if n > 1 else 0.0
        if inner < 0:
            notes.append(f'cores do not fit the width ({inner:.1f} mm webs); cores skipped')
        else:
            z = bottom + dz / 2
            for i in range(n):
                y = web + dx / 2 + i * (dx + inner)
                circle = m3d.CrossSection.circle(0.5, 48).scale((dx, dz)).translate((y, z))
                core = m3d.Manifold.extrude(circle, length + 2.0)
                # (u=y, v=z, w=x) -> (w - 1, u, v)
                core = core.transform([[0, 0, 1, -1.0], [1, 0, 0, 0], [0, 1, 0, 0]])
                solid = solid - core
            if abs(inner - web) > 1 and width < 1150:
                notes.append(f'cut width {width:.0f} mm: cores spread evenly ({inner:.1f} mm internal '
                             f'webs); the asymmetric webs of the notes are not reproduced')
    if rec.get('STRUCTURAL TOPPING / Present [boolean]'):
        t = float(rec.get('STRUCTURAL TOPPING / Thickness (mm)') or 0)
        if t > 0:
            solid = solid + m3d.Manifold.cube((length, width, t)).translate((0, 0, h))
            notes.append(f'structural topping {t:.0f} mm')
    return solid


def to_trimesh(solid: m3d.Manifold) -> trimesh.Trimesh:
    mesh = solid.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3],
                           faces=np.asarray(mesh.tri_verts), process=True)


def main(out: Path) -> int:
    parsed = json.loads((out / 'parsed.json').read_text(encoding='utf-8'))
    results, failures = [], []
    for entry in parsed['element_files']:
        for rec in entry['sheets']['Geometry']['records']:
            pid = field(rec, 'Product ID')
            notes = []
            try:
                solid = (hcs_solid if entry['type'] == 'HCS' else element_solid)(rec, notes)
                mesh = to_trimesh(solid)
            except Exception as exc:                       # noqa: BLE001 -- reported
                failures.append({'file': entry['file'], 'product': pid, 'error': str(exc)})
                continue
            rel = Path('meshes') / entry['pilot'] / entry['type'] / (safe(pid) + '.ply')
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            mesh.export(out / rel, file_type='ply', encoding='binary')
            lo, hi = mesh.bounds
            results.append({
                'file': entry['file'], 'pilot': entry['pilot'], 'type': entry['type'],
                'product': pid, 'ply': rel.as_posix(), 'watertight': bool(mesh.is_watertight),
                'volume_m3': round(float(mesh.volume) / 1e9, 4), 'faces': int(len(mesh.faces)),
                'bbox_mm': [round(float(v), 1) for v in (hi - lo)],
                'origin_mm': [round(float(v), 1) for v in lo], 'notes': notes})
    (out / 'geometry.json').write_text(json.dumps({'products': results, 'failures': failures},
                                                  indent=1), encoding='utf-8')
    (out / 'geometry.md').write_text(report(results, failures), encoding='ascii', errors='replace')
    print(f'{len(results)} meshes, {len(failures)} failures, '
          f'{sum(not r["watertight"] for r in results)} not watertight')
    return 0 if not failures else 1


def safe(name) -> str:
    return ''.join(c if c.isalnum() or c in '-_.' else '_' for c in str(name)).strip('.')


def report(results, failures) -> str:
    lines = ['# ReCreate meshes', '', '| pilot | type | product | m3 | bbox mm (x, y, z) | faces | notes |',
             '|---|---|---|---|---|---|---|']
    for r in results:
        flag = '' if r['watertight'] else ' NOT WATERTIGHT'
        lines.append(f'| {r["pilot"]} | {r["type"]} | {r["product"]} | {r["volume_m3"]} | '
                     f'{" x ".join(str(v) for v in r["bbox_mm"])} | {r["faces"]} | '
                     f'{"; ".join(r["notes"])}{flag} |')
    if failures:
        lines += ['', '## Failures', ''] + [f'- {f["file"]} / {f["product"]}: {f["error"]}'
                                            for f in failures]
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compute one watertight mesh per ReCreate product.')
    parser.add_argument('--out', type=Path, default=common.DEFAULT_OUT,
                        help='folder with parsed.json (parse.py); meshes and geometry.json go here')
    args = parser.parse_args()
    out = common.out_dir(args.out)
    if not (out / 'parsed.json').is_file():
        sys.exit(f'no parsed.json in {out}: run parse.py first')
    sys.exit(main(out))
