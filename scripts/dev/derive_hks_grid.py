"""Derive the frozen HKS time grid from a set of mesh assets (decision 8.6).

For every ``meshes/<snapshot>/<i>/detailed.ply`` (else ``reduced.ply``)
under the given folder this computes the shape's own time bounds in
area-normalised units as ``make_time_grid`` does
(``t_min = 4 / lambda_max``, ``t_max = 4 / lambda_1``, eigenvalues scaled by
the total mass), then takes the **geometric mean** of the bounds over the
catalogue. The printed ``HKS_T_MIN`` / ``HKS_T_MAX`` go into
``apps/descriptors/hks.py`` and are not changed afterwards (a change is an
``HKS_VERSION`` bump and a recompute).

Usage::

    python scripts/dev/derive_hks_grid.py D:\\...\\260916_CSC_ASSETS\\meshes
    python scripts/dev/derive_hks_grid.py <meshes> --limit 20
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / 'src' / 'backend'))

from apps.catalog.geometry_source import Source  # noqa: E402
from apps.catalog.geometry_mesh_export import (  # noqa: E402
    load_trimesh_from_ply_file,
)
from apps.descriptors.hks import HKS_EIGS, spectrum  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('meshes', type=Path)
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()

    files = []
    for folder in sorted(args.meshes.glob('*/*')):
        for name in ('detailed.ply', 'reduced.ply'):
            if (folder / name).is_file():
                files.append(folder / name)
                break
    if args.limit:
        files = files[:args.limit]
    log_min, log_max, failed = [], [], 0
    started = time.time()
    for path in files:
        try:
            mesh = load_trimesh_from_ply_file(str(path))
            evals, _, mass = spectrum(Source('meshes', 'original',
                                             meshes=[mesh]))
        except Exception as exc:                           # noqa: BLE001
            failed += 1
            print(f'  failed {path.parent.parent.name}: {exc}')
            continue
        scaled = evals * mass.sum()
        t_min, t_max = 4.0 / scaled[-1], 4.0 / scaled[0]
        log_min.append(np.log(t_min))
        log_max.append(np.log(t_max))
    ok = len(log_min)
    print(f'{ok} of {len(files)} shapes ({failed} failed, '
          f'{time.time() - started:.0f} s), {HKS_EIGS} eigenpairs each')
    if not ok:
        return 1
    print(f'per-shape t_min: {np.exp(min(log_min)):.3e} .. '
          f'{np.exp(max(log_min)):.3e}')
    print(f'per-shape t_max: {np.exp(min(log_max)):.3e} .. '
          f'{np.exp(max(log_max)):.3e}')
    print(f'HKS_T_MIN = {np.exp(np.mean(log_min)):.6e}')
    print(f'HKS_T_MAX = {np.exp(np.mean(log_max)):.6e}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
