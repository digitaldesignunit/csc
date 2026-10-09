#!/usr/bin/env python3.13
"""
The conservative bound of a folded property (spec section 7.8 and 10.3;
decision 8.116 c).

A folded property carries a range; the CERO export and the CPR projection
want one value. The rule, pure and the same for both:

* a scalar takes the bound named by the quantity's ``conservative`` column
  (``low`` or ``high``); a quantity without one gives a value only when the
  range is a single value;
* a categorical quantity gives its value only when the fold is unambiguous
  (one distinct value);
* an ordinal quantity takes the worst level: the highest of a severity, the
  lowest of a grade.

``None`` means "no single value": the exporter leaves the property out.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Any, Dict, Optional

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.vocab import Quantity


def conservative_value(quantity: Quantity,
                       prop: Dict[str, Any]) -> Optional[Any]:
    """The single value of ``prop`` (a folded property) for ``quantity``, or
    None when the range does not allow one."""
    rng = list(prop.get('range') or [])
    if not rng:
        return None
    if quantity.kind == 'categorical':
        return rng[0] if len(set(rng)) == 1 else None
    low, high = rng[0], rng[-1]
    if quantity.kind == 'ordinal':
        return low if quantity.ordinal_direction == 'grade' else high
    if low == high:
        return low
    if quantity.conservative == 'low':
        return low
    if quantity.conservative == 'high':
        return high
    return None
