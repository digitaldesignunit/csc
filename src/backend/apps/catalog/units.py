#!/usr/bin/env python3.13
"""
Unit conversion to the canonical UCUM unit of a quantity (data model spec
section 2.6: "stored as-entered plus canonical; the server converts").

Pure functions. Only the units that occur in practice for the quantities of
``vocab.QUANTITIES`` are listed; anything else is refused with the list of
accepted units, so a typo never turns into a silently wrong number. All
factors are exact SI relations.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Dict, Optional, Tuple

# canonical unit -> {entered unit: factor to multiply by}
CONVERSIONS: Dict[str, Dict[str, float]] = {
    'MPa': {'MPa': 1.0, 'N/mm2': 1.0, 'N/mm^2': 1.0, 'kPa': 1e-3,
            'Pa': 1e-6, 'GPa': 1e3, 'N/cm2': 1e-2},
    'GPa': {'GPa': 1.0, 'MPa': 1e-3, 'N/mm2': 1e-3, 'kN/mm2': 1.0,
            'kPa': 1e-6},
    'kg/m3': {'kg/m3': 1.0, 'g/cm3': 1e3, 'kg/dm3': 1e3, 'g/dm3': 1.0,
              't/m3': 1e3},
    'mm': {'mm': 1.0, 'cm': 10.0, 'm': 1e3, 'um': 1e-3},
    'kg': {'kg': 1.0, 'g': 1e-3, 't': 1e3},
    '%': {'%': 1.0, '1': 100.0},
    '1': {'1': 1.0},
}


def accepted_units(canonical: str) -> Tuple[str, ...]:
    return tuple(CONVERSIONS.get(canonical, {canonical: 1.0}))


def factor(entered: Optional[str], canonical: str) -> float:
    """The factor taking a value in ``entered`` to ``canonical``; ``entered``
    None means it is already canonical. Raises ValueError for a unit the
    quantity does not accept."""
    if entered is None or entered == canonical:
        return 1.0
    table = CONVERSIONS.get(canonical, {})
    if entered not in table:
        raise ValueError(
            f'unit {entered!r} is not accepted for {canonical!r}; use one '
            f'of {list(accepted_units(canonical))}')
    return table[entered]


def convert(value: float, entered: Optional[str], canonical: str) -> float:
    """``value`` in the unit ``entered``, in the canonical unit (rounded to
    12 significant digits so 0.1 * 1000 is 100, not 100.00000000000001)."""
    return float(f'{value * factor(entered, canonical):.12g}')
