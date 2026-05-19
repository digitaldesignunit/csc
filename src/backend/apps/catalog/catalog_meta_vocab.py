#!/usr/bin/env python3.9
"""
Additional catalog metadata values for dropdowns and filters.

``ADDITIONAL_*`` tuples list names that may not exist on any identity yet.
They are merged with distinct values from the identities collection (catalog
first, then additional, case-insensitive dedupe). Users can still pick
"Other (custom)" in the add wizard for values outside these lists.
"""

from typing import Iterable, List, Sequence

# Extra material names when not yet used on any identity.
# Do not repeat values that already exist in the catalog (those come from DB).
ADDITIONAL_MATERIALS: Sequence[str] = (
    'aluminum',
    'ceramic',
    'composite',
    'copper',
    'glass',
    'gypsum',
    'insulation',
    'plastic',
    'rubber',
    'soil',
    'steel',
    'stone',
    'timber',
    'wood',
    'zinc',
)

# Extra dataset names when not yet used on any identity.
ADDITIONAL_DATASETS: Sequence[str] = (
    'demo',
    'schoenes_neues_feld',
)


def merge_additional_with_catalog(
    additional: Sequence[str],
    catalog_values: Iterable[str],
) -> List[str]:
    """
    Distinct union: catalog values (sorted), then additional not in catalog.
    """
    seen: set[str] = set()
    merged: List[str] = []

    catalog: List[str] = []
    for raw in catalog_values:
        value = (raw or '').strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        catalog.append(value)
    catalog.sort(key=str.lower)
    merged.extend(catalog)

    extras: List[str] = []
    for raw in additional:
        value = (raw or '').strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        extras.append(value)
    extras.sort(key=str.lower)
    merged.extend(extras)
    return merged
