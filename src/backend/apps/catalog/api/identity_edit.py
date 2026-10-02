#!/usr/bin/env python3.13
"""
Creating and editing components, their circulation and their lineage
(data model spec section 3.1.1 -- 3.1.3, section 7.1, I16 -- I18, I25,
I30; decisions 6.2, 8.8, 8.19, 8.31 -- 8.36, 8.38; plan P4).

* ``POST /identities`` --- a new component with its v0 draft; a child
  (``parent_identities``) inherits what it does not state
* ``PATCH /identities/{id}`` --- metadata; a child's own edit detaches the
  unit, adding a unit to ``inherited_fields`` takes it back, a parent's
  edit propagates to every descendant still inheriting it
* ``POST /identities/{id}/exit``, ``DELETE /identities/{id}/exit`` ---
  leave circulation, undo a mistaken exit
* ``POST /identities/{id}/reenter`` --- back into circulation with a new
  origin; the old cycle is archived

``sync_parent_exits`` keeps the split / merged exit of a child's parents
true (8.8, 8.34); the snapshot and identity lifecycles call it.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import copy
import json
import uuid
from collections import deque
from typing import Annotated, Any, Dict, Iterable, List, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import (
    CircularityClass,
    ComponentIdentity,
    ConstructionWork,
    LowCode,
    Origin,
    Timestamp,
)
from apps.catalog.lifecycle import patch_problems
from apps.catalog.lineage import (
    KEEP,
    ChildFacts,
    changed_units,
    cut_refusal,
    derived_exit,
    detach_on_patch,
    inherit_on_create,
    propagate,
    reinherit,
)
from apps.catalog.models import User
from apps.catalog.permissions import Target, can, dataset_roles
from apps.catalog.read_models import identity_body, snapshot_body
from apps.catalog.vocab import (
    EVER_PUBLISHED_STATUSES,
    INHERIT_UNITS,
    TERMINAL_EXIT_KINDS,
    ExitKind,
    OriginalFunction,
    Precision,
)
from .access import (
    component_visible,
    dataset_of,
    deny_write,
    identity_ever_published,
    load_datasets,
    load_identity,
    require,
    viewer_of,
)
from .auth import get_current_active_user
from .catalog_common import allocate_catalog_number, now_iso, validate_uuid
from .change_log import log_change

router = APIRouter()


# BODIES ----------------------------------------------------------------------
class _Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True)


class IdentityCreateBody(_Strict):
    """A new component and its v0. A child omits whatever it inherits."""
    id: Optional[str] = Field(None, description='UUID from the tag; '
                                                'generated when omitted')
    dataset: str
    parent_identities: Optional[List[str]] = Field(None, min_length=1)
    original_function: Optional[OriginalFunction] = None
    material: Optional[str] = None
    material_class: Optional[LowCode] = Field(
        None, description='set by hand (assigned); omit to derive')
    trade_name: Optional[str] = None
    manufacturer: Optional[str] = None
    connection_features: Optional[str] = None
    material_separability: Optional[CircularityClass] = None
    manufactured_at: Optional[Timestamp] = None
    manufactured_precision: Optional[Precision] = None
    origin: Optional[Origin] = None
    is_public: bool = False
    attributes: Dict[str, Any] = Field(default_factory=dict)
    snapshot: Dict[str, Any] = Field(description='the v0 draft '
                                                 '(POST /identities/{id}/'
                                                 'snapshots body)')


class ExitBody(_Strict):
    kind: ExitKind
    at: Timestamp
    at_precision: Precision = 'exact'
    construction_work: Optional[ConstructionWork] = None
    notes: Optional[str] = None


class ReenterBody(_Strict):
    origin: Origin


# HELPERS ---------------------------------------------------------------------
def _same(a: Any, b: Any) -> bool:
    return json.dumps(a, sort_keys=True, default=str) == \
        json.dumps(b, sort_keys=True, default=str)


def _validated(doc: Dict[str, Any]) -> Dict[str, Any]:
    """The identity as stored, or 422 naming the first problem."""
    try:
        return ComponentIdentity.model_validate(doc).model_dump(
            by_alias=True, mode='json')
    except ValidationError as exc:
        first = exc.errors()[0]
        where = '.'.join(str(p) for p in first.get('loc', ()))
        raise HTTPException(status_code=422,
                            detail=f'{where}: {first["msg"]}') from exc


async def _material(request: Request, mid: str, *,
                    allow_retired: bool) -> Dict[str, Any]:
    doc = await request.app.mongodb_materials.find_one({'_id': mid})
    if doc is None:
        raise HTTPException(status_code=422,
                            detail=f'material: unknown material {mid!r} '
                                   f'(GET /materials)')
    if doc.get('merged_into'):
        raise HTTPException(status_code=422,
                            detail=f'material: {mid!r} is merged into '
                                   f'{doc["merged_into"]!r}; use that.')
    if doc.get('retired') and not allow_retired:
        raise HTTPException(status_code=422,
                            detail=f'material: {mid!r} is retired.')
    return doc


async def _material_class(request: Request, values: Dict[str, Any],
                          stated: Dict[str, Any], *,
                          allow_retired: bool) -> None:
    """Fill ``material_class`` (+ source) for a stated material (I25): a
    stated class is assigned, otherwise it is derived from the default."""
    if 'material' not in stated and 'material_class' not in stated:
        return
    material = await _material(request, values['material'],
                               allow_retired=allow_retired)
    if stated.get('material_class') is not None:
        values['material_class_source'] = 'assigned'
    else:
        values['material_class'] = material['default_class']
        values['material_class_source'] = 'derived'


async def _identity(request: Request, identity_id: str) -> Dict[str, Any]:
    validate_uuid(identity_id, label='identity id')
    return await load_identity(request, identity_id)


async def _write(request: Request, before: Dict[str, Any],
                 after: Dict[str, Any], *, user_id: Optional[str],
                 cause: str, source: Optional[str] = None
                 ) -> Optional[Dict[str, Any]]:
    """Store one identity change and log it (I30); None when nothing
    changed. ``before`` is compared as the model stores it, so defaults a
    migrated document lacks are not logged as changes."""
    try:
        stored = ComponentIdentity.model_validate(before).model_dump(
            by_alias=True, mode='json')
    except ValidationError:
        stored = before
    entry = await log_change(request, 'identity', stored, after,
                             by_user_id=user_id, cause=cause,
                             source_record_id=source)
    if entry is None:
        return None
    after = {**after, 'lastmodified': entry['at']}
    result = await request.app.mongodb_component_identities.replace_one(
        {'_id': before['_id'], 'lastmodified': before.get('lastmodified')},
        after)
    if result.matched_count == 0:
        raise HTTPException(status_code=409,
                            detail='The component changed meanwhile; reload.')
    return after


# LINEAGE ---------------------------------------------------------------------
async def _parents_of(request: Request, child: Dict[str, Any]
                      ) -> List[Dict[str, Any]]:
    ids = child.get('parent_identities') or []
    docs = await request.app.mongodb_component_identities.find(
        {'_id': {'$in': ids}}).to_list(length=None)
    by_id = {d['_id']: d for d in docs}
    return [by_id[i] for i in ids if i in by_id]


async def propagate_from(request: Request, parent: Dict[str, Any],
                         units: Iterable[str], *, user_id: Optional[str]
                         ) -> int:
    """
    Breadth-first down the lineage: every descendant still inheriting a
    changed unit takes it over, in the same request, whatever its dataset
    (8.31); a merged child whose parents now disagree lets go (8.33).
    Each changed child gets a change-log entry naming the parent.
    """
    queue = deque([(parent['_id'], list(units))])
    changed = 0
    while queue:
        parent_id, unit_list = queue.popleft()
        if not unit_list:
            continue
        children = await request.app.mongodb_component_identities.find(
            {'parent_identities': parent_id,
             'inherited_fields': {'$in': unit_list}}).to_list(length=None)
        for child in children:
            parents = await _parents_of(request, child)
            update = propagate(child, parents, unit_list)
            if not update.changed:
                continue
            after = _validated({**child, **update.set_values,
                                'inherited_fields': update.inherited_fields,
                                'inherited_from': child.get('inherited_from')
                                if update.inherited_fields else None})
            written = await _write(request, child, after, user_id=user_id,
                                   cause='inherited_from_parent',
                                   source=parent_id)
            if written is not None:
                changed += 1
                queue.append((child['_id'], changed_units(child, written)))
    return changed


async def _child_facts(request: Request, parent_id: str) -> List[ChildFacts]:
    children = await request.app.mongodb_component_identities.find(
        {'parent_identities': parent_id},
        {'parent_identities': 1, 'withdrawn': 1}).to_list(length=None)
    facts = []
    for child in children:
        first = await request.app.mongodb_component_snapshots.find_one(
            {'identity_id': child['_id'],
             'status': {'$in': list(EVER_PUBLISHED_STATUSES)}},
            {'effective_from': 1, 'effective_from_precision': 1},
            sort=[('effective_from', 1)])
        facts.append(ChildFacts(
            child_id=child['_id'],
            parent_count=len(child.get('parent_identities') or []),
            withdrawn=bool(child.get('withdrawn')),
            first_published_at=first.get('effective_from') if first else None,
            first_published_precision=(
                first.get('effective_from_precision') or 'exact')
            if first else 'exact'))
    return facts


async def sync_parent_exits(request: Request, parent_ids: Iterable[str], *,
                            user_id: Optional[str],
                            source: Optional[str] = None) -> List[str]:
    """Keep each parent's split / merged exit true to its children (8.8,
    8.34): set on the first published child, moved with its date, cleared
    with the last one. Setting it clears the parent's reservation (I18).
    Returns the parents that changed."""
    changed = []
    for parent_id in dict.fromkeys(parent_ids):
        parent = await request.app.mongodb_component_identities.find_one(
            {'_id': parent_id})
        if parent is None:
            continue
        exit_ = derived_exit(parent, await _child_facts(request, parent_id))
        if exit_ is KEEP or _same(exit_, parent.get('exit')):
            continue
        after = {**parent, 'exit': exit_}
        if exit_ is not None:
            after['reserved'] = ''
        after = _validated(after)
        if await _write(request, parent, after, user_id=user_id,
                        cause='derived_exit', source=source) is not None:
            changed.append(parent_id)
    return changed


async def check_cut_allowed(request: Request,
                            parents: Iterable[Dict[str, Any]]) -> None:
    """409 when a parent cannot be cut (8.34)."""
    for parent in parents:
        reason = cut_refusal(
            parent, ever_published=await identity_ever_published(
                request, parent))
        if reason:
            raise HTTPException(status_code=409, detail=reason)


# CREATE ----------------------------------------------------------------------
@router.post('/identities', status_code=201,
             summary='Create a component and its v0 draft; a child inherits')
async def create_identity(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: IdentityCreateBody,
):
    """
    ``contributor(D)``; a child also needs read access to each parent and
    each parent must be cuttable (8.8, 8.34). Every inheritance unit the
    body does not state is copied from the parents (3.1.2); a merge whose
    parents disagree on ``material`` or ``original_function`` needs them
    stated. The identity stays unpublished until its v0 is published.
    """
    from .snapshot_lifecycle import (  # the snapshot module imports this one
        SnapshotDraftBody,
        new_snapshot_doc,
    )
    viewer = viewer_of(current_user)
    identity_id = body.id or str(uuid.uuid4())
    validate_uuid(identity_id, label='identity id')
    identities = request.app.mongodb_component_identities
    if await identities.find_one({'_id': identity_id}, {'_id': 1}):
        raise HTTPException(status_code=409,
                            detail=f'Identity {identity_id} already exists')
    datasets = await load_datasets(request)
    if body.dataset not in datasets:
        raise HTTPException(status_code=422,
                            detail=f'dataset: unknown dataset {body.dataset!r}')

    parents: List[Dict[str, Any]] = []
    for pid in body.parent_identities or []:
        validate_uuid(pid, label='parent identity id')
        if pid == identity_id:
            raise HTTPException(status_code=422,
                                detail='A component is not its own parent.')
        parent = await identities.find_one({'_id': pid})
        if parent is None:
            raise HTTPException(status_code=404,
                                detail=f'Parent identity {pid} not found')
        parents.append(parent)
    readable = True
    for parent in parents:
        readable = readable and await component_visible(request, viewer,
                                                        parent)
    target = Target(dataset=datasets[body.dataset], kind='identity',
                    readable=readable)
    if not can(viewer, 'create_identity', target):
        raise deny_write(viewer, 'create_identity')
    await check_cut_allowed(request, parents)

    snapshot_body_in = SnapshotDraftBody.model_validate(body.snapshot)
    stated = body.model_dump(
        mode='json', by_alias=True, exclude_unset=True,
        exclude={'id', 'dataset', 'parent_identities', 'is_public',
                 'attributes', 'snapshot'})
    values: Dict[str, Any] = {}
    inherited_fields: List[str] = []
    inherited_from: Optional[str] = None
    if parents:
        inheritance = inherit_on_create(stated, parents)
        if inheritance.missing:
            raise HTTPException(
                status_code=422,
                detail=f'The parents disagree on {inheritance.missing}; '
                       f'state them (8.33).')
        values.update(inheritance.values)
        inherited_fields = inheritance.inherited_fields
        inherited_from = inheritance.inherited_from
    else:
        for required in ('original_function', 'material'):
            if stated.get(required) is None:
                raise HTTPException(status_code=422,
                                    detail=f'{required}: required for a '
                                           f'component without parents')
    values.update(stated)
    await _material_class(request, values, stated, allow_retired=False)

    now = now_iso()
    catalog_number = await allocate_catalog_number(request)
    doc = _validated({
        **values, '_id': identity_id, 'catalog_number': catalog_number,
        'dataset': body.dataset,
        'parent_identities': body.parent_identities or None,
        'inherited_fields': inherited_fields,
        'inherited_from': inherited_from,
        'exit': None, 'past_cycles': [], 'withdrawn': None, 'reserved': '',
        'is_public': body.is_public, 'current_snapshot_id': None,
        'properties': {}, 'properties_version': 1,
        'attributes': body.attributes, 'created_by_user_id': current_user.id,
        'created': now, 'lastmodified': now})

    # v0 starts when the piece left its previous context (8.10); a cut at
    # the moment it is recorded unless stated
    origin = doc.get('origin') or {}
    effective_from = snapshot_body_in.effective_from
    precision = snapshot_body_in.effective_from_precision
    if effective_from is None and not parents and origin.get('at'):
        effective_from = origin['at']
        precision = precision or origin.get('at_precision') or 'exact'
    snapshot = new_snapshot_doc(
        snapshot_body_in, identity_id=identity_id, version=0,
        user=current_user, effective_from=effective_from or now,
        precision=precision or 'exact')

    await identities.insert_one(dict(doc))
    try:
        await request.app.mongodb_component_snapshots.insert_one(
            dict(snapshot))
    except Exception:
        await identities.delete_one({'_id': identity_id})
        raise
    return JSONResponse(status_code=201, content={
        'identity': identity_body(doc), 'snapshot': snapshot_body(snapshot)})


# PATCH -----------------------------------------------------------------------
@router.patch('/identities/{identity_id}',
              summary='Edit component metadata; lineage follows (3.1.2)')
async def patch_identity(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    identity_id: str,
    body: Annotated[Dict[str, Any], Body()],
):
    """
    ``moderator(D)``; while unpublished also its creator (8.9). Patching a
    field of an inherited unit makes the unit the component's own; adding
    a unit to ``inherited_fields`` takes it back from the parents. A
    changed unit propagates to every descendant still inheriting it
    (8.31). ``material`` without ``material_class`` re-derives the class;
    ``material_class: null`` returns it to derived (I25).
    """
    identity = await _identity(request, identity_id)
    viewer = viewer_of(current_user)
    await require(request, current_user, 'patch_identity', identity=identity)
    dataset = await dataset_of(request, identity.get('dataset'))
    published = await identity_ever_published(request, identity)
    problems = patch_problems(
        'identity', {k: [] for k in body}, identity_published=published,
        is_author=current_user.id == identity.get('created_by_user_id'),
        is_moderator=viewer.is_admin or 'moderator' in dataset_roles(
            viewer, dataset))
    if problems.get('derived'):
        raise HTTPException(status_code=422, detail={
            'message': 'Server-maintained fields cannot be set.',
            'fields': problems['derived']})
    if problems.get('forbidden'):
        raise deny_write(viewer, 'edit ' + ', '.join(problems['forbidden']))

    current_units = list(identity.get('inherited_fields') or [])
    after = copy.deepcopy(identity)
    fields = {k: v for k, v in body.items() if k != 'inherited_fields'}
    after.update(fields)

    # a child's own edit makes the unit its own (3.1.2)
    detached = detach_on_patch(identity, fields)
    units = [u for u in current_units if u not in detached]

    # material: a stated class is assigned, otherwise derived (I25)
    if 'material' in fields or 'material_class' in fields:
        material = await _material(
            request, after.get('material'),
            allow_retired=after.get('material') == identity.get('material'))
        if fields.get('material_class') is not None:
            after['material_class_source'] = 'assigned'
        else:
            after['material_class'] = material['default_class']
            after['material_class_source'] = 'derived'

    # re-inherit: units added to inherited_fields (I17)
    if 'inherited_fields' in body:
        wanted = body['inherited_fields']
        if not isinstance(wanted, list) or not set(units) <= set(wanted):
            raise HTTPException(
                status_code=422,
                detail='inherited_fields: only additions (re-inherit); a '
                       'unit becomes the component\'s own when you edit it.')
        added = [u for u in wanted if u not in units]
        if added:
            if any(set(fields) & set(INHERIT_UNITS[u]) for u in added):
                raise HTTPException(
                    status_code=422,
                    detail='Re-inherit a unit or edit it, not both.')
            try:
                update = reinherit({**after, 'inherited_fields': units},
                                   await _parents_of(request, identity),
                                   added)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            after.update(update.set_values)
            units = update.inherited_fields

    after['inherited_fields'] = units
    after['inherited_from'] = identity.get('inherited_from') if units else None
    if units and not after['inherited_from']:
        after['inherited_from'] = (identity.get('parent_identities') or
                                   [None])[0]
    after = _validated(after)
    written = await _write(request, identity, after,
                           user_id=current_user.id, cause='patch')
    if written is None:
        return JSONResponse(status_code=200, content=identity_body(identity))
    await propagate_from(request, written, changed_units(identity, written),
                         user_id=current_user.id)
    return JSONResponse(status_code=200, content=identity_body(written))


# CIRCULATION -----------------------------------------------------------------
@router.post('/identities/{identity_id}/exit',
             summary='Take a component out of circulation (moderator(D))')
async def exit_identity(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    identity_id: str,
    body: ExitBody,
):
    """Installed, recycled, disposed, returned, lost --- or a hand-set
    ``split`` without catalogued pieces. ``merged`` is only ever set by the
    server (8.8). ``construction_work`` only for ``installed`` (I18)."""
    identity = await _identity(request, identity_id)
    await require(request, current_user, 'exit', identity=identity)
    if identity.get('withdrawn'):
        raise HTTPException(status_code=409, detail='The component is '
                                                    'withdrawn.')
    if not await identity_ever_published(request, identity):
        raise HTTPException(status_code=409,
                            detail='Not published yet: it never entered '
                                   'circulation.')
    if identity.get('exit'):
        raise HTTPException(status_code=409,
                            detail='Already out of circulation; undo that '
                                   'exit first.')
    if body.kind == 'merged':
        raise HTTPException(status_code=422,
                            detail='merged is set by the server when a '
                                   'merged piece is published (8.8).')
    exit_ = {**body.model_dump(mode='json'),
             'recorded_by_user_id': current_user.id}
    after = _validated({**identity, 'exit': exit_, 'reserved': ''})
    written = await _write(request, identity, after,
                           user_id=current_user.id, cause='exit')
    return JSONResponse(status_code=200, content=identity_body(written))


@router.delete('/identities/{identity_id}/exit',
               summary='Undo a mistaken exit (moderator(D))')
async def undo_exit(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    identity_id: str,
):
    """Not for a split / merge the server keeps from published children:
    withdraw the child instead (8.8)."""
    identity = await _identity(request, identity_id)
    await require(request, current_user, 'exit', identity=identity)
    exit_ = identity.get('exit')
    if not exit_:
        raise HTTPException(status_code=409, detail='The component is in '
                                                    'circulation.')
    if exit_.get('recorded_by_user_id') is None:
        raise HTTPException(
            status_code=409,
            detail='This split / merge follows from published pieces cut '
                   'from it; withdraw those to undo it (8.8).')
    after = _validated({**identity, 'exit': None})
    written = await _write(request, identity, after,
                           user_id=current_user.id, cause='exit')
    return JSONResponse(status_code=200, content=identity_body(written))


@router.post('/identities/{identity_id}/reenter',
             summary='Bring a component back into circulation '
                     '(moderator(D))')
async def reenter_identity(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    identity_id: str,
    body: ReenterBody,
):
    """
    An installed, returned or lost piece comes back with a new origin; the
    old ``{origin, exit}`` goes to ``past_cycles`` (3.1.3). Terminal exits
    cannot re-enter (I18). The next snapshot defaults to the new
    ``origin.at`` (8.19). A re-entered child owns its new origin.
    """
    identity = await _identity(request, identity_id)
    await require(request, current_user, 'reenter', identity=identity)
    exit_ = identity.get('exit')
    if not exit_:
        raise HTTPException(status_code=409, detail='The component is in '
                                                    'circulation.')
    if exit_.get('kind') in TERMINAL_EXIT_KINDS:
        raise HTTPException(status_code=409,
                            detail=f'A {exit_["kind"]} piece no longer exists '
                                   f'as this component; it cannot re-enter '
                                   f'(I18).')
    cycles = [*(identity.get('past_cycles') or []),
              {'origin': identity.get('origin'), 'exit': exit_}]
    units = [u for u in identity.get('inherited_fields') or []
             if u != 'origin']
    after = _validated({
        **identity, 'exit': None, 'past_cycles': cycles,
        'origin': body.origin.model_dump(mode='json', by_alias=True),
        'inherited_fields': units,
        'inherited_from': identity.get('inherited_from') if units else None})
    written = await _write(request, identity, after,
                           user_id=current_user.id, cause='reenter')
    await propagate_from(request, written, changed_units(identity, written),
                         user_id=current_user.id)
    return JSONResponse(status_code=200, content=identity_body(written))
