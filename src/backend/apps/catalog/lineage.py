#!/usr/bin/env python3.13
"""
Lineage: what a child inherits from its parents, and how a cut ends them
(data model spec section 3.1.2, 3.1.3, I17, I18; decisions 6.2, 8.8, 8.31
-- 8.34).

Pure functions over plain documents (dicts as stored); the routes load the
documents, call these and write the results.

* ``inherit_on_create``  --- a new child: every unit it does not state
  itself is copied from its parents (a merge only where they agree)
* ``propagate``          --- a parent changed: what each inheriting child
  takes over, or lets go of when merged parents no longer agree
* ``reinherit``          --- a child takes a unit back from its parents
* ``cut_refusal``        --- whether a piece may be cut at all (8.34)
* ``derived_exit``       --- the split / merged exit the server keeps on a
  parent while it has published children (8.8, 8.34)
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import copy
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pydantic import ValidationError

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import CircularityClass, Origin
from apps.catalog.vocab import (
    CUTTABLE_EXIT_KINDS,
    INHERIT_UNITS,
    ORIGIN_IDENTIFYING_KEYS,
    SERVER_SET_EXIT_KINDS,
)

# units a child must end up with: a merge whose parents disagree on them
# cannot leave them empty, so the client states them (422 otherwise)
REQUIRED_UNITS: Tuple[str, ...] = ('material', 'original_function')

# what a unit becomes when merged parents disagree and the child states
# nothing (section 3.1.2: "stays unset ... and must be assigned")
UNSET_VALUES: Dict[str, Dict[str, Any]] = {
    'origin': {'origin': {'kind': 'unknown', 'at': None,
                          'at_precision': 'unknown'}},
    'manufactured_at': {'manufactured_at': None,
                        'manufactured_precision': 'unknown'},
    'trade_name': {'trade_name': None},
    'manufacturer': {'manufacturer': None},
    'material_separability': {'material_separability': None},
}


# HELPERS ---------------------------------------------------------------------
def _canonical(value: Any) -> str:
    """Order-independent comparison of nested values."""
    return json.dumps(value, sort_keys=True, default=str)


_BLOCKS = {'origin': Origin, 'material_separability': CircularityClass}


def _normalized(field: str, value: Any) -> Any:
    """A block as the model stores it (defaults filled in), so a document
    written before a field existed compares equal to one written after."""
    model = _BLOCKS.get(field)
    if model is None or not isinstance(value, dict):
        return copy.deepcopy(value)
    try:
        return model.model_validate(value).model_dump(by_alias=True,
                                                      mode='json')
    except ValidationError:
        return copy.deepcopy(value)


def unit_values(doc: Dict[str, Any], unit: str) -> Dict[str, Any]:
    """The fields of one inheritance unit, as the model stores them."""
    values = {f: _normalized(f, doc.get(f)) for f in INHERIT_UNITS[unit]}
    if unit == 'manufactured_at' and values['manufactured_precision'] is None:
        values['manufactured_precision'] = 'unknown'
    if unit == 'material' and values['material_class_source'] is None \
            and values['material'] is not None:
        values['material_class_source'] = 'derived'
    return values


def _label(doc: Dict[str, Any]) -> str:
    number = doc.get('catalog_number')
    return f'CSC-{int(number):06d}' if number else str(doc.get('_id'))


def _merge_origin(parents: Sequence[Dict[str, Any]]
                  ) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Merged parents agree on ``origin`` when its identifying keys match
    (8.33); the child then gets the first parent's origin with every
    parent's actors (deduplicated) and the notes joined, each prefixed with
    its parent's catalog number.
    """
    origins = [_normalized('origin', p.get('origin')) for p in parents]
    if all(o is None for o in origins):
        return True, None
    if any(o is None for o in origins):
        return False, None
    keys = [_canonical({k: o.get(k) for k in ORIGIN_IDENTIFYING_KEYS})
            for o in origins]
    if any(k != keys[0] for k in keys):
        return False, None
    merged = copy.deepcopy(origins[0])
    actors: List[Dict[str, Any]] = []
    seen = set()
    for origin in origins:
        for actor in origin.get('performed_by') or []:
            key = _canonical(actor)
            if key not in seen:
                seen.add(key)
                actors.append(copy.deepcopy(actor))
    merged['performed_by'] = actors
    notes = [f'{_label(p)}: {o["notes"]}' for p, o in zip(parents, origins)
             if o.get('notes')]
    merged['notes'] = '\n'.join(notes) if notes else None
    return True, merged


