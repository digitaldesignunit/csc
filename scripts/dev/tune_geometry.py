"""Tuning tables for the shape-class and complexity thresholds (plan P5).

The thresholds in ``apps/catalog/shape_class.py`` and ``complexity.py`` are
guesses until they are checked against the data. This reads the snapshots of
a migrated database whose frame, hull scores and proxies the geometry runner
has derived (``rehearse_06.py`` runs it, then prints this report) and shows:

* **Shape class**: the extent ratios and boxscores per dataset, the class
  counts under the current thresholds, how the counts move over a grid of
  thresholds, and the derived class against the piece's ``original_function``
  (a weak hint: beams and columns should come out linear, slabs and plates
  planar).
* **Complexity**: the confusion table of the derived level against the
  **71 authored ``beyond_debris`` ratings** (the only genuine labels), the
  same under the best thresholds of a grid search, and the residual /
  boxscore values behind them.

Nothing here changes a threshold: the user reviews the tables, then the
constants are edited and frozen.
"""
from __future__ import annotations

import itertools
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / 'src' / 'backend'))

from apps.catalog import complexity, shape_class  # noqa: E402

CLASSES = ('linear', 'planar', 'block', 'irregular')
EXPECTED = {'IfcBeam': 'linear', 'IfcColumn': 'linear', 'IfcMember': 'linear',
            'IfcSlab': 'planar', 'IfcPlate': 'planar', 'IfcWall': 'planar',
            'IfcCovering': 'planar'}


