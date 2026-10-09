#!/usr/bin/env python3.13
"""
The change log: what changed on a record, and the record as it was
(data model spec section 3.8, I30; decision 8.36).

Pure functions. ``diff`` lists the top-level fields a write changed ---
derived fields and the status (which keeps its own ``status_history``,
8.30) are left out; ``as_of`` rolls a document back over the entries
written after a date.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import copy
import json
from datetime import datetime
from typing import Any, Dict, Iterable, List

# fields never logged: derived, bookkeeping, or logged elsewhere (8.30)
NOT_LOGGED: Dict[str, frozenset] = {
    # `reserved` is a booking in the catalogue, not a fact about the piece
    'identity': frozenset({
        'properties', 'properties_version', 'lastmodified', 'created',
        'etag', '_id', 'reserved',
    }),
    'snapshot': frozenset({
        'descriptors', 'properties', 'properties_version', 'frame', 'bbx',
        'derivation', 'mesh_ply_resolutions', 'photo_count', 'status',
        'status_changed_by_user_id', 'status_changed_at', 'status_history',
        'lastmodified', 'created', 'etag', '_id',
    }),
    'evidence': frozenset({
        'status', 'status_changed_by_user_id', 'status_changed_at',
        'status_history', 'lastmodified', 'created', 'etag', '_id',
    }),
}


def _same(a: Any, b: Any) -> bool:
    return json.dumps(a, sort_keys=True, default=str) == \
        json.dumps(b, sort_keys=True, default=str)


def diff(kind: str, before: Dict[str, Any], after: Dict[str, Any]
         ) -> List[Dict[str, Any]]:
    """The logged fields that differ, as ``{path, old, new}`` (top-level
    paths: a changed block is logged whole)."""
    skip = NOT_LOGGED[kind]
    changes = []
    for key in sorted((set(before) | set(after)) - skip):
        old, new = before.get(key), after.get(key)
        if not _same(old, new):
            changes.append({'path': key, 'old': copy.deepcopy(old),
                            'new': copy.deepcopy(new)})
    return changes


def _when(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


_KEPT = frozenset({'_id', 'created', 'status', 'status_history',
                   'status_changed_at', 'status_changed_by_user_id'})


def as_of(kind: str, doc: Dict[str, Any], entries: Iterable[Dict[str, Any]],
          at: str) -> Dict[str, Any]:
    """
    ``doc`` as it was at ``at``: every entry written after ``at`` is undone,
    newest first; a snapshot's or evidence record's status is read from its
    ``status_history``. Derived fields were never logged and are dropped
    rather than shown wrongly. The caller checks ``created <= at``.
    """
    when = _when(at)
    later = sorted((e for e in entries if _when(e['at']) > when),
                   key=lambda e: _when(e['at']), reverse=True)
    out = copy.deepcopy(doc)
    for entry in later:
        for change in entry['changes']:
            if change.get('old') is None:
                out.pop(change['path'], None)
            else:
                out[change['path']] = copy.deepcopy(change['old'])
    for key in NOT_LOGGED[kind] - _KEPT:
        out.pop(key, None)
    full = out.get('status_history') or []
    if kind in ('snapshot', 'evidence') and full:
        # without a history (migrated records) the status stays as it is
        history = [h for h in full if _when(h['at']) <= when]
        out['status_history'] = history
        if history:
            out['status'] = history[-1]['to']
            out['status_changed_at'] = history[-1]['at']
            out['status_changed_by_user_id'] = history[-1]['by_user_id']
        else:
            out['status'] = full[0]['from']
    out['as_of'] = at
    return out
