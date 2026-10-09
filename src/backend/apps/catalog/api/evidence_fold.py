#!/usr/bin/env python3.13
"""
The property fold at the database (data model spec section 4.4; plan P6):
recompute ``identity.properties`` and the ``properties`` of every snapshot
of one component, and pass an identity change on to the pieces cut from it.

Called after anything that moves the fold: an evidence record published,
withdrawn, reinstated, superseded or verified; a snapshot published,
withdrawn, reinstated, superseded or given another ``effective_from``; an
exit, a re-entry or an origin change of the identity (they move the
resolved contexts, 8.10, 8.19); a new child (inheritance). A recompute that
changes nothing writes nothing and propagates nothing.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Any, Dict, List, Optional, Set

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import Request

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.etag import compute_snapshot_etag
from apps.catalog.properties import (
    PROPERTIES_VERSION,
    contexts_for,
    fold,
    keep_derived_at,
    quantities_of_scope,
    same_properties,
    snapshot_inputs,
    window,
)
from apps.catalog.timeline import live_snapshots
from .catalog_common import now_iso

RETRIES = 4


async def published_evidence(request: Request, identity_id: str
                             ) -> List[Dict[str, Any]]:
    """The records that can enter a fold: published, not corrected."""
    return await request.app.mongodb_component_evidence.find(
        {'identity_id': identity_id, 'status': 'published',
         'superseded_by': None}).to_list(length=None)


async def _write_snapshot_properties(request: Request, snapshot_id: str,
                                     new: Dict[str, Any]) -> bool:
    """Set a snapshot's ``properties`` (and its etag), retrying when a
    runner or a PATCH changed the document meanwhile."""
    coll = request.app.mongodb_component_snapshots
    for _ in range(RETRIES):
        doc = await coll.find_one({'_id': snapshot_id})
        if doc is None:
            return False
        old = doc.get('properties') or {}
        if same_properties(old, new):
            return False
        value = keep_derived_at(old, new)
        updated = {**doc, 'properties': value,
                   'properties_version': PROPERTIES_VERSION}
        result = await coll.update_one(
            {'_id': snapshot_id, 'etag': doc.get('etag')},
            {'$set': {'properties': value,
                      'properties_version': PROPERTIES_VERSION,
                      'etag': compute_snapshot_etag(updated),
                      'lastmodified': now_iso()}})
        if result.matched_count:
            return True
    raise RuntimeError(f'snapshot {snapshot_id}: properties not written '
                       f'(changed concurrently)')


async def _parents(request: Request, identity: Dict[str, Any]
                   ) -> List[Dict[str, Any]]:
    ids = identity.get('parent_identities') or []
    if not ids:
        return []
    docs = await request.app.mongodb_component_identities.find(
        {'_id': {'$in': ids}}, {'properties': 1}).to_list(length=None)
    by_id = {d['_id']: d for d in docs}
    return [by_id[i] for i in ids if i in by_id]


async def recompute_properties(request: Request, identity_id: str, *,
                               _seen: Optional[Set[str]] = None) -> bool:
    """Recompute the fold of one component; returns whether its identity
    properties changed (then the pieces cut from it are recomputed too)."""
    seen = _seen if _seen is not None else set()
    if identity_id in seen:
        return False
    seen.add(identity_id)
    identities = request.app.mongodb_component_identities
    identity = await identities.find_one({'_id': identity_id})
    if identity is None:
        return False
    snapshots = await request.app.mongodb_component_snapshots.find(
        {'identity_id': identity_id},
        {'_id': 1, 'version': 1, 'status': 1, 'superseded_by': 1,
         'effective_from': 1, 'effective_from_precision': 1,
         'properties': 1}).to_list(length=None)
    records = await published_evidence(request, identity_id)
    now = now_iso()

    # snapshot target: the as-of sets of the live snapshots, nothing for the
    # others (a corrected or withdrawn state no longer resolves)
    contexts = contexts_for(identity, snapshots, records)
    live_ids = {s['_id'] for s in live_snapshots(snapshots)}
    for snap in snapshots:
        sid = snap['_id']
        new = fold(quantities_of_scope('snapshot'),
                   snapshot_inputs(records, contexts, sid),
                   now=now).properties if sid in live_ids else {}
        if not same_properties(snap.get('properties') or {}, new):
            await _write_snapshot_properties(request, sid, new)

    # identity target, with inheritance from the parents
    parents = await _parents(request, identity)
    result = fold(quantities_of_scope('identity'), records,
                  parents_of=lambda: parents, now=now)
    old = identity.get('properties') or {}
    if same_properties(old, result.properties):
        return False
    update = await identities.update_one(
        {'_id': identity_id, 'lastmodified': identity.get('lastmodified')},
        {'$set': {'properties': keep_derived_at(old, result.properties),
                  'properties_version': PROPERTIES_VERSION,
                  'lastmodified': now}})
    if not update.matched_count:                 # changed meanwhile: again
        seen.discard(identity_id)
        return await recompute_properties(request, identity_id, _seen=seen)
    children = await identities.find(
        {'parent_identities': identity_id}, {'_id': 1}).to_list(length=None)
    for child in children:
        await recompute_properties(request, child['_id'], _seen=seen)
    return True


async def evidence_fold_view(request: Request, identity: Dict[str, Any], *,
                             as_of: Optional[str] = None
                             ) -> Dict[str, Any]:
    """``GET /identities/{id}/properties``: the stored properties and the
    outranked records. With ``as_of`` the identity-scoped quantities are
    recomputed over the records observed up to that date --- computed, not
    stored, and without inheritance (the parents' own windows are not
    reconstructed)."""
    records = await published_evidence(request, identity['_id'])
    if as_of is not None:
        records = window(records, as_of)
    parents = [] if as_of is not None else await _parents(request, identity)
    result = fold(quantities_of_scope('identity'), records,
                  parents_of=lambda: parents, now=now_iso())
    properties = result.properties if as_of is not None \
        else (identity.get('properties') or {})
    return {'identity_id': identity['_id'], 'as_of': as_of,
            'properties': properties,
            'outranked_evidence_ids': result.outranked}