def collect(snapshots: Iterable[Dict[str, Any]],
            identities: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per snapshot with a frame, from the derived fields."""
    rows = []
    for snap in snapshots:
        bbx = snap.get('bbx')
        if not bbx:
            continue
        identity = identities[snap['identity_id']]
        primary = next((p for p in (snap.get('geometry') or {})
                        .get('proxies') or [] if p.get('role') == 'primary'),
                       None)
        fit = (primary or {}).get('fit') or {}
        p95 = fit.get('p95_mm')
        rows.append({
            'id': snap['_id'], 'dataset': identity['dataset'],
            'function': identity.get('original_function'),
            'extents': sorted(bbx, reverse=True),
            'boxscore': (snap.get('descriptors') or {}).get('boxscore'),
            'residual_ratio': (p95 / max(bbx)) if p95 is not None and max(bbx)
            else None,
            'authored': (snap.get('complexity')
                         if snap.get('complexity_source') == 'assigned'
                         else None),
            'derived_complexity': snap.get('complexity')
            if snap.get('complexity_source') == 'derived' else None,
            'shape_class': snap.get('shape_class'),
            'shape_class_source': snap.get('shape_class_source'),
            'primitive': (primary or {}).get('primitive'),
        })
    return rows


def _quantiles(values: Sequence[float], qs=(0.05, 0.25, 0.5, 0.75, 0.95)):
    ordered = sorted(v for v in values if v is not None)
    if not ordered:
        return ['-'] * len(qs)
    return [f'{ordered[min(len(ordered) - 1, int(q * len(ordered)))]:.3g}'
            for q in qs]


def _classify(row, t_linear, t_planar, t_irregular) -> str:
    saved = (shape_class.T_LINEAR, shape_class.T_PLANAR,
             shape_class.T_IRREGULAR)
    shape_class.T_LINEAR, shape_class.T_PLANAR = t_linear, t_planar
    shape_class.T_IRREGULAR = t_irregular
    try:
        return shape_class.derive_shape_class(row['extents'], row['boxscore'])
    finally:
        (shape_class.T_LINEAR, shape_class.T_PLANAR,
         shape_class.T_IRREGULAR) = saved


def shape_class_report(rows: List[Dict[str, Any]]) -> List[str]:
    out = ['SHAPE CLASS', '']
    out.append(f'thresholds now: T_LINEAR {shape_class.T_LINEAR}, '
               f'T_PLANAR {shape_class.T_PLANAR}, '
               f'T_IRREGULAR {shape_class.T_IRREGULAR}')
    out.append('')
    out.append('per dataset: quantiles 5 / 25 / 50 / 75 / 95 %')
    by_dataset = defaultdict(list)
    for row in rows:
        by_dataset[row['dataset']].append(row)
    for dataset, items in sorted(by_dataset.items()):
        e1e2 = [r['extents'][0] / r['extents'][1] for r in items
                if r['extents'][1] > 0]
        e2e3 = [r['extents'][1] / r['extents'][2] for r in items
                if r['extents'][2] > 0]
        box = [r['boxscore'] for r in items]
        out.append(f'  {dataset} ({len(items)})')
        out.append(f'    e1/e2     {" ".join(_quantiles(e1e2))}')
        out.append(f'    e2/e3     {" ".join(_quantiles(e2e3))}')
        out.append(f'    boxscore  {" ".join(_quantiles(box))}')
    out.append('')
    out.append('class counts under the current thresholds, per dataset '
               '(assigned classes excluded)')
    for dataset, items in sorted(by_dataset.items()):
        counts = Counter(_classify(r, shape_class.T_LINEAR,
                                   shape_class.T_PLANAR,
                                   shape_class.T_IRREGULAR) for r in items)
        out.append(f'  {dataset:28s} '
                   + '  '.join(f'{c} {counts.get(c, 0)}' for c in CLASSES))
    out.append('')
    out.append('sensitivity: class counts over all pieces')
    out.append('  T_LINEAR T_PLANAR T_IRREGULAR | '
               + ' '.join(f'{c:>9s}' for c in CLASSES))
    for tl, tp, ti in itertools.product((2.5, 3, 4, 5), (2.5, 3, 4), (15, 25, 40)):
        counts = Counter(_classify(r, tl, tp, ti) for r in rows)
        out.append(f'  {tl:8g} {tp:8g} {ti:11g} | '
                   + ' '.join(f'{counts.get(c, 0):9d}' for c in CLASSES))
    out.append('')
    out.append('derived class by original_function (current thresholds)')
    table = defaultdict(Counter)
    for row in rows:
        table[row['function']][_classify(
            row, shape_class.T_LINEAR, shape_class.T_PLANAR,
            shape_class.T_IRREGULAR)] += 1
    for function, counts in sorted(table.items(), key=lambda kv: str(kv[0])):
        expected = EXPECTED.get(function)
        out.append(f'  {str(function):26s} '
                   + '  '.join(f'{c} {counts.get(c, 0)}' for c in CLASSES)
                   + (f'   (expected {expected})' if expected else ''))
    return out


def _level(value, thresholds) -> int:
    return 0 if value is None else sum(value >= t for t in thresholds)


def _complexity(row, t_residual, t_box) -> int:
    level = max(_level(row['residual_ratio'], t_residual),
                _level(row['boxscore'], t_box))
    return max(level, 2) if row['shape_class'] == 'composite' else level


def _confusion(rows, t_residual, t_box) -> List[str]:
    labels = sorted({r['authored'] for r in rows})
    table = {(a, d): 0 for a in labels for d in range(4)}
    for row in rows:
        table[(row['authored'], _complexity(row, t_residual, t_box))] += 1
    out = ['    authored \\ derived   0    1    2    3']
    for a in labels:
        out.append(f'    {a:^18d} ' + ' '.join(
            f'{table[(a, d)]:4d}' for d in range(4)))
    exact = sum(table[(a, a)] for a in labels)
    near = sum(v for (a, d), v in table.items() if abs(a - d) <= 1)
    total = sum(table.values())
    out.append(f'    exact {exact}/{total} ({exact / total:.0%}), '
               f'within one level {near}/{total} ({near / total:.0%})')
    return out


def complexity_report(rows: List[Dict[str, Any]]) -> List[str]:
    labelled = [r for r in rows if r['authored'] is not None]
    out = ['COMPLEXITY', '']
    out.append(f'{len(labelled)} authored ratings (beyond_debris); '
               f'thresholds now: residual {tuple(complexity.T_RESIDUAL)}, '
               f'boxscore {tuple(complexity.T_BOXSCORE)}')
    if not labelled:
        return out
    out.append('')
    out.append('current thresholds')
    out += _confusion(labelled, complexity.T_RESIDUAL, complexity.T_BOXSCORE)
    out.append('')
    out.append('values per authored level: residual p95 / e1 and boxscore '
               '(quantiles 5 / 25 / 50 / 75 / 95 %)')
    for level in sorted({r['authored'] for r in labelled}):
        items = [r for r in labelled if r['authored'] == level]
        out.append(f'  level {level} ({len(items)})')
        out.append('    residual  ' + ' '.join(_quantiles(
            [r['residual_ratio'] for r in items])))
        out.append('    boxscore  ' + ' '.join(_quantiles(
            [r['boxscore'] for r in items])))
    residual_grid = [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12]
    box_grid = [2, 5, 10, 15, 20, 30, 45]
    best = []
    for r in itertools.combinations(residual_grid, 3):
        for b in itertools.combinations(box_grid, 3):
            exact = sum(_complexity(row, r, b) == row['authored']
                        for row in labelled)
            near = sum(abs(_complexity(row, r, b) - row['authored']) <= 1
                       for row in labelled)
            best.append((exact, near, r, b))
    best.sort(key=lambda item: (-item[0], -item[1]))
    out.append('')
    out.append('grid search, best 5 by exact agreement')
    for exact, near, r, b in best[:5]:
        out.append(f'  exact {exact}/{len(labelled)}, within one {near}: '
                   f'residual {r}, boxscore {b}')
    out.append('')
    out.append('confusion under the best thresholds')
    out += _confusion(labelled, best[0][2], best[0][3])
    out.append('')
    unlabelled = [r for r in rows if r['authored'] is None]
    counts = Counter(_complexity(r, complexity.T_RESIDUAL,
                                 complexity.T_BOXSCORE) for r in unlabelled)
    out.append(f'unlabelled pieces ({len(unlabelled)}), levels under the '
               f'current thresholds: '
               + ' '.join(f'{k} {counts.get(k, 0)}' for k in range(4)))
    return out


def report(rows: List[Dict[str, Any]]) -> str:
    return '\n'.join(shape_class_report(rows) + [''] + complexity_report(rows))
