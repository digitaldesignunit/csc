#!/usr/bin/env python3.13
"""
Status lifecycle and field freeze (data model spec I15, section 3.2.2,
3.3.4, 3.1.5).

Pure functions. ``transition_action`` says which permission a status change
needs (checked with ``permissions.can``); ``patch_problems`` sorts the fields
of a PATCH into the three refusals of decision 8.3:

* ``derived``   --- server-only field, never accepted from a client (422)
* ``frozen``    --- claim about a published state; supersede it (409)
* ``forbidden`` --- editable, but not by this caller (403)
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Dict, FrozenSet, Iterable, List, Optional, Tuple

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.vocab import DELETABLE_STATUSES


# STATUS TRANSITIONS (I15) ----------------------------------------------------
# (from, to) -> the permission action it needs; identical for snapshots and
# evidence. Leaving `published` by supersession is not a status change.
TRANSITIONS: Dict[Tuple[str, str], str] = {
    ('draft', 'pending'): 'submit',
    ('pending', 'published'): 'publish',
    ('pending', 'rejected'): 'reject',
    ('rejected', 'draft'): 'resubmit',
    ('published', 'withdrawn'): 'withdraw',
    ('withdrawn', 'published'): 'reinstate',
}
# transitions that need a reason in the request (I15, section 3.1.4)
REASON_REQUIRED: FrozenSet[Tuple[str, str]] = frozenset({
    ('pending', 'rejected'),
    ('published', 'withdrawn'),
})


def transition_action(current: str, target: str) -> Optional[str]:
    """The permission action a status change needs; None if not allowed."""
    return TRANSITIONS.get((current, target))


def transition_allowed(current: str, target: str) -> bool:
    return (current, target) in TRANSITIONS


def hard_delete_allowed(status: str) -> bool:
    """Anything that was published is withdrawn, never deleted (6.4)."""
    return status in DELETABLE_STATUSES


# FIELD CLASSES ---------------------------------------------------------------
# Snapshot (section 3.2.2, decision 8.3). Top-level field names; `capture` is
# frozen except its `notes`, which count as mutable metadata.
SNAPSHOT_FROZEN: FrozenSet[str] = frozenset({
    'geometry', 'capture', 'fragment', 'quantity',
})
SNAPSHOT_MUTABLE_METADATA: FrozenSet[str] = frozenset({
    'name', 'notes', 'location', 'color', 'capture.notes',
})
SNAPSHOT_VALID_TIME: FrozenSet[str] = frozenset({
    'effective_from', 'effective_from_precision',
})
SNAPSHOT_OVERRIDES: FrozenSet[str] = frozenset({
    'shape_class', 'complexity',
})
SNAPSHOT_DERIVED: FrozenSet[str] = frozenset({
    'descriptors', 'properties', 'properties_version', 'frame', 'bbx',
    'mesh_ply_resolutions', 'photo_count', 'shape_class_source',
    'complexity_source', 'status', 'status_changed_by_user_id',
    'status_changed_at', 'supersedes', 'superseded_by', 'version',
    'identity_id', 'added_by_user_id', 'added_by_username', 'etag',
    'created', 'lastmodified', '_id', 'id',
})

# Evidence (section 3.3.4): frozen on publish; notes and position.description
# stay editable; verification has its own route; attachments are add-only.
EVIDENCE_FROZEN: FrozenSet[str] = frozenset({
    'payload', 'summary', 'derived', 'observed_at', 'observed_at_precision',
    'sampled_at', 'sampled_at_precision', 'performed_by', 'standard',
    'method', 'method_version', 'position.snapshot_id', 'position.point',
    'position.kind',
})
EVIDENCE_MUTABLE: FrozenSet[str] = frozenset({'notes', 'position.description'})
EVIDENCE_DERIVED: FrozenSet[str] = frozenset({
    'source_tier', 'destructive', 'status', 'status_changed_by_user_id',
    'status_changed_at', 'supersedes', 'superseded_by', 'identity_id',
    'recorded_by_user_id', 'recorded_by_username', 'attachments',
    'verification', 'etag', 'created', 'lastmodified', '_id', 'id',
})

# Identity (section 3.1): metadata PATCH (moderator, or the creator while
# unpublished, 8.9); everything else is server-maintained or has its own route.
IDENTITY_METADATA: FrozenSet[str] = frozenset({
    'original_function', 'material', 'material_class', 'trade_name',
    'manufactured_at', 'manufactured_precision', 'origin', 'is_public',
    # inherited_fields: adding a field back (re-inherit) only, I17
    'attributes', 'inherited_fields',
})
IDENTITY_OWN_ROUTE: FrozenSet[str] = frozenset({
    'dataset',                # move: moderator of both datasets
    'exit', 'withdrawn', 'reserved', 'current_snapshot_id',
})
IDENTITY_DERIVED: FrozenSet[str] = frozenset({
    'catalog_number', 'properties', 'properties_version', 'inherited_from',
    'past_cycles', 'parent_identities', 'material_class_source',
    'created_by_user_id', 'created', 'lastmodified', '_id', 'id',
})


def _expand(fields: Iterable[str],
            nested: Dict[str, Iterable[str]]) -> List[str]:
    """``capture`` -> ``capture.notes`` etc. where a patch names subfields."""
    out: List[str] = []
    for name in fields:
        if name in nested:
            out.extend(f'{name}.{sub}' for sub in nested[name])
        else:
            out.append(name)
    return out


def patch_problems(
    kind: str,
    fields: Dict[str, Iterable[str]],
    *,
    status: Optional[str] = None,
    identity_published: bool = True,
    is_author: bool = False,
    is_moderator: bool = False,
) -> Dict[str, List[str]]:
    """
    Sort the fields of a PATCH into ``derived`` / ``frozen`` / ``forbidden``.

    ``fields`` maps each top-level key to its changed subkeys (empty for a
    scalar), e.g. ``{'notes': [], 'capture': ['notes']}``. An empty result
    means the PATCH may proceed. Unknown keys count as derived (not writable).
    """
    problems: Dict[str, List[str]] = {
        'derived': [], 'frozen': [], 'forbidden': []}
    names = _expand([k for k, v in fields.items()],
                    {k: v for k, v in fields.items() if v})

    if kind == 'snapshot':
        published = status in ('published', 'withdrawn')
        for name in names:
            top = name.split('.', 1)[0]
            if name in SNAPSHOT_MUTABLE_METADATA:
                allowed = is_moderator or (not published and is_author)
            elif top in SNAPSHOT_VALID_TIME or top in SNAPSHOT_OVERRIDES:
                allowed = is_moderator or (not published and is_author)
            elif top in SNAPSHOT_FROZEN:
                if published:
                    problems['frozen'].append(name)
                    continue
                allowed = is_moderator or is_author
            else:
                problems['derived'].append(name)
                continue
            if not allowed:
                problems['forbidden'].append(name)

    elif kind == 'evidence':
        published = status in ('published', 'withdrawn')
        for name in names:
            top = name.split('.', 1)[0]
            if name in EVIDENCE_MUTABLE or top == 'notes':
                allowed = is_moderator or (not published and is_author)
            elif (name in EVIDENCE_FROZEN or top in EVIDENCE_FROZEN
                  or top == 'position'):
                if published:
                    problems['frozen'].append(name)
                    continue
                allowed = is_author or is_moderator
            else:
                problems['derived'].append(name)
                continue
            if not allowed:
                problems['forbidden'].append(name)

    elif kind == 'identity':
        for name in names:
            top = name.split('.', 1)[0]
            if top in IDENTITY_METADATA:
                allowed = is_moderator or (
                    not identity_published and is_author)
            elif top in IDENTITY_OWN_ROUTE:
                problems['forbidden'].append(name)
                continue
            else:
                problems['derived'].append(name)
                continue
            if not allowed:
                problems['forbidden'].append(name)
    else:
        raise ValueError(f'unknown document kind: {kind!r}')

    return {key: value for key, value in problems.items() if value}
