"""Check the computed bars against the computed meshes.

    python -I -X utf8 check_bars.py [--out <out folder>]

For every product and reinforcement type: the share of sample points (every 25 mm along each bar) that lie
inside the element's mesh. Writes `<out>/bars_check.md`. Needs numpy and trimesh (requirements-import.txt).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import recreate_common as common  # noqa: E402
import trimesh  # noqa: E402


def sample_points(bars, step: float = 25.0):
    """Points every ``step`` mm along the centre lines of the bars."""
    pts = []
    for bar in bars:
        p = np.asarray(bar['points'], dtype=float)
        for a, b in zip(p[:-1], p[1:]):
            n = max(2, int(np.linalg.norm(b - a) / step) + 1)
            pts.append(a + (b - a) * np.linspace(0, 1, n)[:, None])
    return np.vstack(pts)


def main(out: Path) -> int:
    plan = json.loads((out / 'plan.json').read_text(encoding='utf-8'))
    geo = {g['product']: g for g in json.loads((out / 'geometry.json').read_text(encoding='utf-8'))['products']}
    seen, rows = set(), []
    for item in plan['items']:
        layout = next((r for r in item['evidence'] if r['method'] == 'reinforcement_layout'), None)
        if not layout:
            continue
        key = (item['product'], item['identity']['attributes']['recreate']['reinf_id'])
        if key in seen:
            continue
        seen.add(key)
        mesh = trimesh.load(out / geo[item['product']]['ply'])
        pts = sample_points(layout['payload']['bars'])
        inside = mesh.contains(pts)
        rows.append((key[0], key[1], len(layout['payload']['bars']), len(pts), float(inside.mean())))
    rows.sort(key=lambda r: r[4])
    lines = ['| product | reinf | bars | samples | inside |', '|---|---|---|---|---|']
    lines += [f'| {a} | {b} | {c} | {d} | {e:.1%} |' for a, b, c, d, e in rows]
    (out / 'bars_check.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines[:14]))
    if rows:
        print('...', len(rows), 'pairs; median inside', f'{np.median([r[4] for r in rows]):.1%}')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Share of bar sample points inside the meshes.')
    parser.add_argument('--out', type=Path, default=common.DEFAULT_OUT,
                        help='folder with plan.json, geometry.json and the meshes')
    args = parser.parse_args()
    out = common.out_dir(args.out)
    if not (out / 'plan.json').is_file():
        sys.exit(f'no plan.json in {out}: run plan.py first')
    sys.exit(main(out))