def expected_unit(unit: str, parents: Sequence[Dict[str, Any]]
                  ) -> Tuple[bool, Dict[str, Any]]:
    """
    What a child inheriting ``unit`` holds: ``(agree, values)``. One parent
    always agrees; merged parents agree when their values are equal ---
    for ``origin`` when its identifying keys are (8.33).
    """
    if not parents:
        raise ValueError('a child has at least one parent')
    if len(parents) == 1:
        return True, unit_values(parents[0], unit)
    if unit == 'origin':
        agree, merged = _merge_origin(parents)
        return agree, ({'origin': merged} if agree else {})
    values = [unit_values(p, unit) for p in parents]
    first = _canonical(values[0])
    if any(_canonical(v) != first for v in values[1:]):
        return False, {}
    return True, values[0]


# CREATE ----------------------------------------------------------------------
@dataclass
class Inheritance:
    """What a new child stores: the unit values, which units it inherits,
    and which required units it still lacks (merged parents disagree and
    the client stated none)."""
    values: Dict[str, Any]
    inherited_fields: List[str]
    inherited_from: Optional[str]
    missing: List[str]


def states_unit(payload: Dict[str, Any], unit: str) -> bool:
    """A unit is the child's own as soon as the payload names a field of
    it (section 3.1.2)."""
    return any(f in payload for f in INHERIT_UNITS[unit])


def inherit_on_create(payload: Dict[str, Any],
                      parents: Sequence[Dict[str, Any]]) -> Inheritance:
    """Copy-on-create (section 3.1.2): each unit the payload does not state
    is taken from the parents where they agree."""
    values: Dict[str, Any] = {}
    inherited: List[str] = []
    missing: List[str] = []
    for unit in INHERIT_UNITS:
        if states_unit(payload, unit):
            continue
        agree, unit_vals = expected_unit(unit, parents)
        if agree:
            values.update(unit_vals)
            inherited.append(unit)
        elif unit in REQUIRED_UNITS:
            missing.append(unit)
        else:
            values.update(copy.deepcopy(UNSET_VALUES[unit]))
    return Inheritance(
        values=values, inherited_fields=inherited,
        inherited_from=parents[0]['_id'] if inherited else None,
        missing=missing)


# PROPAGATE / RE-INHERIT ------------------------------------------------------
@dataclass
class ChildUpdate:
    """One child's response to a parent change: fields to set, units it
    lets go of (merged parents no longer agree), and its new list."""
    set_values: Dict[str, Any]
    detached: List[str]
    inherited_fields: List[str]

    @property
    def changed(self) -> bool:
        return bool(self.set_values or self.detached)


def propagate(child: Dict[str, Any], parents: Sequence[Dict[str, Any]],
              units: Iterable[str]) -> ChildUpdate:
    """
    A parent changed ``units``. The child takes over every one it still
    inherits (8.31); when merged parents now disagree on one, the child
    keeps its value and stops inheriting it (8.33). ``parents`` are the
    child's parents as they are *after* the change.
    """
    listed = list(child.get('inherited_fields') or [])
    set_values: Dict[str, Any] = {}
    detached: List[str] = []
    for unit in units:
        if unit not in listed:
            continue
        agree, values = expected_unit(unit, parents)
        if not agree:
            detached.append(unit)
            continue
        for field, value in values.items():
            if _canonical(child.get(field)) != _canonical(value):
                set_values[field] = value
    kept = [u for u in listed if u not in detached]
    return ChildUpdate(set_values=set_values, detached=detached,
                       inherited_fields=kept)


def reinherit(child: Dict[str, Any], parents: Sequence[Dict[str, Any]],
              units: Iterable[str]) -> ChildUpdate:
    """The child takes ``units`` back (PATCH adding them to
    ``inherited_fields``). Raises ``ValueError`` when merged parents
    disagree on one: there is nothing to take back."""
    listed = list(child.get('inherited_fields') or [])
    set_values: Dict[str, Any] = {}
    for unit in units:
        if unit not in INHERIT_UNITS:
            raise ValueError(f'not inheritable: {unit} (I17)')
        agree, values = expected_unit(unit, parents)
        if not agree:
            raise ValueError(f'the parents disagree on {unit}; it cannot be '
                             f'inherited (8.33)')
        set_values.update(values)
        if unit not in listed:
            listed.append(unit)
    return ChildUpdate(set_values=set_values, detached=[],
                       inherited_fields=listed)


