#!/usr/bin/env python3.13
"""
Batches and draws (data model spec section 3.1.6, I32; decisions 8.105,
8.110).

A **batch** is an identity whose current snapshot has ``quantity > 1``. A
**draw** is a child naming the batch as its only parent; it takes
``quantity`` pieces out. ``remaining = quantity - drawn`` is derived from
the published children and never stored.

The helpers read; the routes that create or publish a draw call them.
``batch_lock`` serialises the check and the publish of draws on one batch
inside a process; the publish verifies once more afterwards, so a second
worker cannot overdraw either.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import HTTPException, Request

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.lineage import ChildFacts, drawn_quantity
from apps.catalog.models import User
from apps.catalog.permissions import dataset_roles
from apps.catalog.vocab import EVER_PUBLISHED_STATUSES
from .access import dataset_of, viewer_of

_LOCKS: Dict[str, List[Any]] = {}      # id -> [lock, users]


@asynccontextmanager
async def batch_locks(ids):
    """Hold the locks of these identities, taken in sorted order (no two
    requests wait on each other); a lock nobody holds or waits for is
    dropped again, so the table stays as small as the work in flight."""
    taken = sorted(set(ids))
    for key in taken:
        _LOCKS.setdefault(key, [asyncio.Lock(), 0])[1] += 1
    held = []
    try:
        for key in taken:
            await _LOCKS[key][0].acquire()
            held.append(key)
        yield
    finally:
        for key in held:
            _LOCKS[key][0].release()
        for key in taken:
            _LOCKS[key][1] -= 1
            if _LOCKS[key][1] == 0:
                del _LOCKS[key]


async def current_quantity(request: Request, identity: Dict[str, Any]
                           ) -> Optional[int]:
    """The quantity of the identity's current snapshot, None without one."""
    current = identity.get('current_snapshot_id')
    if not current:
        return None
    snap = await request.app.mongodb_component_snapshots.find_one(
        {'_id': current}, {'quantity': 1})
    return int((snap or {}).get('quantity') or 1) if snap else None


async def batch_size(request: Request, identity: Dict[str, Any]
                     ) -> Optional[int]:
    """The recorded size of a batch, None for anything else."""
    size = await current_quantity(request, identity)
    return size if size and size > 1 else None


async def child_facts(request: Request, parent_id: str) -> List[ChildFacts]:
    """What the exit rule needs to know about each child of a parent: how
    many parents it has, whether it is withdrawn, when its first published
    state starts and how many pieces that state records."""
    children = await request.app.mongodb_component_identities.find(
        {'parent_identities': parent_id},
        {'parent_identities': 1, 'withdrawn': 1}).to_list(length=None)
    facts = []
    for child in children:
        first = await request.app.mongodb_component_snapshots.find_one(
            {'identity_id': child['_id'], 'superseded_by': None,
             'status': {'$in': list(EVER_PUBLISHED_STATUSES)}},
            {'effective_from': 1, 'effective_from_precision': 1,
             'quantity': 1},
            sort=[('effective_from', 1), ('version', -1)])
        facts.append(ChildFacts(
            child_id=child['_id'],
            parent_count=len(child.get('parent_identities') or []),
            withdrawn=bool(child.get('withdrawn')),
            first_published_at=first.get('effective_from') if first else None,
            first_published_precision=(
                first.get('effective_from_precision') or 'exact')
            if first else 'exact',
            quantity=int(first.get('quantity') or 1) if first else 1))
    return facts


async def drawn_total(request: Request, batch_id: str, *,
                      excluding: Optional[str] = None) -> int:
    """Pieces drawn so far, leaving out one child (the one being checked)."""
    return drawn_quantity([f for f in await child_facts(request, batch_id)
                           if f.child_id != excluding])


async def remaining_of(request: Request, identity: Dict[str, Any], *,
                       excluding: Optional[str] = None) -> Optional[int]:
    """``remaining`` of a batch; None when the identity is not one."""
    size = await batch_size(request, identity)
    if size is None:
        return None
    return size - await drawn_total(request, identity['_id'],
                                    excluding=excluding)


async def draw_parent(request: Request, parents: List[Dict[str, Any]]
                      ) -> Optional[Dict[str, Any]]:
    """The batch a child with exactly these parents draws from."""
    if len(parents) == 1 and await batch_size(request, parents[0]):
        return parents[0]
    return None


async def refuse_batch_merge(request: Request, parents: List[Dict[str, Any]]
                             ) -> None:
    """409: a batch is only drawn from, never merged (8.110)."""
    if len(parents) < 2:
        return
    for parent in parents:
        if await batch_size(request, parent):
            raise HTTPException(
                status_code=409,
                detail='A batch is only drawn from; it cannot be a parent '
                       'of a merge (8.110).')


async def check_draw_rights(request: Request, user: User,
                            batch: Dict[str, Any]) -> None:
    """409: while a batch is reserved, only the reserving user or a
    moderator of its dataset draws from it (8.110)."""
    holder = batch.get('reserved') or ''
    if not holder or holder == user.id:
        return
    viewer = viewer_of(user)
    dataset = await dataset_of(request, batch.get('dataset'))
    if viewer.is_admin or 'moderator' in dataset_roles(viewer, dataset):
        return
    raise HTTPException(
        status_code=409,
        detail='The batch is reserved by someone else; only the reserving '
               'user or a moderator draws from it (8.110).')


async def check_draw_fits(request: Request, batch: Dict[str, Any],
                          quantity: int, *,
                          excluding: Optional[str] = None) -> None:
    """409: the draw takes more pieces than remain (8.105)."""
    remaining = await remaining_of(request, batch, excluding=excluding)
    if remaining is not None and quantity > remaining:
        size = await batch_size(request, batch)
        raise HTTPException(
            status_code=409,
            detail=f'Only {max(remaining, 0)} of {size} pieces remain in '
                   f'the batch; the draw takes {quantity} (8.105).')


async def check_batch_correction(request: Request, identity: Dict[str, Any],
                                 quantity: int) -> None:
    """409: a correction cannot take a batch below what was drawn (I32)."""
    drawn = await drawn_total(request, identity['_id'])
    if quantity < drawn:
        raise HTTPException(
            status_code=409,
            detail=f'{drawn} pieces were drawn from this batch; its '
                   f'quantity cannot go below that (I32).')


async def authored_proxies(request: Request, batch: Dict[str, Any]
                           ) -> List[Dict[str, Any]]:
    """The authored proxies of the batch's current snapshot: what a draw
    starts from (8.105)."""
    current = batch.get('current_snapshot_id')
    snap = await request.app.mongodb_component_snapshots.find_one(
        {'_id': current}, {'geometry.proxies': 1}) if current else None
    proxies = ((snap or {}).get('geometry') or {}).get('proxies') or []
    return [p for p in proxies
            if (p.get('fit') or {}).get('method') == 'authored']
