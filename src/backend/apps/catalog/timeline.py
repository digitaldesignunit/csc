#!/usr/bin/env python3.13
"""
The snapshot timeline (data model spec section 4.1; decisions 8.10, 8.19)
and the merged timeline of one component (section 7.1).

Pure functions over plain documents. ``resolve_snapshot_at`` says which
snapshot a date belongs to; the context is never persisted on the evidence
document. ``build_timeline`` merges everything that happened to a component
into one list for the timeline route.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.timeutil import PRECISION_SPAN, parse_ts

# resolutions of a context (spec 4.1)
EXACT = 'exact'
APPROXIMATE = 'approximate'
BEFORE_FIRST = 'before_first'
AFTER_EXIT = 'after_exit'
CONTEXT_RESOLUTIONS = (EXACT, APPROXIMATE, BEFORE_FIRST, AFTER_EXIT)


@dataclass(frozen=True)
class Context:
    """The state of the piece a date belongs to. ``snapshot_id`` is None
    for ``before_first`` and ``after_exit``: no snapshot records that
    state (8.10)."""
    snapshot_id: Optional[str]
    resolution: str

    def as_dict(self) -> Dict[str, Any]:
        return {'snapshot_id': self.snapshot_id,
                'resolution': self.resolution}


def live_snapshots(snapshots: Sequence[Dict[str, Any]]) -> List[dict]:
    """Published and not corrected: what resolution and the fold see."""
    return [s for s in snapshots
            if s.get('status') == 'published' and not s.get('superseded_by')]


def _cycle_gaps(identity: Dict[str, Any]):
    """(exit.at, next origin.at) of every archived cycle (8.19): the time
    the piece spent elsewhere before it re-entered. A gap whose re-entry
    date is unknown is left out: nothing bounds it."""
    cycles = identity.get('past_cycles') or []
    current = identity.get('origin')
    for k, cycle in enumerate(cycles):
        nxt = cycles[k + 1].get('origin') if k + 1 < len(cycles) else current
        left = (cycle.get('exit') or {}).get('at')
        right = (nxt or {}).get('at')
        if left and right:
            yield parse_ts(left), parse_ts(right)


def resolve_snapshot_at(identity: Dict[str, Any],
                        snapshots: Sequence[Dict[str, Any]], at: str, *,
                        at_precision: str = 'exact') -> Context:
    """
    The snapshot a date belongs to: the latest live snapshot whose
    ``effective_from`` is not after it. ``before_first`` when none is;
    ``after_exit`` when the date is after the identity's exit, or inside the
    gap between an archived cycle's exit and the next cycle's origin (8.19)
    --- evidence of those times feeds no snapshot.

    ``approximate`` when the date or the snapshot's start is too coarse to
    say which side of the change it fell on: the date lies within the
    precision span of the snapshot's ``effective_from``, or the date's own
    span reaches the next snapshot's start.
    """
    when = parse_ts(at)
    exit_ = identity.get('exit')
    if exit_ and exit_.get('at') and when > parse_ts(exit_['at']):
        return Context(None, AFTER_EXIT)
    for left, right in _cycle_gaps(identity):
        if left < when < right:
            return Context(None, AFTER_EXIT)
    live = live_snapshots(snapshots)
    started = [s for s in live if parse_ts(s['effective_from']) <= when]
    if not started:
        return Context(None, BEFORE_FIRST)
    chosen = max(started, key=lambda s: (parse_ts(s['effective_from']),
                                         s.get('version', 0)))
    span = PRECISION_SPAN.get(chosen.get('effective_from_precision')
                              or 'exact')
    approximate = span is None or \
        when < parse_ts(chosen['effective_from']) + span
    later = [parse_ts(s['effective_from']) for s in live
             if parse_ts(s['effective_from']) > when]
    if later and not approximate:
        own = PRECISION_SPAN.get(at_precision)
        approximate = own is None or when + own > min(later)
    return Context(chosen['_id'], APPROXIMATE if approximate else EXACT)


def context_time(record: Dict[str, Any], context_field: str):
    """``(at, precision)`` a record resolves at: ``sampled_at`` for a core,
    ``observed_at`` for everything else (spec 4.1); a core without
    ``sampled_at`` falls back to ``observed_at``."""
    if context_field == 'sampled_at' and record.get('sampled_at'):
        return (record['sampled_at'],
                record.get('sampled_at_precision') or 'exact')
    return (record['observed_at'],
            record.get('observed_at_precision') or 'exact')


# MERGED TIMELINE (section 7.1) -----------------------------------------------
SECTION_BEFORE = 'before_cataloguing'
SECTION_HISTORY = 'history'
SECTION_AFTER = 'after_leaving_circulation'


def _event(kind: str, at: Optional[str], **fields: Any) -> Dict[str, Any]:
    return {'kind': kind, 'at': at, **fields}


def _sort_key(event: Dict[str, Any]):
    at = event.get('at')
    moment = parse_ts(at) if at else datetime.max.replace(
        tzinfo=timezone.utc)
    return (moment, event.get('order', 5))


def build_timeline(
    identity: Dict[str, Any],
    snapshots: Sequence[Dict[str, Any]],
    evidence: Sequence[Dict[str, Any]],
    contexts: Dict[str, Context],
    changes: Sequence[Dict[str, Any]] = (),
    *,
    members: bool = True,
) -> List[Dict[str, Any]]:
    """
    One chronological list of what happened to a component: archived
    cycles, the origin, every snapshot (corrected ones marked), every
    evidence record (with where it falls: before cataloguing, in the
    history, after the piece left circulation), changes of the metadata and
    the exit.

    ``snapshots`` and ``evidence`` are what the caller may see (withdrawn
    ones from outside the dataset arrive as bare rows, ``status:
    withdrawn``); ``contexts`` maps an evidence id to its resolved context;
    ``changes`` are change-log entries of the identity itself --- outside
    the dataset only their date is shown (8.36).
    """
    events: List[Dict[str, Any]] = []
    for k, cycle in enumerate(identity.get('past_cycles') or []):
        origin = cycle.get('origin')
        if origin:
            events.append(_event(
                'origin', origin.get('at'), order=0,
                precision=origin.get('at_precision'), cycle=k,
                detail=origin.get('kind'), section=SECTION_HISTORY))
        exit_ = cycle.get('exit') or {}
        events.append(_event(
            'exit', exit_.get('at'), order=9,
            precision=exit_.get('at_precision'), cycle=k,
            detail=exit_.get('kind'), section=SECTION_HISTORY))
    origin = identity.get('origin')
    if origin:
        events.append(_event(
            'origin', origin.get('at'), order=0,
            precision=origin.get('at_precision'), cycle=None,
            detail=origin.get('kind'), section=SECTION_HISTORY))
    for snap in snapshots:
        withdrawn = snap.get('status') == 'withdrawn'
        events.append(_event(
            'snapshot', snap.get('effective_from'), order=1,
            precision=snap.get('effective_from_precision'),
            record_id=snap['_id'], version=snap.get('version'),
            status=snap.get('status'), name=snap.get('name'),
            corrected=bool(snap.get('superseded_by')),
            corrects=snap.get('supersedes'), withdrawn=withdrawn,
            section=SECTION_HISTORY))
    for record in evidence:
        context = contexts.get(record['_id'])
        resolution = context.resolution if context else None
        section = SECTION_HISTORY
        if resolution == BEFORE_FIRST:
            section = SECTION_BEFORE
        elif resolution == AFTER_EXIT:
            section = SECTION_AFTER
        summary = record.get('summary') or {}
        events.append(_event(
            'evidence', record.get('observed_at'), order=2,
            precision=record.get('observed_at_precision'),
            record_id=record['_id'], method=record.get('method'),
            status=record.get('status'),
            quantity=summary.get('quantity'), value=summary.get('value'),
            range=summary.get('range'), unit=summary.get('unit'),
            corrected=bool(record.get('superseded_by')),
            corrects=record.get('supersedes'),
            verification=(record.get('verification') or {}).get('state'),
            snapshot_id=context.snapshot_id if context else None,
            resolution=resolution, section=section))
    if exit_ := identity.get('exit'):
        events.append(_event(
            'exit', exit_.get('at'), order=9,
            precision=exit_.get('at_precision'), cycle=None,
            detail=exit_.get('kind'), section=SECTION_HISTORY))
    for change in changes:
        entry = _event('metadata_changed', change.get('at'), order=8,
                       section=SECTION_HISTORY)
        if members:
            entry['paths'] = [c['path'] for c in change.get('changes') or []]
            entry['cause'] = change.get('cause')
        events.append(entry)
    events.sort(key=_sort_key)
    return events
