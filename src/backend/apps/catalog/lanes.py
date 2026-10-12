#!/usr/bin/env python3.13
"""
The swimlane history of a component (decision 8.140 a, c, g, h): the piece
in the middle, its parents above, its children below, each lane with the
events of its life in time order, and the links where a piece was cut from
or assembled out of others.

Pure functions over plain documents; the route (``api/history.py``) reads the
documents with projections, decides what the caller may see and calls these.
A lane the caller may not see is a stub (its id and ``visible: false``), and
the lanes beyond ``MAX_LANES`` are a count.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.lifecycle import chain_position
from apps.catalog.timeutil import parse_ts

MAX_LANES = 12
# the sort order of events that share a date: the start, a version, evidence,
# the end
_ORDER = {'origin': 0, 'version': 1, 'evidence': 2, 'evidence_group': 2,
          'exit': 8, 'withdrawal': 9}
# how much of a timestamp names the group of an evidence record
_DAY = {'year': 4, 'month': 7, 'day': 10}


def _sort_key(event: Dict[str, Any]) -> Tuple:
    at = event.get('at')
    # an undated event comes first (it starts its section, 8.140 d)
    moment = parse_ts(at).timestamp() if at else float('-inf')
    return (moment, _ORDER.get(event['kind'], 5), event.get('id') or '')


def _event(kind: str, at: Optional[str], **fields: Any) -> Dict[str, Any]:
    event: Dict[str, Any] = {'kind': kind, 'at': at}
    event.update({k: v for k, v in fields.items() if v is not None})
    return event


def _day_key(record: Dict[str, Any]) -> str:
    text = str(record.get('observed_at') or '')
    return text[:_DAY.get(record.get('observed_at_precision') or 'day', 10)]


def lane_events(identity: Dict[str, Any],
                snapshots: Sequence[Dict[str, Any]],
                evidence: Sequence[Dict[str, Any]], *,
                expand: str = 'groups') -> List[Dict[str, Any]]:
    """The events of one lane in time order. ``snapshots`` and ``evidence``
    are what the caller may see in full. Evidence is grouped per day and
    method unless ``expand`` is ``all``."""
    events: List[Dict[str, Any]] = []
    for k, cycle in enumerate(identity.get('past_cycles') or []):
        origin = cycle.get('origin') or {}
        if origin:
            events.append(_event('origin', origin.get('at'),
                                 precision=origin.get('at_precision'),
                                 detail=origin.get('kind'), cycle=k))
        exit_ = cycle.get('exit') or {}
        if exit_:
            events.append(_event('exit', exit_.get('at'),
                                 precision=exit_.get('at_precision'),
                                 detail=exit_.get('kind'), cycle=k))
    origin = identity.get('origin')
    if origin:
        events.append(_event('origin', origin.get('at'),
                             precision=origin.get('at_precision'),
                             detail=origin.get('kind'),
                             planned=True if origin.get('planned') else None))
    exit_ = identity.get('exit')
    if exit_:
        events.append(_event('exit', exit_.get('at'),
                             precision=exit_.get('at_precision'),
                             detail=exit_.get('kind')))
    withdrawn = identity.get('withdrawn')
    if withdrawn:
        events.append(_event('withdrawal', withdrawn.get('at')))

    by_id = {s['_id']: s for s in snapshots}
    for snap in snapshots:
        events.append(_event(
            'version', snap.get('effective_from'), id=snap['_id'],
            precision=snap.get('effective_from_precision'),
            version=chain_position(snap, by_id), status=snap.get('status'),
            name=snap.get('name'),
            # a correction shows as the version it corrects (8.123 b)
            corrected=True if snap.get('superseded_by') else None,
            corrects=snap.get('supersedes'),
            withdrawn=True if snap.get('status') == 'withdrawn' else None))

    shown = [r for r in evidence if r.get('status') != 'withdrawn']
    if expand == 'all':
        for record in shown:
            events.append(_event(
                'evidence', record.get('observed_at'), id=record['_id'],
                precision=record.get('observed_at_precision'),
                method=record.get('method'), status=record.get('status'),
                quantity=(record.get('summary') or {}).get('quantity'),
                corrected=True if record.get('superseded_by') else None))
    else:
        groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for record in shown:
            groups.setdefault((_day_key(record), record.get('method') or ''),
                              []).append(record)
        for (day, method), records in groups.items():
            records.sort(key=lambda r: (str(r.get('observed_at') or ''),
                                        r['_id']))
            first = records[0]
            events.append(_event(
                'evidence_group', first.get('observed_at'),
                id=records[0]['_id'], precision=first.get(
                    'observed_at_precision'), method=method or None,
                day=day or None, count=len(records),
                ids=[r['_id'] for r in records],
                statuses=sorted({r.get('status') for r in records
                                 if r.get('status')})))
    events.sort(key=_sort_key)
    return events


def first_version(snapshots: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The first version of a piece among the snapshots the caller sees: the
    lowest place in the version order (a correction keeps the place of what
    it corrects), earliest ``created`` among equals."""
    rows = list(snapshots)
    if not rows:
        return None
    by_id = {s['_id']: s for s in rows}
    return min(rows, key=lambda s: (chain_position(s, by_id),
                                    str(s.get('created') or ''), s['_id']))


def lane_header(identity: Dict[str, Any],
                snapshots: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """What names a lane: the number, the name of its current version (else
    its latest), the dataset and the state of the piece."""
    current = identity.get('current_snapshot_id')
    named = next((s for s in snapshots if s['_id'] == current), None)
    if named is None and snapshots:
        named = max(snapshots, key=lambda s: (s.get('version') or 0))
    return {
        'catalog_number': identity.get('catalog_number'),
        'name': (named or {}).get('name'),
        'dataset': identity.get('dataset'),
        'withdrawn': bool(identity.get('withdrawn')),
        'exited': bool(identity.get('exit')),
        'in_place': bool((identity.get('origin') or {}).get('planned')),
    }


def link_kind(child: Dict[str, Any]) -> str:
    """A piece with one parent was cut, with several it was assembled."""
    return 'assemble' if len(child.get('parent_identities') or []) > 1 \
        else 'cut'


def cap_lanes(order: Sequence[str], limit: int = MAX_LANES
              ) -> Tuple[List[str], int]:
    """The first ``limit`` lanes in their order and how many are left out."""
    kept = list(order[:limit])
    return kept, max(0, len(order) - len(kept))
