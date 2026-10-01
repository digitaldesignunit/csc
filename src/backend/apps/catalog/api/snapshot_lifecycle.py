#!/usr/bin/env python3.13
"""
The snapshot lifecycle (data model spec section 3.2.2, section 7.1, I3,
I3b, I15, I21; decisions 8.16, 8.17, 8.18, 8.30; plan P3).

* ``POST /identities/{id}/snapshots`` --- a new state, always a draft
* ``POST /snapshots/{sid}/supersede`` --- a correction of a published one
* ``POST /snapshots/{sid}/submit|recall|resubmit`` --- the author's steps
* ``POST /snapshots/{sid}/publish|reject|promote|withdraw|reinstate`` ---
  ``moderator(D)``
* ``PATCH /snapshots/{sid}`` --- per-field permission (8.3)
* ``DELETE /snapshots/{sid}`` --- only never-published records (I15)

Every status change appends to ``status_history`` (8.30). One snapshot per
identity is in flight at a time (I3b); ``current_snapshot_id`` always
points at a published, non-superseded snapshot or is null (I3b, 8.17).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import uuid
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import (
    Capture,
    ComponentSnapshot,
    GeoLocation,
    Geometry,
    Grade,
    Rgb,
    Timestamp,
)
from apps.catalog.lifecycle import patch_problems, transition_action
from apps.catalog.models import User
from apps.catalog.permissions import Target, can, dataset_roles
from apps.catalog.read_models import snapshot_body
from apps.catalog.vocab import Precision, ShapeClass
from .access import (
    EVER_PUBLISHED,
    dataset_of,
    deny_read,
    deny_write,
    load_identity,
    load_snapshot,
    require,
    snapshot_projection,
    viewer_of,
)
from .auth import get_current_active_user
from .catalog_common import compute_snapshot_etag, now_iso, validate_uuid

router = APIRouter()

IN_FLIGHT = ('draft', 'pending')


# BODIES ----------------------------------------------------------------------
class SnapshotDraftBody(BaseModel):
    """A new state or a correction, as the client sends it. Derived fields
    (frame, bbx, descriptors, fitted proxies, ...) are never accepted."""
    model_config = ConfigDict(extra='forbid')

    name: Optional[str] = None
    effective_from: Optional[Timestamp] = Field(
        None, description='a new state: default now; a correction inherits')
    effective_from_precision: Optional[Precision] = None
    geometry: Geometry
    capture: Optional[Capture] = None
    shape_class: Optional[ShapeClass] = Field(
        None, description='set by hand (assigned); omit to derive')
    complexity: Optional[Grade] = Field(
        None, description='set by hand (assigned); omit to derive')
    fragment: bool = False
    quantity: int = Field(1, ge=1)
    color: Optional[Rgb] = None
    location: Optional[GeoLocation] = None
    notes: Optional[str] = None


class ReasonBody(BaseModel):
    reason: str = Field(min_length=1)


class WithdrawBody(BaseModel):
    reason: str = Field(min_length=1)
    replacement_id: Optional[str] = Field(
        None, description='published snapshot to become current instead')


# HELPERS ---------------------------------------------------------------------
def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


async def _snapshots_of(request: Request, identity_id: str) -> List[dict]:
    return await request.app.mongodb_component_snapshots.find(
        {'identity_id': identity_id}).sort('version', 1).to_list(length=None)


def _live(snapshots: List[dict]) -> List[dict]:
    """Published, non-superseded: what resolution, promotion and I3 see."""
    return [s for s in snapshots
            if s.get('status') == 'published' and not s.get('superseded_by')]


def _ensure_nothing_in_flight(snapshots: List[dict],
                              except_id: Optional[str] = None) -> None:
    """I3b: one draft or pending snapshot per identity."""
    for snap in snapshots:
        if snap['_id'] != except_id and snap.get('status') in IN_FLIGHT:
            raise HTTPException(
                status_code=409,
                detail=f'Snapshot v{snap["version"]} is already '
                       f'{snap["status"]}; finish or delete it first (I3b).')


def _ensure_monotonic(snapshot: dict, snapshots: List[dict]) -> None:
    """I3: over live snapshots, effective_from does not go back in time
    as the version grows (a correction shares its predecessor's)."""
    mine = _ts(snapshot['effective_from'])
    for other in _live(snapshots):
        if other['_id'] in (snapshot['_id'], snapshot.get('supersedes')):
            continue
        theirs = _ts(other['effective_from'])
        if (other['version'] < snapshot['version'] and theirs > mine) or \
                (other['version'] > snapshot['version'] and theirs < mine):
            raise HTTPException(
                status_code=409,
                detail=f'effective_from {snapshot["effective_from"]} breaks '
                       f'the order with v{other["version"]} '
                       f'({other["effective_from"]}); adjust it first (I3).')


def _validated(doc: dict) -> dict:
    try:
        ComponentSnapshot.model_validate(doc)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = '.'.join(str(p) for p in first.get('loc', ()))
        raise HTTPException(status_code=422,
                            detail=f'{where}: {first["msg"]}') from exc
    doc['etag'] = compute_snapshot_etag(doc)
    return doc


def _check_client_geometry(body: SnapshotDraftBody) -> None:
    """Fitted proxies are derived (3.2.1): a client sends authored ones."""
    for proxy in body.geometry.proxies:
        if proxy.fit.method != 'authored':
            raise HTTPException(
                status_code=422,
                detail='geometry.proxies: only authored proxies are accepted;'
                       ' fitted ones are computed by the server')


def _new_snapshot(body: SnapshotDraftBody, *, identity_id: str, version: int,
                  user: User, effective_from: str, precision: str,
                  supersedes: Optional[str] = None) -> dict:
    now = now_iso()
    data = body.model_dump(mode='json', exclude={
        'effective_from', 'effective_from_precision'})
    doc = {
        **data,
        '_id': str(uuid.uuid4()), 'identity_id': identity_id,
        'version': version, 'status': 'draft',
        'status_changed_by_user_id': user.id, 'status_changed_at': now,
        'status_history': [], 'supersedes': supersedes, 'superseded_by': None,
        'effective_from': effective_from,
        'effective_from_precision': precision,
        'shape_class_source': 'assigned' if body.shape_class else None,
        'complexity_source': 'assigned' if body.complexity is not None
        else None,
        'descriptors': {}, 'properties': {}, 'properties_version': 1,
        'frame': None, 'bbx': None,
        'added_by_user_id': user.id, 'added_by_username': user.username,
        'photo_count': 0, 'mesh_ply_resolutions': {},
        'created': now, 'lastmodified': now,
    }
    return _validated(doc)


async def _insert(request: Request, doc: dict) -> JSONResponse:
    await request.app.mongodb_component_snapshots.insert_one(doc)
    return JSONResponse(status_code=201, content=snapshot_body(doc))


async def _change_status(request: Request, user: User, snapshot: dict,
                         to: str, *, reason: Optional[str] = None,
                         also: Optional[Dict[str, Any]] = None) -> dict:
    """Move one snapshot to ``to``: history entry (8.30), new etag; fails
    with 409 if someone changed its status meanwhile."""
    now = now_iso()
    entry = {'from': snapshot['status'], 'to': to, 'at': now,
             'by_user_id': user.id, 'reason': reason}
    updated = {
        **snapshot, **(also or {}), 'status': to,
        'status_changed_by_user_id': user.id, 'status_changed_at': now,
        'status_history': [*(snapshot.get('status_history') or []), entry],
        'lastmodified': now,
    }
    updated = _validated(updated)
    result = await request.app.mongodb_component_snapshots.replace_one(
        {'_id': snapshot['_id'], 'status': snapshot['status']}, updated)
    if result.matched_count == 0:
        raise HTTPException(status_code=409,
                            detail='The snapshot changed meanwhile; reload.')
    return updated


async def _set_current(request: Request, identity_id: str,
                       snapshot_id: Optional[str]) -> None:
    await request.app.mongodb_component_identities.update_one(
        {'_id': identity_id},
        {'$set': {'current_snapshot_id': snapshot_id,
                  'lastmodified': now_iso()}})


async def _can(request: Request, user: User, action: str,
               identity: dict, snapshot: dict) -> bool:
    """``can`` without raising (submit?publish=1 asks before acting)."""
    viewer = viewer_of(user)
    dataset = await dataset_of(request, identity.get('dataset'))
    return can(viewer, action, Target(
        dataset=dataset, kind='snapshot', status=snapshot.get('status'),
        author_id=snapshot.get('added_by_user_id')))


def _transition_or_409(snapshot: dict, to: str) -> str:
    action = transition_action(snapshot.get('status'), to)
    if action is None:
        raise HTTPException(
            status_code=409,
            detail=f'A {snapshot.get("status")} snapshot cannot become {to} '
                   f'(I15).')
    return action


async def _load(request: Request, snapshot_id: str):
    validate_uuid(snapshot_id, label='snapshot id')
    snapshot = await load_snapshot(request, snapshot_id)
    identity = await load_identity(request, str(snapshot['identity_id']))
    return snapshot, identity


def _ok(doc: dict) -> JSONResponse:
    return JSONResponse(status_code=200, content=snapshot_body(doc))


async def _publish(request: Request, user: User, snapshot: dict,
                   identity: dict, *, promote: bool) -> dict:
    """pending --> published (moderator(D); a child's first snapshot also
    needs moderator of every parent's dataset, 8.8). A correction marks
    its predecessor superseded and replaces it as current."""
    viewer = viewer_of(user)
    first = not any(s.get('status') in EVER_PUBLISHED
                    for s in await _snapshots_of(request, identity['_id']))
    parents = []
    if first:
        for pid in identity.get('parent_identities') or []:
            parent = await request.app.mongodb_component_identities.find_one(
                {'_id': pid}, {'dataset': 1})
            if parent is not None:
                parents.append(await dataset_of(request, parent['dataset']))
    target = Target(dataset=await dataset_of(request, identity.get('dataset')),
                    kind='snapshot', status=snapshot.get('status'),
                    author_id=snapshot.get('added_by_user_id'),
                    parent_datasets=tuple(parents))
    if not can(viewer, 'publish', target):
        raise deny_write(viewer, 'publish')
    _ensure_monotonic(snapshot, await _snapshots_of(request, identity['_id']))

    predecessor = None
    if snapshot.get('supersedes'):
        predecessor = await request.app.mongodb_component_snapshots.find_one(
            {'_id': snapshot['supersedes']})
        if predecessor is None or predecessor.get('status') != 'published' \
                or predecessor.get('superseded_by'):
            raise HTTPException(
                status_code=409,
                detail='The snapshot it corrects is no longer a published, '
                       'uncorrected one (I21).')
    published = await _change_status(request, user, snapshot, 'published')
    current = identity.get('current_snapshot_id')
    if predecessor is not None:
        await request.app.mongodb_component_snapshots.update_one(
            {'_id': predecessor['_id']},
            {'$set': {'superseded_by': published['_id'],
                      'lastmodified': now_iso()}})
        if current == predecessor['_id']:
            current = published['_id']
            await _set_current(request, identity['_id'], current)
    if promote or not current:
        # I3b: a current snapshot exists whenever a live one does
        await _set_current(request, identity['_id'], published['_id'])
    return published


# CREATE ----------------------------------------------------------------------
@router.post('/identities/{identity_id}/snapshots', status_code=201,
             summary='Record a new state of a component (always a draft)')
async def create_snapshot(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    identity_id: str,
    body: SnapshotDraftBody,
):
    """contributor(D). ``effective_from`` defaults to now. Only for a piece
    in circulation: an exited piece re-enters first (section 3.1.3)."""
    validate_uuid(identity_id, label='identity id')
    identity = await load_identity(request, identity_id)
    await require(request, current_user, 'create_snapshot',
                  identity=identity)
    if identity.get('withdrawn'):
        raise HTTPException(status_code=409,
                            detail='The component is withdrawn.')
    if identity.get('exit'):
        raise HTTPException(
            status_code=409,
            detail='The component is out of circulation; it re-enters '
                   'before it gets a new state (section 3.1.3).')
    _check_client_geometry(body)
    snapshots = await _snapshots_of(request, identity_id)
    _ensure_nothing_in_flight(snapshots)
    version = max((s['version'] for s in snapshots), default=-1) + 1
    doc = _new_snapshot(
        body, identity_id=identity_id, version=version, user=current_user,
        effective_from=body.effective_from or now_iso(),
        precision=body.effective_from_precision or 'exact')
    return await _insert(request, doc)


@router.post('/snapshots/{snapshot_id}/supersede', status_code=201,
             summary='Correct a published snapshot (a new draft)')
async def supersede_snapshot(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
    body: SnapshotDraftBody,
):
    """contributor(D). The correction inherits ``effective_from``; on
    publish it marks the old one superseded (section 3.2.2, I21)."""
    old, identity = await _load(request, snapshot_id)
    await require(request, current_user, 'supersede_snapshot',
                  identity=identity, snapshot=old)
    if old.get('status') != 'published' or old.get('superseded_by'):
        raise HTTPException(
            status_code=409,
            detail='Only a published, uncorrected snapshot is corrected '
                   '(I21).')
    _check_client_geometry(body)
    snapshots = await _snapshots_of(request, identity['_id'])
    _ensure_nothing_in_flight(snapshots)
    version = max(s['version'] for s in snapshots) + 1
    doc = _new_snapshot(
        body, identity_id=identity['_id'], version=version, user=current_user,
        effective_from=old['effective_from'],
        precision=old.get('effective_from_precision') or 'exact',
        supersedes=old['_id'])
    return await _insert(request, doc)


# THE AUTHOR'S STEPS ----------------------------------------------------------
@router.post('/snapshots/{snapshot_id}/submit',
             summary='draft --> pending (author)')
async def submit_snapshot(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
    publish: bool = Query(False, description='moderators: publish at once'),
    promote: bool = Query(False, description='with publish: make current'),
):
    snapshot, identity = await _load(request, snapshot_id)
    action = _transition_or_409(snapshot, 'pending')
    await require(request, current_user, action, identity=identity,
                  snapshot=snapshot)
    pending = await _change_status(request, current_user, snapshot, 'pending')
    if publish and await _can(request, current_user, 'publish', identity,
                              pending):
        pending = await _publish(request, current_user, pending, identity,
                                 promote=promote)
    return _ok(pending)


@router.post('/snapshots/{snapshot_id}/recall',
             summary='pending --> draft (author, 8.18)')
async def recall_snapshot(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
):
    snapshot, identity = await _load(request, snapshot_id)
    action = _transition_or_409(snapshot, 'draft')
    await require(request, current_user, action, identity=identity,
                  snapshot=snapshot)
    return _ok(await _change_status(request, current_user, snapshot, 'draft'))


@router.post('/snapshots/{snapshot_id}/resubmit',
             summary='rejected --> draft (author)')
async def resubmit_snapshot(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
):
    snapshot, identity = await _load(request, snapshot_id)
    action = _transition_or_409(snapshot, 'draft')
    await require(request, current_user, action, identity=identity,
                  snapshot=snapshot)
    _ensure_nothing_in_flight(await _snapshots_of(request, identity['_id']),
                              except_id=snapshot['_id'])
    return _ok(await _change_status(request, current_user, snapshot, 'draft'))


# MODERATION ------------------------------------------------------------------
@router.post('/snapshots/{snapshot_id}/publish',
             summary='pending --> published (moderator(D))')
async def publish_snapshot(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
    promote: bool = Query(False, description='also make it current'),
):
    snapshot, identity = await _load(request, snapshot_id)
    _transition_or_409(snapshot, 'published')
    return _ok(await _publish(request, current_user, snapshot, identity,
                              promote=promote))


@router.post('/snapshots/{snapshot_id}/reject',
             summary='pending --> rejected with a reason (moderator(D))')
async def reject_snapshot(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
    body: ReasonBody,
):
    snapshot, identity = await _load(request, snapshot_id)
    action = _transition_or_409(snapshot, 'rejected')
    await require(request, current_user, action, identity=identity,
                  snapshot=snapshot)
    return _ok(await _change_status(request, current_user, snapshot,
                                    'rejected', reason=body.reason))


@router.post('/snapshots/{snapshot_id}/promote',
             summary='Make a published snapshot current (moderator(D))')
async def promote_snapshot(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
):
    snapshot, identity = await _load(request, snapshot_id)
    await require(request, current_user, 'promote', identity=identity,
                  snapshot=snapshot)
    if snapshot.get('status') != 'published' or snapshot.get('superseded_by'):
        raise HTTPException(
            status_code=409,
            detail='Only a published, uncorrected snapshot becomes current.')
    await _set_current(request, identity['_id'], snapshot['_id'])
    return _ok(snapshot)


@router.post('/snapshots/{snapshot_id}/withdraw',
             summary='published --> withdrawn with a reason (moderator(D))')
async def withdraw_snapshot(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
    body: WithdrawBody,
):
    """The current snapshot falls back to ``replacement_id`` or the latest
    remaining live one, else null (section 3.1.4, 8.17)."""
    snapshot, identity = await _load(request, snapshot_id)
    action = _transition_or_409(snapshot, 'withdrawn')
    await require(request, current_user, action, identity=identity,
                  snapshot=snapshot)
    snapshots = await _snapshots_of(request, identity['_id'])
    remaining = [s for s in _live(snapshots) if s['_id'] != snapshot['_id']]
    replacement = None
    if body.replacement_id:
        replacement = next((s for s in remaining
                            if s['_id'] == body.replacement_id), None)
        if replacement is None:
            raise HTTPException(
                status_code=422,
                detail='replacement_id must be another published, '
                       'uncorrected snapshot of this component.')
    withdrawn = await _change_status(request, current_user, snapshot,
                                     'withdrawn', reason=body.reason)
    if identity.get('current_snapshot_id') == snapshot['_id'] or replacement:
        fallback = replacement or (remaining[-1] if remaining else None)
        await _set_current(request, identity['_id'],
                           fallback['_id'] if fallback else None)
    return _ok(withdrawn)


@router.post('/snapshots/{snapshot_id}/reinstate',
             summary='withdrawn --> published (moderator(D))')
async def reinstate_snapshot(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
):
    snapshot, identity = await _load(request, snapshot_id)
    action = _transition_or_409(snapshot, 'published')
    await require(request, current_user, action, identity=identity,
                  snapshot=snapshot)
    published = await _change_status(request, current_user, snapshot,
                                     'published')
    if not identity.get('current_snapshot_id') \
            and not published.get('superseded_by'):
        await _set_current(request, identity['_id'], published['_id'])
    return _ok(published)


# EDIT, DELETE ----------------------------------------------------------------
@router.patch('/snapshots/{snapshot_id}',
              summary='Edit a snapshot; per-field permission (8.3)')
async def patch_snapshot(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
    body: Annotated[Dict[str, Any], Body()],
):
    """
    Before publish: a draft --- author / moderator(D); a pending one ---
    moderator(D) (8.18); a rejected one --- nobody. After publish:
    moderator(D) for mutable metadata, valid time and overrides; frozen
    fields --> 409 pointing at /supersede; derived fields --> 422.
    """
    snapshot, identity = await _load(request, snapshot_id)
    viewer = viewer_of(current_user)
    projection, _ = await snapshot_projection(request, viewer, snapshot,
                                              identity)
    if projection != 'full':
        raise deny_read(viewer)
    dataset = await dataset_of(request, identity.get('dataset'))
    roles = dataset_roles(viewer, dataset)
    fields = {k: (list(v) if k == 'capture' and isinstance(v, dict) else [])
              for k, v in body.items()}
    problems = patch_problems(
        'snapshot', fields, status=snapshot.get('status'),
        is_author=current_user.id == snapshot.get('added_by_user_id'),
        is_moderator=viewer.is_admin or 'moderator' in roles)
    if problems.get('derived'):
        raise HTTPException(status_code=422, detail={
            'message': 'Server-maintained fields cannot be set.',
            'fields': problems['derived']})
    if problems.get('frozen'):
        raise HTTPException(status_code=409, detail={
            'message': 'Frozen on a published snapshot; record a correction '
                       '(POST /snapshots/{sid}/supersede).',
            'fields': problems['frozen']})
    if problems.get('forbidden'):
        raise deny_write(viewer, 'edit ' + ', '.join(problems['forbidden']))
    updated = {**snapshot}
    for key, value in body.items():
        if key == 'capture' and isinstance(value, dict) \
                and snapshot.get('status') in EVER_PUBLISHED:
            updated['capture'] = {**(snapshot.get('capture') or {}), **value}
        else:
            updated[key] = value
    for key in ('shape_class', 'complexity'):
        if key in body:
            updated[f'{key}_source'] = 'assigned' \
                if body[key] is not None else None
    if 'geometry' in body:
        _check_client_geometry(SnapshotDraftBody.model_validate(
            {'geometry': body['geometry']}))
    updated['lastmodified'] = now_iso()
    updated = _validated(updated)
    if 'effective_from' in body and snapshot.get('status') in EVER_PUBLISHED:
        _ensure_monotonic(updated,
                          await _snapshots_of(request, identity['_id']))
    await request.app.mongodb_component_snapshots.replace_one(
        {'_id': snapshot['_id']}, updated)
    return _ok(updated)


@router.delete('/snapshots/{snapshot_id}',
               summary='Delete a never-published snapshot (author or '
                       'moderator(D))')
async def delete_snapshot(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
):
    """Only draft / pending / rejected (I15); a published one is
    withdrawn instead. Files go with it."""
    snapshot, identity = await _load(request, snapshot_id)
    if snapshot.get('status') not in ('draft', 'pending', 'rejected'):
        # for everyone, admin included: published records are withdrawn
        raise HTTPException(
            status_code=409,
            detail='A published snapshot is never deleted; withdraw it '
                   '(I15).')
    await require(request, current_user, 'delete_record', identity=identity,
                  snapshot=snapshot)
    from .snapshots import _delete_snapshot_disk_assets  # avoid a cycle
    _delete_snapshot_disk_assets(request, snapshot_id)
    await request.app.mongodb_component_snapshots.delete_one(
        {'_id': snapshot_id, 'status': {'$in': ['draft', 'pending',
                                                'rejected']}})
    return JSONResponse(status_code=200, content={
        'ok': True, 'snapshot_id': snapshot_id,
        'identity_id': identity['_id']})
