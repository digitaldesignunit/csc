#!/usr/bin/env python3.13
"""
Withdrawal, deletion and purge of whole components, and the permanent
identifier resolver (data model spec section 3.1.4, section 3.1.5,
section 7.5, I19; decisions 6.4, 6.9, 8.11, 8.17; plan P3).

* ``POST /identities/{id}/withdraw`` / ``reinstate`` --- ``moderator(D)``
* ``DELETE /identities/{id}`` --- never-published only (author or
  ``moderator(D)``); ``?purge=1`` --- admin, anything, leaves a 410 stub
* ``DELETE /snapshots/{sid}?purge=1`` --- admin (lifecycle module handles
  the ordinary delete)
* ``GET /id/{uuid}`` --- permanent: redirects to the component page
  (HTML) or the passport (JSON); a duplicate 301s to its canonical piece
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os
from typing import Annotated, List, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.models import User
from .access import (
    component_visible,
    identity_ever_published,
    load_identity,
    raise_if_purged,
    require,
    viewer_of,
)
from .auth import get_current_active_user, get_optional_current_user
from .catalog_common import now_iso, validate_uuid

router = APIRouter()


class WithdrawIdentityBody(BaseModel):
    reason: str = Field(min_length=1)
    duplicate_of: Optional[str] = Field(
        None, description='the canonical piece this one duplicates')


class PurgeBody(BaseModel):
    confirm_id: str = Field(description='repeat the id being purged')
    reason: str = Field(min_length=1)


def _snapshot_files(request: Request, snapshot_id: str) -> None:
    from .snapshots import _delete_snapshot_disk_assets  # avoid a cycle
    _delete_snapshot_disk_assets(request, snapshot_id)
    capture = getattr(request.app, 'snapshot_capture_dir', None)
    if capture:
        import shutil
        shutil.rmtree(os.path.join(capture, snapshot_id),
                      ignore_errors=True)


async def _stubs(request: Request, user: User, ids: List[str],
                 reason: str) -> None:
    """What remains of purged ids: every GET on them answers 410."""
    now = now_iso()
    if ids:
        await request.app.mongodb_purged_records.insert_many([
            {'_id': i, 'purged_at': now, 'purged_by_user_id': user.id,
             'reason': reason} for i in ids])


async def _referenced_by(request: Request, identity_id: str) -> List[int]:
    """Catalog numbers of pieces naming this one as parent or duplicate."""
    docs = await request.app.mongodb_component_identities.find(
        {'$or': [{'parent_identities': identity_id},
                 {'withdrawn.duplicate_of': identity_id}],
         '_id': {'$ne': identity_id}},
        {'catalog_number': 1}).to_list(length=None)
    return sorted(d.get('catalog_number') or 0 for d in docs)


# WITHDRAW / REINSTATE --------------------------------------------------------
@router.post('/identities/{identity_id}/withdraw',
             summary='Withdraw a published component (moderator(D))')
async def withdraw_identity(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    identity_id: str,
    body: WithdrawIdentityBody,
):
    """
    Hidden everywhere by default; members of D see it in full, everyone
    else who could see it a tombstone (8.17). With ``duplicate_of`` the
    resolver and the component page lead to the canonical piece; pieces
    that named this one as their canonical piece follow along (I19).
    """
    validate_uuid(identity_id, label='identity id')
    identity = await load_identity(request, identity_id)
    await require(request, current_user, 'withdraw_identity',
                  identity=identity)
    if identity.get('withdrawn'):
        raise HTTPException(status_code=409, detail='Already withdrawn.')
    if not await identity_ever_published(request, identity):
        raise HTTPException(
            status_code=409,
            detail='Never published: delete it instead (section 3.1.4).')
    duplicate_of = body.duplicate_of
    if duplicate_of is not None:
        validate_uuid(duplicate_of, label='duplicate_of')
        target = await request.app.mongodb_component_identities.find_one(
            {'_id': duplicate_of}, {'withdrawn': 1})
        if duplicate_of == identity_id or target is None:
            raise HTTPException(status_code=422,
                                detail='duplicate_of names another, '
                                       'existing component.')
        if target.get('withdrawn'):
            raise HTTPException(
                status_code=422,
                detail='duplicate_of is withdrawn itself; name the piece it '
                       'leads to (I19).')
    followers = await request.app.mongodb_component_identities.count_documents(
        {'withdrawn.duplicate_of': identity_id})
    if followers and duplicate_of is None:
        raise HTTPException(
            status_code=409,
            detail=f'{followers} withdrawn piece(s) name this one as their '
                   f'canonical piece; give duplicate_of so they follow '
                   f'(I19).')
    now = now_iso()
    await request.app.mongodb_component_identities.update_one(
        {'_id': identity_id},
        {'$set': {'withdrawn': {'at': now, 'by_user_id': current_user.id,
                                'reason': body.reason,
                                'duplicate_of': duplicate_of},
                  'reserved': '', 'lastmodified': now}})
    if followers:
        await request.app.mongodb_component_identities.update_many(
            {'withdrawn.duplicate_of': identity_id},
            {'$set': {'withdrawn.duplicate_of': duplicate_of,
                      'lastmodified': now}})
    return JSONResponse(status_code=200, content={
        'ok': True, 'identity_id': identity_id, 'withdrawn_at': now,
        'duplicate_of': duplicate_of, 'followers_repointed': followers})


@router.post('/identities/{identity_id}/reinstate',
             summary='Reinstate a withdrawn component (moderator(D))')
async def reinstate_identity(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    identity_id: str,
):
    validate_uuid(identity_id, label='identity id')
    identity = await load_identity(request, identity_id)
    await require(request, current_user, 'reinstate_identity',
                  identity=identity)
    if not identity.get('withdrawn'):
        raise HTTPException(status_code=409, detail='Not withdrawn.')
    await request.app.mongodb_component_identities.update_one(
        {'_id': identity_id},
        {'$set': {'withdrawn': None, 'lastmodified': now_iso()}})
    return JSONResponse(status_code=200, content={
        'ok': True, 'identity_id': identity_id})


# DELETE / PURGE --------------------------------------------------------------
@router.delete('/identities/{identity_id}',
               summary='Delete a never-published component; ?purge=1: admin')
async def delete_identity(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    identity_id: str,
    purge: bool = Query(False),
    body: Optional[PurgeBody] = None,
):
    """
    Without ``purge``: only while nothing of it was ever published (I19),
    by its creator or moderator(D); snapshots and files go with it.
    ``?purge=1`` (admin; the body repeats the id and gives a reason):
    anything, evidence included, leaving 410 stubs for every id.
    """
    validate_uuid(identity_id, label='identity id')
    identity = await load_identity(request, identity_id)
    db = request.app
    if purge:
        await require(request, current_user, 'purge', identity=identity)
        if body is None or body.confirm_id != identity_id:
            raise HTTPException(status_code=422,
                                detail='Purge: repeat the id in confirm_id '
                                       'and give a reason.')
        reason = body.reason
    else:
        if await identity_ever_published(request, identity):
            raise HTTPException(
                status_code=409,
                detail='Published once: withdraw it instead; nothing '
                       'published is deleted (section 3.1.4).')
        await require(request, current_user, 'delete_identity',
                      identity=identity)
        reason = None
    referenced = await _referenced_by(request, identity_id)
    if referenced:
        raise HTTPException(
            status_code=409,
            detail=f'Other pieces name this one (catalog numbers '
                   f'{referenced}); resolve those links first.')
    snapshots = await db.mongodb_component_snapshots.find(
        {'identity_id': identity_id}, {'_id': 1}).to_list(length=None)
    evidence = await db.mongodb_component_evidence.find(
        {'identity_id': identity_id}, {'_id': 1}).to_list(length=None)
    if evidence and not purge:
        raise HTTPException(status_code=409,
                            detail='It has evidence records; delete those '
                                   'first.')
    for snap in snapshots:
        _snapshot_files(request, snap['_id'])
    await db.mongodb_component_snapshots.delete_many(
        {'identity_id': identity_id})
    await db.mongodb_component_evidence.delete_many(
        {'identity_id': identity_id})
    await db.mongodb_component_identities.delete_one({'_id': identity_id})
    if purge:
        await _stubs(request, current_user,
                     [identity_id, *(s['_id'] for s in snapshots),
                      *(e['_id'] for e in evidence)], reason)
    return JSONResponse(status_code=200, content={
        'ok': True, 'identity_id': identity_id, 'purged': purge,
        'snapshots': len(snapshots), 'evidence': len(evidence)})


async def purge_snapshot_record(request: Request, user: User,
                                snapshot: dict, identity: dict,
                                body: Optional[PurgeBody]) -> JSONResponse:
    """``DELETE /snapshots/{sid}?purge=1`` (admin): hard delete incl. files,
    whatever the status; a 410 stub remains (section 3.1.4). The current
    snapshot cannot be purged --- promote another or withdraw it first."""
    await require(request, user, 'purge', identity=identity,
                  snapshot=snapshot)
    if body is None or body.confirm_id != snapshot['_id']:
        raise HTTPException(status_code=422,
                            detail='Purge: repeat the id in confirm_id and '
                                   'give a reason.')
    if identity.get('current_snapshot_id') == snapshot['_id']:
        raise HTTPException(status_code=409,
                            detail='The current snapshot: promote another or '
                                   'withdraw it first.')
    _snapshot_files(request, snapshot['_id'])
    await request.app.mongodb_component_snapshots.delete_one(
        {'_id': snapshot['_id']})
    await request.app.mongodb_component_snapshots.update_many(
        {'superseded_by': snapshot['_id']}, {'$set': {'superseded_by': None}})
    await _stubs(request, user, [snapshot['_id']], body.reason)
    return JSONResponse(status_code=200, content={
        'ok': True, 'snapshot_id': snapshot['_id'], 'purged': True})


# RESOLVER (section 7.5) ------------------------------------------------------
def _frontend_url() -> str:
    return (os.getenv('FRONTEND_URL') or '').rstrip('/')


@router.get('/id/{uuid}', summary='Permanent identifier resolver')
async def resolve_id(
    request: Request,
    current_user: Annotated[Optional[User],
                            Depends(get_optional_current_user)],
    uuid: str,
):
    """
    ``Accept: text/html`` --> 302 to the component page; otherwise 302 to
    the passport. A withdrawn duplicate --> 301 to ``/id/{duplicate_of}``;
    other withdrawn pieces and pieces without a current state still
    redirect (the page shows the tombstone / "no current state"); purged
    --> 410; unknown or never published (unless the caller may see it)
    --> 404. Visibility applies after the redirect (8.11).
    """
    validate_uuid(uuid, label='id')
    doc = await request.app.mongodb_component_identities.find_one(
        {'_id': uuid}, {'withdrawn': 1, 'current_snapshot_id': 1,
                        'dataset': 1, 'is_public': 1,
                        'created_by_user_id': 1, 'catalog_number': 1})
    if doc is None:
        await raise_if_purged(request, uuid, 'Component')
    withdrawn = doc.get('withdrawn') or {}
    if withdrawn.get('duplicate_of'):
        return RedirectResponse(f'/id/{withdrawn["duplicate_of"]}',
                                status_code=301)
    if not await identity_ever_published(request, doc) and \
            not await component_visible(request, viewer_of(current_user),
                                        doc):
        raise HTTPException(status_code=404,
                            detail=f'Component {uuid} not found')
    if 'text/html' in (request.headers.get('accept') or ''):
        return RedirectResponse(f'{_frontend_url()}/components/{uuid}',
                                status_code=302)
    # JSON: withdrawn pieces answer with the tombstone there (8.17)
    return RedirectResponse(f'/identities/{uuid}/compose', status_code=302)
