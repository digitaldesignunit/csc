"""
Dimension search (decision 8.169, sorting 8.173): which pieces are about a
size, and which can hold a size.

Both modes compare the three sides of the asked box with the three sides of
the piece's current ``bbx``, each sorted from largest to smallest, so the
stored orientation does not matter (a standing column keeps its longest side
as z).

* ``about``: every sorted side lies within the tolerance of the asked side
  (a percentage of the asked side, or millimetres). The match value is the
  largest relative deviation, ``max |s - t| / t``, as a ratio (0.08 = 8 %).
* ``can_hold``: every sorted side of the piece is at least the asked side,
  which is exactly when the asked box fits inside the piece turned in
  90-degree steps. The match value is the waste, the piece's box volume minus
  the asked volume, in mm^3. It takes no tolerance.

A piece without a ``bbx`` (geometry not derived) never matches. The stages
read the joined ``current_snapshot`` and add ``fit`` to the row.
"""

import math
import re
from typing import Any, Dict, List, Literal, Optional, Tuple

FitMode = Literal['about', 'can_hold']

# the longest side an asked size or an absolute tolerance may have (100 m)
MAX_FIT_MM = 100_000.0
DEFAULT_TOLERANCE = '10%'
# one nanometre of slack for float rounding at the exact edge of a tolerance
_SLACK = 1e-9

_TOLERANCE = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*(%|mm)\s*$', re.IGNORECASE)
_SIZE_PART = re.compile(r'^\d+(?:\.\d+)?$')

_BBX = '$current_snapshot.bbx'


class FitError(ValueError):
    """A fit parameter that cannot be used; the message is for the caller."""


def parse_size(text: str) -> Tuple[float, float, float]:
    """``'1200,600,200'`` (mm, any order) -> the three sides, largest first."""
    parts = [p.strip() for p in text.split(',')]
    if len(parts) != 3 or not all(_SIZE_PART.match(p) for p in parts):
        raise FitError('fit_size needs three positive numbers in mm, '
                       'separated by commas, for example 1200,600,200')
    sides = [float(p) for p in parts]
    if any(not (0 < s <= MAX_FIT_MM) or not math.isfinite(s) for s in sides):
        raise FitError(f'every side of fit_size must be above 0 and at most '
                       f'{int(MAX_FIT_MM)} mm')
    return tuple(sorted(sides, reverse=True))  # type: ignore[return-value]


def parse_tolerance(text: str) -> Tuple[str, float]:
    """``'10%'`` or ``'50mm'`` -> ``('percent', 10.0)`` or ``('mm', 50.0)``."""
    found = _TOLERANCE.match(text)
    if not found:
        raise FitError('fit_tol is a number with % or mm, for example 10% '
                       'or 50mm')
    value, unit = float(found.group(1)), found.group(2).lower()
    if unit == '%':
        if value > 100:
            raise FitError('fit_tol in % is at most 100%')
        return 'percent', value
    if value > MAX_FIT_MM:
        raise FitError(f'fit_tol in mm is at most {int(MAX_FIT_MM)}mm')
    return 'mm', value


def fit_stages(mode: FitMode, sides: Tuple[float, float, float],
               tolerance: Optional[Tuple[str, float]]) -> List[Dict[str, Any]]:
    """The stages after the join of the current snapshot: keep the pieces
    that match and add ``fit`` (``{mode, deviation}`` or ``{mode,
    waste_mm3}``). ``sides`` are the asked sides, largest first."""
    s = [{'$arrayElemAt': ['$_fit_sides', i]} for i in range(3)]
    if mode == 'about':
        kind, value = tolerance or parse_tolerance(DEFAULT_TOLERANCE)
        diffs = [{'$abs': {'$subtract': [s[i], sides[i]]}} for i in range(3)]
        limits = [(sides[i] * value / 100 if kind == 'percent' else value)
                  + _SLACK for i in range(3)]
        conditions = [{'$lte': [diffs[i], limits[i]]} for i in range(3)]
        fit = {'mode': 'about', 'deviation': {'$max': [
            {'$divide': [diffs[i], sides[i]]} for i in range(3)]}}
    else:
        conditions = [{'$gte': [s[i], sides[i] - _SLACK]} for i in range(3)]
        fit = {'mode': 'can_hold', 'waste_mm3': {'$subtract': [
            {'$multiply': s}, sides[0] * sides[1] * sides[2]]}}
    return [
        # three numbers, else the piece has no size to compare
        {'$match': {'current_snapshot.bbx': {'$size': 3},
                    'current_snapshot.bbx.0': {'$type': 'number'},
                    'current_snapshot.bbx.1': {'$type': 'number'},
                    'current_snapshot.bbx.2': {'$type': 'number'}}},
        {'$addFields': {'_fit_sides': _sorted_sides()}},
        {'$match': {'$expr': {'$and': conditions}}},
        {'$addFields': {'fit': fit}},
        {'$unset': '_fit_sides'},
    ]


def _sorted_sides() -> List[Dict[str, Any]]:
    """The three sides of ``bbx``, largest first, without ``$sortArray`` (so no
    MongoDB version is needed): the largest, the middle and the smallest as
    ``$max`` / ``$min`` of the elements. The middle is the larger of the
    smaller of the first two and the smaller of their larger and the third, so
    no arithmetic touches the values and equal sides stay equal."""
    a, b, c = (_side(i) for i in range(3))
    return [
        {'$max': [a, b, c]},
        {'$max': [{'$min': [a, b]}, {'$min': [{'$max': [a, b]}, c]}]},
        {'$min': [a, b, c]},
    ]


def _side(index: int) -> Dict[str, Any]:
    return {'$arrayElemAt': [_BBX, index]}


def match_sort_field(mode: Optional[str]) -> str:
    """The sort path of ``match``: closest first, or least waste first."""
    return 'fit.waste_mm3' if mode == 'can_hold' else 'fit.deviation'


def volume_stages(order: int) -> Tuple[List[Dict[str, Any]], Dict[str, int],
                                        List[str]]:
    """``volume`` as a sort: the stages that compute it, the ``$sort`` spec
    and the helper fields to drop. A piece without three numbers in ``bbx``
    sorts last whichever way the order goes."""
    box = {'$cond': [{'$isArray': _BBX}, _BBX, []]}
    # a missing side makes the product null
    volume = {'$cond': [
        {'$eq': [{'$size': box}, 3]},
        {'$multiply': [{'$arrayElemAt': [box, i]} for i in range(3)]},
        None]}
    stages = [
        {'$addFields': {'_volume': volume}},
        {'$addFields': {'_volume_missing': {'$cond': [
            {'$eq': ['$_volume', None]}, 1, 0]}}},
    ]
    return stages, {'_volume_missing': 1, '_volume': order, '_id': 1}, [
        '_volume', '_volume_missing']
