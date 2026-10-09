#!/usr/bin/env python3.13
"""
The rebound hammer method (spec A.1, EN 12504-2:2021; decisions 8.40, 8.41,
8.43): what the server recomputes, what it refuses and what it only warns
about. Pure functions.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import math
import statistics
from typing import Any, Dict, List, Optional, Tuple

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.evidence.payloads import (
    Q_HAMMERS,
    ReboundHammerPayload,
)
from apps.catalog.evidence.types import DerivedModelKind, Prepared, Problem

MIN_READINGS = 9                    # EN 12504-2
DISCARD_SHARE = (1, 5)              # more than 20 % of the readings ...
DISCARD_DEVIATION = (1, 4)          # ... deviate by more than 25 %
ANVIL_TOLERANCE = 3.0               # +-3 of the expected anvil reading
MAX_CARBONATION_MM = 5.0            # German annex NA.6 / NA.7
THICKNESS_FIRM_SUPPORT_MM = 100.0   # 12504-2, 6.1
GRID_TOLERANCE = 1e-3               # unit vectors, orthogonality
POINT_TOLERANCE_MM = 0.01           # position.point against the grid centre

DERIVED_KINDS = (
    DerivedModelKind(
        'din_en_13791_a20_na6', 'concrete_class',
        'DIN EN 13791/A20, NA.6 (rebound number R, N-type hammer)',
        'The strength class the user reads from the German annex table for '
        'the median R; the note names the table row. The server holds no '
        'table values and checks the conditions: N-type hammer, carbonation '
        'depth up to 5 mm or a ground surface, a valid median, a set that '
        'was not discarded.', needs_note=True),
    DerivedModelKind(
        'din_en_13791_a20_na7', 'concrete_class',
        'DIN EN 13791/A20, NA.7 (Q-value, Q_N hammer)',
        'The strength class the user reads from the German annex table for '
        'the median Q; the note names the table row. Conditions as for '
        'NA.6, with a Q_N hammer.', needs_note=True),
    DerivedModelKind(
        'en_13791_correlation', 'compressive_strength_in_situ',
        'EN 13791 site correlation',
        'The lower 5 % prediction bound of a correlation between rebound '
        'values and cores taken at the same locations (at least 8 pairs, '
        'extrapolation at most 4 MPa). The correlation is made outside CSC; '
        'the reference names it and its report is an attachment.',
        needs_reference=True),
)


def round_half_up(value: float) -> int:
    """Whole number, halves up (Python's round() goes to even)."""
    return int(math.floor(value + 0.5))


def _readings_stats(readings: List[float], rejected: List[int],
                    policy: str) -> Tuple[List[float], float, bool]:
    """(valid readings, their median, set discarded)."""
    valid = [r for i, r in enumerate(readings) if i not in set(rejected)]
    median = statistics.median(valid)
    discarded = False
    if policy == 'en_12504_2':
        deviating = sum(
            1 for r in valid
            if abs(r - median) * DISCARD_DEVIATION[1]
            > abs(median) * DISCARD_DEVIATION[0])
        discarded = deviating * DISCARD_SHARE[1] > len(valid) \
            * DISCARD_SHARE[0]
    return valid, median, discarded


def _norm(vector: List[float]) -> float:
    return math.sqrt(sum(c * c for c in vector))


def grid_points(grid: Dict[str, Any]) -> List[List[float]]:
    """Impact points, row by row: reading i belongs to point i."""
    ox, oy, oz = grid['origin']
    u, v, s = grid['u'], grid['v'], grid['spacing_mm']
    points = []
    for row in range(grid['rows']):
        for col in range(grid['cols']):
            points.append([round(ox + u[0] * col * s + v[0] * row * s, 6),
                           round(oy + u[1] * col * s + v[1] * row * s, 6),
                           round(oz + u[2] * col * s + v[2] * row * s, 6)])
    return points


def grid_centre(grid: Dict[str, Any]) -> List[float]:
    cols, rows, s = grid['cols'], grid['rows'], grid['spacing_mm']
    ox, oy, oz = grid['origin']
    u, v = grid['u'], grid['v']
    a, b = (cols - 1) * s / 2.0, (rows - 1) * s / 2.0
    return [round(ox + u[0] * a + v[0] * b, 6),
            round(oy + u[1] * a + v[1] * b, 6),
            round(oz + u[2] * a + v[2] * b, 6)]


def _check_grid(payload: Dict[str, Any], problems: List[Problem]) -> None:
    grid = payload['test_area']['grid']
    where = 'payload.test_area.grid'
    if grid['rows'] * grid['cols'] != len(payload['readings']):
        problems.append(Problem(
            where, f'rows x cols is {grid["rows"] * grid["cols"]} but there '
                   f'are {len(payload["readings"])} readings: one reading '
                   f'per grid point'))
    if grid['spacing_mm'] < payload['test_area']['min_spacing_mm']:
        problems.append(Problem(
            f'{where}.spacing_mm',
            f'{grid["spacing_mm"]} mm is less than min_spacing_mm '
            f'({payload["test_area"]["min_spacing_mm"]} mm)'))
    u, v = grid['u'], grid['v']
    for name, vector in (('u', u), ('v', v)):
        if abs(_norm(vector) - 1.0) > GRID_TOLERANCE:
            problems.append(Problem(f'{where}.{name}',
                                    'a unit vector (length 1) is needed'))
    if abs(sum(a * b for a, b in zip(u, v))) > GRID_TOLERANCE:
        problems.append(Problem(where, 'u and v must be orthogonal'))


def _anvil_warnings(check: Optional[Dict[str, Any]]) -> List[str]:
    if not check:
        return []
    out = []
    series = [('before', check['expected'], check['before'])]
    if check.get('after'):
        series.append(('after', check['expected'], check['after']))
    second = check.get('second_anvil')
    if second:
        series.append(('second anvil', second['expected'], second))
    for name, expected, data in series:
        for reading in data['readings']:
            if abs(reading - expected) > ANVIL_TOLERANCE:
                out.append(f'anvil check ({name}): reading {reading:g} is '
                           f'outside {expected:g} +- {ANVIL_TOLERANCE:g}')
    return out


def prepare(model: ReboundHammerPayload, ctx: Dict[str, Any]) -> Prepared:
    """Recompute median, valid count and the discard rule; check the grid
    and the hammer; derive the summary (never a strength, A.1)."""
    payload = model.model_dump(by_alias=True, mode='json')
    problems: List[Problem] = []
    warnings: List[str] = []
    readings = payload['readings']
    rejected = payload['rejected_reading_indices']

    if len(readings) < MIN_READINGS:
        problems.append(Problem(
            'payload.readings',
            f'at least {MIN_READINGS} readings are required '
            f'(EN 12504-2); got {len(readings)}'))
    bad = [i for i in rejected if not 0 <= i < len(readings)]
    if bad or len(set(rejected)) != len(rejected):
        problems.append(Problem(
            'payload.rejected_reading_indices',
            'indices must be unique and point at a reading'))
    elif len(set(rejected)) >= len(readings):
        problems.append(Problem('payload.rejected_reading_indices',
                                'every reading is rejected: no valid '
                                'reading is left'))
    q_hammer = payload['instrument']['hammer_type'] in Q_HAMMERS
    if (payload['reading_unit'] == 'Q') != q_hammer:
        problems.append(Problem(
            'payload.reading_unit',
            'reading_unit "Q" belongs to the hammer types Q_N and Q_L, '
            'and only to them'))
    if payload['test_area'].get('grid'):
        _check_grid(payload, problems)

    summary = None
    position = None
    excluded = False
    if not problems:
        valid, median, discarded = _readings_stats(
            readings, rejected, payload['outlier_policy'])
        shown = round_half_up(median)
        for field, server in (('median', shown),
                              ('n_valid', len(valid)),
                              ('set_discarded', discarded)):
            sent = payload.get(field)
            if sent is not None and sent != server:
                problems.append(Problem(
                    f'payload.{field}',
                    f'the server computes {server!r} from the readings; '
                    f'got {sent!r}'))
        payload['median'] = shown
        payload['n_valid'] = len(valid)
        payload['set_discarded'] = discarded
        excluded = discarded
        quantity = 'q_value' if q_hammer else 'rebound_number'
        summary = {'quantity': quantity, 'value': shown, 'range': None,
                   'unit': '1', 'unit_entered': None, 'kind': 'measured',
                   'uncertainty': None}
        if discarded:
            warnings.append(
                'the set is discarded by the EN 12504-2 rule (more than '
                '20 % of the readings deviate by more than 25 % from the '
                'median); retest the area. The record stays as evidence of '
                'the attempt and does not count in the property fold')
        if len(valid) < MIN_READINGS:
            warnings.append(f'only {len(valid)} valid readings remain; EN '
                            f'12504-2 asks for at least {MIN_READINGS}')
        grid = payload['test_area'].get('grid')
        if grid:
            grid['points'] = grid_points(grid)
            position = {'kind': 'region', 'point': grid_centre(grid)}
    warnings.extend(_anvil_warnings(payload['instrument'].get('anvil_check')))
    area = payload['test_area']
    if area.get('support') == 'loose' \
            and (area.get('member_thickness_mm') or 1e9) \
            < THICKNESS_FIRM_SUPPORT_MM:
        warnings.append('a loose member under 100 mm thick: EN 12504-2 '
                        'asks for a firm support')
    if payload['impact_direction'] == 'inclined' \
            and payload.get('impact_angle_deg') is None:
        warnings.append('inclined impacts: state impact_angle_deg')
    return Prepared(payload=payload, summary=summary, position=position,
                    errors=problems, warnings=warnings,
                    excluded_from_fold=excluded)


# DERIVED RESULTS (decision 8.41) ---------------------------------------------
def check_derived(entry: Dict[str, Any], payload: Dict[str, Any],
                  where: str) -> List[Problem]:
    """The conditions a rebound-derived result names; ``payload`` is the
    prepared rebound payload."""
    kind = (entry.get('model') or {}).get('kind')
    model = entry['model']
    problems: List[Problem] = []
    if payload.get('median') is None:
        return [Problem(where, 'the rebound record has no valid median')]
    if payload.get('set_discarded'):
        problems.append(Problem(where, 'the set was discarded; nothing '
                                       'can be derived from it'))
    hammer = payload['instrument']['hammer_type']
    area = payload['test_area']
    if kind in ('din_en_13791_a20_na6', 'din_en_13791_a20_na7'):
        want, unit = (('N', '1') if kind.endswith('na6')
                      else ('Q_N', 'Q'))
        if hammer != want or payload['reading_unit'] != unit:
            problems.append(Problem(
                where, f'{kind} needs a hammer of type {want} reporting '
                       f'{"R" if unit == "1" else "Q"}; this record has '
                       f'{hammer}'))
        carbonation = area.get('carbonation_depth_mm')
        if area['surface_preparation'] != 'ground' and (
                carbonation is None or carbonation > MAX_CARBONATION_MM):
            problems.append(Problem(
                where, 'the German annex applies up to a carbonation depth '
                       'of 5 mm unless the surface was ground: state '
                       'carbonation_depth_mm or record a ground surface'))
        if not (model.get('note') or '').strip():
            problems.append(Problem(
                f'{where}.model.note',
                'name the table row the class was read from'))
        if not isinstance(entry.get('value'), str) or not entry['value']:
            problems.append(Problem(f'{where}.value',
                                    'the class as written in the table'))
    elif kind == 'en_13791_correlation':
        if not (model.get('reference') or '').strip():
            problems.append(Problem(
                f'{where}.model.reference',
                'name the correlation (the report is an attachment)'))
        value = entry.get('value')
        if not isinstance(value, (int, float)) or value <= 0:
            problems.append(Problem(f'{where}.value',
                                    'the prediction bound in MPa'))
    return problems
