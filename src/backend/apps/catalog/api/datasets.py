#!/usr/bin/env python3.13
"""
Datasets, memberships and the caller's roles (data model spec section 3.6,
section 7.7; plan P3).

* ``GET /users/me`` --- the caller with the global role and the roles per
  dataset; the frontend shows controls from this (nothing role-related is
  in the session token besides the global role).
* ``GET /datasets`` --- the datasets the caller can see, with the caller's
  roles in each; ``GET /datasets/{did}`` adds the members for
  ``moderator(D)`` and admin.
* ``POST /datasets`` (admin), ``PATCH /datasets/{did}`` and
  ``PUT /datasets/{did}/members/{user_id}`` (``moderator(D)``).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Annotated, Any, Dict, List, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from pymongo.errors import DuplicateKeyError

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import Dataset
from apps.catalog.models import User
from apps.catalog.permissions import dataset_roles
from apps.catalog.vocab import DATASET_ROLES, DatasetRole, Visibility
from .access import load_datasets, require, viewer_of
from .auth import get_current_active_user, get_optional_current_user
from .catalog_common import now_iso

router = APIRouter()


# RESPONSES -------------------------------------------------------------------
class Membership(BaseModel):
    dataset: str
    name: str
    visibility: Visibility
    roles: List[DatasetRole]


class Me(BaseModel):
    id: str = Field(alias='_id')
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: str
    # datasets the caller holds roles in (admin: implicit, not listed)
    memberships: List[Membership]
    # slugs where the caller moderates; admin: every dataset
    moderated_datasets: List[str]

    model_config = {'populate_by_name': True}


class DatasetMemberView(BaseModel):
    user_id: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    roles: List[DatasetRole]
    added_at: Optional[str] = None


class DatasetView(BaseModel):
    id: str = Field(alias='_id')
    name: str
    description: Optional[str] = None
    visibility: Visibility
    # the caller's roles here (admin: every role)
    roles: List[DatasetRole]
    # moderator(D) and admin only
    members: Optional[List[DatasetMemberView]] = None

    model_config = {'populate_by_name': True}


class DatasetCreate(BaseModel):
    id: str = Field(alias='_id', description='slug, immutable')
    name: str = Field(min_length=1)
    description: Optional[str] = None
    visibility: Visibility = 'members'

    model_config = {'populate_by_name': True}


class DatasetPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    visibility: Optional[Visibility] = None


class MemberRoles(BaseModel):
    roles: List[DatasetRole] = Field(
        description='the full set of roles; empty removes the member')


def _ordered(roles) -> List[str]:
    return [r for r in DATASET_ROLES if r in roles]


async def _member_views(request: Request,
                        dataset: Dataset) -> List[DatasetMemberView]:
    ids = [m.user_id for m in dataset.members]
    users = {u['_id']: u for u in await request.app.mongodb_users.find(
        {'_id': {'$in': ids}},
        {'username': 1, 'full_name': 1, 'email': 1}).to_list(length=None)}
    return [DatasetMemberView(
        user_id=m.user_id,
        username=users.get(m.user_id, {}).get('username'),
        full_name=users.get(m.user_id, {}).get('full_name'),
        email=users.get(m.user_id, {}).get('email'),
        roles=_ordered(m.roles),
        added_at=m.added_at) for m in dataset.members]


async def _dataset_view(request: Request, user: Optional[User],
                        dataset: Dataset, *,
                        with_members: bool) -> DatasetView:
    roles = dataset_roles(viewer_of(user), dataset)
    members = None
    if with_members and 'moderator' in roles:
        members = await _member_views(request, dataset)
    return DatasetView(_id=dataset.id, name=dataset.name,
                       description=dataset.description,
                       visibility=dataset.visibility,
                       roles=_ordered(roles), members=members)


async def _dataset_or_404(request: Request, did: str) -> Dataset:
    dataset = (await load_datasets(request)).get(did)
    if dataset is None:
        raise HTTPException(status_code=404, detail=f'Dataset {did} not found')
    return dataset


# ROUTES ----------------------------------------------------------------------
@router.get('/users/me', response_model=Me, response_model_by_alias=True,
            summary='The caller, with the roles per dataset')
async def get_me(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    viewer = viewer_of(current_user)
    datasets = (await load_datasets(request)).values()
    memberships = [
        Membership(dataset=d.id, name=d.name, visibility=d.visibility,
                   roles=_ordered(d.roles_of(current_user.id)))
        for d in sorted(datasets, key=lambda d: d.id)
        if d.roles_of(current_user.id)]
    moderated = sorted(d.id for d in datasets
                       if 'moderator' in dataset_roles(viewer, d))
    return Me(_id=current_user.id, username=current_user.username,
              full_name=current_user.full_name, email=current_user.email,
              role=current_user.role, memberships=memberships,
              moderated_datasets=moderated)


@router.get('/datasets', response_model=List[DatasetView],
            response_model_by_alias=True, response_model_exclude_none=True,
            summary='Datasets the caller can see, with the caller\'s roles')
async def list_datasets(
    request: Request,
    current_user: Annotated[Optional[User],
                            Depends(get_optional_current_user)],
):
    """Admin: all. Signed in: member of, or ``catalog``. Anonymous: those
    holding public components (3.6)."""
    viewer = viewer_of(current_user)
    datasets = sorted((await load_datasets(request)).values(),
                      key=lambda d: d.id)
    if viewer.is_admin:
        shown = datasets
    elif viewer.logged_in:
        shown = [d for d in datasets if dataset_roles(viewer, d)
                 or d.visibility == 'catalog']
    else:
        public = set(await request.app.mongodb_component_identities.distinct(
            'dataset', {'is_public': True}))
        shown = [d for d in datasets if d.id in public]
    return [await _dataset_view(request, current_user, d, with_members=False)
            for d in shown]


@router.get('/datasets/{did}', response_model=DatasetView,
            response_model_by_alias=True, response_model_exclude_none=True,
            summary='One dataset; members for moderator(D) and admin')
async def get_dataset(
    request: Request,
    current_user: Annotated[Optional[User],
                            Depends(get_optional_current_user)],
    did: str,
):
    viewer = viewer_of(current_user)
    dataset = await _dataset_or_404(request, did)
    visible = viewer.is_admin or dataset_roles(viewer, dataset) or (
        viewer.logged_in and dataset.visibility == 'catalog')
    if not visible:
        raise HTTPException(
            status_code=401 if not viewer.logged_in else 403,
            detail='You have no access to this dataset.')
    return await _dataset_view(request, current_user, dataset,
                               with_members=True)


@router.post('/datasets', response_model=DatasetView, status_code=201,
             response_model_by_alias=True, response_model_exclude_none=True,
             summary='Create a dataset (admin)')
async def create_dataset(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: DatasetCreate,
):
    any_dataset = Dataset.model_validate({
        '_id': 'new', 'name': 'new', 'created': now_iso(),
        'lastmodified': now_iso()})
    await require(request, current_user, 'create_dataset',
                  dataset=any_dataset)
    now = now_iso()
    try:
        dataset = Dataset.model_validate({
            '_id': body.id, 'name': body.name,
            'description': body.description, 'visibility': body.visibility,
            'members': [], 'created': now, 'lastmodified': now})
    except ValidationError as exc:
        raise HTTPException(status_code=422,
                            detail=exc.errors()[0]['msg']) from exc
    try:
        await request.app.mongodb_datasets.insert_one(
            dataset.model_dump(by_alias=True, mode='json'))
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409,
                            detail=f'Dataset {body.id} exists') from exc
    return await _dataset_view(request, current_user, dataset,
                               with_members=True)


@router.patch('/datasets/{did}', response_model=DatasetView,
              response_model_by_alias=True, response_model_exclude_none=True,
              summary='Name, description, visibility (moderator(D))')
async def patch_dataset(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    did: str,
    body: DatasetPatch,
):
    dataset = await _dataset_or_404(request, did)
    await require(request, current_user, 'edit_dataset', dataset=dataset)
    changes: Dict[str, Any] = body.model_dump(exclude_unset=True)
    if 'name' in changes and changes['name'] is None:
        raise HTTPException(status_code=422, detail='name cannot be empty')
    if changes:
        changes['lastmodified'] = now_iso()
        await request.app.mongodb_datasets.update_one({'_id': did},
                                                      {'$set': changes})
        request.state.csc_datasets = None
    return await _dataset_view(request, current_user,
                               await _dataset_or_404(request, did),
                               with_members=True)


@router.put('/datasets/{did}/members/{user_id}', response_model=DatasetView,
            response_model_by_alias=True, response_model_exclude_none=True,
            summary='Set a member\'s roles; empty removes (moderator(D))')
async def put_dataset_member(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    did: str,
    user_id: str,
    body: MemberRoles,
):
    dataset = await _dataset_or_404(request, did)
    await require(request, current_user, 'manage_members', dataset=dataset)
    if await request.app.mongodb_users.find_one({'_id': user_id},
                                                {'_id': 1}) is None:
        raise HTTPException(status_code=404, detail='User not found')
    roles = _ordered(set(body.roles))
    members = [m.model_dump(mode='json') for m in dataset.members
               if m.user_id != user_id]
    existing = next((m for m in dataset.members if m.user_id == user_id),
                    None)
    if roles:
        members.append({
            'user_id': user_id, 'roles': roles,
            'added_by_user_id': (existing.added_by_user_id if existing
                                 else current_user.id),
            'added_at': existing.added_at if existing else now_iso()})
    await request.app.mongodb_datasets.update_one(
        {'_id': did}, {'$set': {'members': members,
                                'lastmodified': now_iso()}})
    request.state.csc_datasets = None
    return await _dataset_view(request, current_user,
                               await _dataset_or_404(request, did),
                               with_members=True)


# CODEGEN ---------------------------------------------------------------------
class AccessTypesEnvelope(BaseModel):
    """Codegen only: the types of the access, dataset, invitation and user
    routes (``/schema/access`` --> frontend ``AccessModels.ts``)."""
    me: Me
    dataset: DatasetView
    tombstone: 'Tombstone'
    invitation: 'InvitationView'
    invite_result: 'InviteResult'
    member_result: 'MemberByEmailResult'
    admin_user: 'AdminUserRow'
    user_hit: 'UserHit'


@router.get('/schema/access', include_in_schema=False)
async def get_access_json_schema():
    from apps.catalog.read_models import Tombstone
    from .invitations import (InvitationView, InviteResult,
                              MemberByEmailResult)
    from .users import AdminUserRow, UserHit
    AccessTypesEnvelope.model_rebuild(_types_namespace={
        'Tombstone': Tombstone, 'InvitationView': InvitationView,
        'InviteResult': InviteResult,
        'MemberByEmailResult': MemberByEmailResult,
        'AdminUserRow': AdminUserRow, 'UserHit': UserHit})
    return AccessTypesEnvelope.model_json_schema(by_alias=True)
