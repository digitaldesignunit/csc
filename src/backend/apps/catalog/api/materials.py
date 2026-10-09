#!/usr/bin/env python3.13
"""
The materials list (data model spec section 2.10, section 7.7, I25;
decisions 6.10, 8.35; plan P4).

* ``GET /materials`` --- public; retired and merged entries on request
* ``POST /materials`` --- admin; ``default_class`` required
* ``PATCH /materials/{mid}`` --- admin; a new ``default_class`` re-derives
  every derived ``material_class``
* ``DELETE /materials/{mid}`` --- admin, only while nothing references it
* ``POST /materials/{mid}/merge`` --- admin; moves every identity to the
  target and leaves an alias

Every identity a material change rewrites gets a change-log entry (8.36).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Annotated, Any, Dict, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import LowCode, Material, Slug
from apps.catalog.models import User
from apps.catalog.vocab import MaterialGroup
from .access import require
from .auth import get_current_active_user
from .catalog_common import now_iso
from .change_log import log_change

router = APIRouter()


class MaterialCreateBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: Slug = Field(alias='_id')
    label: str = Field(min_length=1)
    group: MaterialGroup
    default_class: LowCode
    uniclass: Optional[str] = None
    notes: Optional[str] = None


class MaterialPatchBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: Optional[str] = Field(None, min_length=1)
    group: Optional[MaterialGroup] = None
    default_class: Optional[LowCode] = None
    uniclass: Optional[str] = None
    notes: Optional[str] = None
    retired: Optional[bool] = None


class MergeBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    into: str


def _materials(request: Request):
    return request.app.mongodb_materials


def _validated(doc: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return Material.model_validate(doc).model_dump(by_alias=True,
                                                       mode='json')
    except ValidationError as exc:
        first = exc.errors()[0]
        raise HTTPException(status_code=422, detail=first['msg']) from exc


async def _load(request: Request, mid: str) -> Dict[str, Any]:
    doc = await _materials(request).find_one({'_id': mid})
    if doc is None:
        raise HTTPException(status_code=404, detail=f'Material {mid} not found')
    return doc


async def _rewrite_identities(request: Request, query: Dict[str, Any],
                              updates: Dict[str, Any], *, user: User,
                              cause: str, source: str) -> int:
    """Apply ``updates`` to every identity matching ``query``, one change-
    log entry each (8.36). Returns how many changed."""
    identities = request.app.mongodb_component_identities
    changed = 0
    async for before in identities.find(query):
        after = {**before, **updates}
        entry = await log_change(request, 'identity', before, after,
                                 by_user_id=user.id, cause=cause,
                                 source_record_id=source)
        if entry is None:
            continue
        await identities.update_one(
            {'_id': before['_id']},
            {'$set': {**updates, 'lastmodified': entry['at']}})
        changed += 1
    return changed


@router.get('/materials', summary='The controlled materials list (2.10)')
async def list_materials(
    request: Request,
    include_retired: bool = Query(False, description='also retired ones'),
    include_merged: bool = Query(False, description='also merged aliases'),
):
    query: Dict[str, Any] = {}
    if not include_merged:
        query['merged_into'] = None
    if not include_retired:
        query['retired'] = {'$ne': True}
    docs = await _materials(request).find(query).sort('label', 1).to_list(
        length=None)
    return JSONResponse(status_code=200, content=docs)


@router.post('/materials', status_code=201, summary='Add a material (admin)')
async def create_material(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: MaterialCreateBody,
):
    await require(request, current_user, 'manage_materials')
    if await _materials(request).find_one({'_id': body.id}, {'_id': 1}):
        raise HTTPException(status_code=409,
                            detail=f'Material {body.id} already exists')
    doc = _validated(body.model_dump(by_alias=True))
    await _materials(request).insert_one(dict(doc))
    return JSONResponse(status_code=201, content=doc)


@router.patch('/materials/{mid}', summary='Edit a material (admin)')
async def patch_material(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    mid: str,
    body: MaterialPatchBody,
):
    """``_id`` is immutable (a rename is a merge into a new id). A new
    ``default_class`` re-derives every derived ``material_class`` (I25)."""
    await require(request, current_user, 'manage_materials')
    before = await _load(request, mid)
    if before.get('merged_into'):
        raise HTTPException(status_code=409,
                            detail=f'{mid} is merged into '
                                   f'{before["merged_into"]}; edit that one.')
    after = _validated({**before, **body.model_dump(exclude_unset=True)})
    await _materials(request).replace_one({'_id': mid}, after)
    rederived = 0
    if after['default_class'] != before['default_class']:
        rederived = await _rewrite_identities(
            request, {'material': mid, 'material_class_source': 'derived'},
            {'material_class': after['default_class']},
            user=current_user, cause='patch', source=mid)
    return JSONResponse(status_code=200,
                        content={**after, 'identities_rederived': rederived})


@router.delete('/materials/{mid}', summary='Delete an unused material (admin)')
async def delete_material(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    mid: str,
):
    """Only while no identity references it, withdrawn ones included."""
    await require(request, current_user, 'manage_materials')
    await _load(request, mid)
    used = await request.app.mongodb_component_identities.count_documents(
        {'material': mid})
    if used:
        raise HTTPException(status_code=409,
                            detail=f'{used} component(s) use {mid}; merge it '
                                   f'into another material instead.')
    aliases = await _materials(request).count_documents({'merged_into': mid})
    if aliases:
        raise HTTPException(status_code=409,
                            detail=f'{aliases} merged material(s) point at '
                                   f'{mid}; it stays as their target.')
    await _materials(request).delete_one({'_id': mid})
    return JSONResponse(status_code=200, content={'ok': True, '_id': mid})


@router.post('/materials/{mid}/merge',
             summary='Merge a material into another (admin)')
async def merge_material(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    mid: str,
    body: MergeBody,
):
    """Every identity moves to the target; derived classes follow the
    target's default, assigned ones stay; ``mid`` remains as an alias
    ``{_id, merged_into}`` so old references resolve (8.35)."""
    await require(request, current_user, 'manage_materials')
    source = await _load(request, mid)
    target = await _load(request, body.into)
    if mid == body.into:
        raise HTTPException(status_code=422,
                            detail='A material cannot merge into itself.')
    if source.get('merged_into') or target.get('merged_into'):
        raise HTTPException(status_code=409,
                            detail='Merge only between materials that are '
                                   'not merged themselves.')
    moved = await _rewrite_identities(
        request, {'material': mid, 'material_class_source': 'derived'},
        {'material': body.into, 'material_class': target['default_class']},
        user=current_user, cause='material_merge', source=mid)
    moved += await _rewrite_identities(
        request, {'material': mid, 'material_class_source': 'assigned'},
        {'material': body.into},
        user=current_user, cause='material_merge', source=mid)
    await _materials(request).update_many(
        {'merged_into': mid}, {'$set': {'merged_into': body.into}})
    alias = {**source, 'merged_into': body.into, 'retired': True}
    await _materials(request).replace_one({'_id': mid}, alias)
    return JSONResponse(status_code=200, content={
        'ok': True, 'merged': mid, 'into': body.into,
        'identities_moved': moved, 'at': now_iso()})