def detach_on_patch(child: Dict[str, Any], patched_fields: Iterable[str]
                    ) -> List[str]:
    """A child's own PATCH of a field it inherits makes the whole unit its
    own (section 3.1.2): the units to drop from ``inherited_fields``."""
    fields = set(patched_fields)
    return [u for u in child.get('inherited_fields') or []
            if fields & set(INHERIT_UNITS[u])]


def changed_units(before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
    """The units whose values differ between two versions of a document."""
    return [u for u in INHERIT_UNITS
            if _canonical(unit_values(before, u))
            != _canonical(unit_values(after, u))]


# CUTS (decision 8.34) --------------------------------------------------------
def cut_refusal(parent: Dict[str, Any], *, ever_published: bool
                ) -> Optional[str]:
    """Why a piece cannot be cut, or None. A cut needs a published,
    non-withdrawn parent that is in circulation or already ended by a
    cut; checked at child create and again at the child's first publish."""
    label = _label(parent)
    if parent.get('withdrawn'):
        duplicate = (parent['withdrawn'] or {}).get('duplicate_of')
        tail = f'; it duplicates {duplicate}' if duplicate else ''
        return f'{label} is withdrawn{tail}.'
    if not ever_published:
        return f'{label} is not published yet; publish it first.'
    exit_ = parent.get('exit')
    if exit_ and exit_.get('kind') not in CUTTABLE_EXIT_KINDS:
        if exit_.get('kind') in ('installed', 'returned', 'lost'):
            return (f'{label} is out of circulation ({exit_["kind"]}); '
                    f'it re-enters first.')
        return f'{label} no longer exists as this piece ({exit_["kind"]}).'
    return None


# DERIVED EXIT (decisions 8.8, 8.34) ------------------------------------------
@dataclass(frozen=True)
class ChildFacts:
    """What the exit rule needs to know about one child of a parent."""
    child_id: str
    parent_count: int
    withdrawn: bool
    # effective_from of the child's earliest ever-published snapshot
    first_published_at: Optional[str]
    first_published_precision: str = 'exact'


def _when(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


_KEEP = object()


def derived_exit(parent: Dict[str, Any], children: Sequence[ChildFacts]):
    """
    The exit a parent should hold given its children, or ``KEEP`` when the
    rule does not touch it (no children and no server-set exit, or an
    authored exit other than a split / merge, which is never overwritten).

    A child counts once it has ever been published and is not withdrawn.
    The kind is ``merged`` when every such child has more than one parent,
    else ``split``; ``at`` is the earliest child ``effective_from``, or a
    hand-set split's own date if that is earlier (8.34).
    """
    exit_ = parent.get('exit') or None
    live = [c for c in children
            if not c.withdrawn and c.first_published_at is not None]
    is_cut = exit_ is not None and exit_.get('kind') in SERVER_SET_EXIT_KINDS
    server_set = is_cut and exit_.get('recorded_by_user_id') is None
    hand_set = is_cut and not server_set

    if exit_ is not None and not is_cut:
        return _KEEP                        # installed, recycled, ...
    if server_set:
        manual_at = exit_.get('manual_at')
        manual_by = exit_.get('manual_by_user_id')
        manual_precision = exit_.get('at_precision') if manual_at else None
    elif hand_set:
        manual_at = exit_.get('at')
        manual_by = exit_.get('recorded_by_user_id')
        manual_precision = exit_.get('at_precision')
    else:
        manual_at = manual_by = manual_precision = None

    if not live:
        if not server_set:
            return _KEEP
        if manual_at:                       # back to the hand-set split
            return {'kind': exit_['kind'] if exit_['kind'] != 'merged'
                    else 'split', 'at': manual_at,
                    'at_precision': manual_precision or 'exact',
                    'construction_work': None,
                    'notes': exit_.get('notes'),
                    'recorded_by_user_id': manual_by,
                    'manual_at': None, 'manual_by_user_id': None}
        return None                         # the cut is undone

    earliest = min(live, key=lambda c: _when(c.first_published_at))
    at, precision = earliest.first_published_at, \
        earliest.first_published_precision
    if manual_at and _when(manual_at) < _when(at):
        at, precision = manual_at, manual_precision or 'exact'
    kind = 'merged' if all(c.parent_count > 1 for c in live) else 'split'
    return {'kind': kind, 'at': at, 'at_precision': precision,
            'construction_work': None,
            'notes': exit_.get('notes') if exit_ else None,
            'recorded_by_user_id': None,
            'manual_at': manual_at, 'manual_by_user_id': manual_by}


KEEP = _KEEP
