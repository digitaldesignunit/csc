"""Render a few computed meshes to one PNG for a visual check.

    python -I -X utf8 preview.py [--out <out folder>] [--products 5415_G01,7496_50]

Writes `<out>/preview.png` (shaded meshes, one per product id). Needs matplotlib, numpy and trimesh
(requirements-import.txt).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib  # noqa: E402

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import recreate_common as common  # noqa: E402
import trimesh  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

DEFAULT_PRODUCTS = '5415_G01,7496_50'


def main(out: Path, pick) -> int:
    g = {p['product']: p for p in json.loads((out / 'geometry.json').read_text(encoding='utf-8'))['products']}
    missing = [pid for pid in pick if pid not in g]
    if missing:
        sys.exit(f'no such product in geometry.json: {", ".join(missing)}')
    fig = plt.figure(figsize=(5 * len(pick), 5.5))
    for i, pid in enumerate(pick, 1):
        p = g[pid]
        mesh = trimesh.load(out / p['ply'])
        ax = fig.add_subplot(1, len(pick), i, projection='3d')
        tris = mesh.vertices[mesh.faces]
        light = np.array([0.4, -0.6, 0.7])
        light /= np.linalg.norm(light)
        shade = 0.35 + 0.65 * np.clip(mesh.face_normals @ light, 0, 1)
        ax.add_collection3d(Poly3DCollection(tris, facecolors=np.outer(shade, [0.75, 0.75, 0.72]),
                                             edgecolors=(0.2, 0.2, 0.2, 0.25), linewidths=0.2))
        lo, hi = mesh.bounds
        ax.set_box_aspect(hi - lo)
        ax.set_xlim(lo[0], hi[0])
        ax.set_ylim(lo[1], hi[1])
        ax.set_zlim(lo[2], hi[2])
        ax.view_init(elev=22, azim=-60)
        ax.set_title(f'{p["pilot"]} {p["type"]} {pid}\n{p["volume_m3"]} m3', fontsize=9)
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(out / 'preview.png', dpi=110)
    print(out / 'preview.png')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Render computed ReCreate meshes for a visual check.')
    parser.add_argument('--out', type=Path, default=common.DEFAULT_OUT,
                        help='folder with geometry.json and the meshes; preview.png goes here')
    parser.add_argument('--products', default=DEFAULT_PRODUCTS,
                        help='comma-separated product ids (default: one wall and one hollow-core slab)')
    args = parser.parse_args()
    out = common.out_dir(args.out)
    if not (out / 'geometry.json').is_file():
        sys.exit(f'no geometry.json in {out}: run geometry.py first')
    sys.exit(main(out, [p.strip() for p in args.products.split(',') if p.strip()]))
