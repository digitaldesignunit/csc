#!/usr/bin/env python3.13

import re
from collections import defaultdict
from typing import Annotated, Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from pymongo.errors import PyMongoError

from apps.catalog.models import AdminUserUpdate, User, UserPublic
from apps.catalog.vocab import DATASET_ROLES, DatasetRole
from .access import load_datasets
from .auth import require_admin, users_coll

router = APIRouter()

_USER_LIST_PROJECTION = {
    '_id': 1,
    'username': 1,
    'email': 1,
    'full_name': 1,
    'disabled': 1,
    'role': 1,
    'email_verified': 1,
}


async def _count_active_admins(users) -> int:
    return await users.count_documents({
        'role': 'admin',
        'disabled': {'$ne': True},
    })


def _user_public(doc: dict) -> UserPublic:
    return UserPublic.model_validate(doc)


class MembershipRow(BaseModel):
    dataset: str
    roles: List[DatasetRole]


class AdminUserRow(UserPublic):
    """A row of the admin user list (8.21)."""
    memberships: List[MembershipRow] = Field(default_factory=list)
    invited: bool = False


class UserHit(BaseModel):
    id: str = Field(alias='_id')
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None

    model_config = {'populate_by_name': True}


def _memberships_by_user(datasets) -> Dict[str, List[MembershipRow]]:
    out: Dict[str, List[MembershipRow]] = defaultdict(list)
    for dataset in sorted(datasets, key=lambda d: d.id):
        for member in dataset.members:
            out[member.user_id].append(MembershipRow(
                dataset=dataset.id,
                roles=[r for r in DATASET_ROLES if r in member.roles]))
    return out


@router.get(
    '/users',
    response_model=List[AdminUserRow],
    response_model_by_alias=True,
    summary='User accounts with memberships, filterable (admin only)',
)
async def list_users(
    request: Request,
    _admin_user: Annotated[User, Depends(require_admin)],
    users=Depends(users_coll),
    q: Optional[str] = Query(None, description='text in username, name, '
                                               'email'),
    dataset: Optional[str] = Query(None, description='member of'),
    dataset_role: Optional[DatasetRole] = Query(
        None, description='holds this role (in `dataset`, else in any)'),
    no_dataset: bool = Query(False, description='member of no dataset'),
    role: Optional[Literal['user', 'admin']] = Query(None),
    state: Optional[Literal['enabled', 'disabled', 'unverified']] = Query(
        None),
    invited: bool = Query(False, description='registered by invitation'),
):
    """Filters combine (8.21); memberships come from ``datasets.members``,
    joined here in one pass."""
    match: Dict[str, Any] = {}
    if q:
        pattern = {'$regex': re.escape(q.strip()), '$options': 'i'}
        match['$or'] = [{'username': pattern}, {'full_name': pattern},
                        {'email': pattern}]
    if role:
        match['role'] = role
    if state == 'disabled':
        match['disabled'] = True
    elif state == 'enabled':
        match['disabled'] = {'$ne': True}
        match['email_verified'] = True
    elif state == 'unverified':
        match['email_verified'] = {'$ne': True}
    if invited:
        match['invitation_id'] = {'$nin': [None, '']}
    try:
        docs = await users.find(
            match, {**_USER_LIST_PROJECTION, 'invitation_id': 1}).sort(
            'username', 1).to_list(length=None)
    except PyMongoError as exc:
        print(f'[ERROR] list_users DB error: {exc}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )
    memberships = _memberships_by_user((await load_datasets(request)).values())
    rows: List[AdminUserRow] = []
    for doc in docs:
        mine = memberships.get(doc['_id'], [])
        if no_dataset and mine:
            continue
        if dataset and not any(m.dataset == dataset for m in mine):
            continue
        if dataset_role and not any(
                dataset_role in m.roles and (not dataset or m.dataset == dataset)
                for m in mine):
            continue
        rows.append(AdminUserRow.model_validate({
            **doc, 'memberships': mine,
            'invited': bool(doc.get('invitation_id'))}))
    return rows


@router.get(
    '/users/search',
    response_model=List[UserHit],
    response_model_by_alias=True,
    summary='Prefix search over username, name, email (admin; 8.20)',
)
async def search_users(
    _admin_user: Annotated[User, Depends(require_admin)],
    users=Depends(users_coll),
    q: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=50),
):
    pattern = {'$regex': '^' + re.escape(q.strip()), '$options': 'i'}
    docs = await users.find(
        {'$or': [{'username': pattern}, {'full_name': pattern},
                 {'email': pattern}]},
        {'_id': 1, 'username': 1, 'full_name': 1, 'email': 1}).sort(
        'username', 1).limit(limit).to_list(length=None)
    return [UserHit.model_validate(d) for d in docs]


@router.patch(
    '/users/{user_id}',
    response_model=UserPublic,
    summary='Update a user account (admin only)',
)
async def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    admin_user: Annotated[User, Depends(require_admin)],
    users=Depends(users_coll),
):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='No fields to update',
        )

    try:
        existing = await users.find_one({'_id': user_id}, _USER_LIST_PROJECTION)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='User not found',
            )

        is_self = user_id == admin_user.id
        target_is_admin = existing.get('role') == 'admin'
        target_is_active = existing.get('disabled') is not True

        if is_self:
            if updates.get('role') is not None and updates['role'] != 'admin':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='You cannot change your own admin role',
                )
            if updates.get('disabled') is True:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='You cannot disable your own account',
                )

        next_role = updates.get('role', existing.get('role', 'user'))
        next_disabled = updates.get('disabled', existing.get('disabled', False))

        demoting_admin = (
            target_is_admin
            and target_is_active
            and (next_role != 'admin' or next_disabled is True)
        )
        if demoting_admin:
            active_admins = await _count_active_admins(users)
            if active_admins <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Cannot remove or disable the last active admin',
                )

        result = await users.find_one_and_update(
            {'_id': user_id},
            {'$set': updates},
            projection=_USER_LIST_PROJECTION,
            return_document=True,
        )
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='User not found',
            )

        return _user_public(result)
    except HTTPException:
        raise
    except PyMongoError as exc:
        print(f'[ERROR] update_user DB error: {exc}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )
