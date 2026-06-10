#!/usr/bin/env python3.9

from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import PyMongoError

from apps.catalog.models import AdminUserUpdate, User, UserPublic
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


@router.get(
    '/users',
    response_model=List[UserPublic],
    summary='List all user accounts (admin only)',
)
async def list_users(
    _admin_user: Annotated[User, Depends(require_admin)],
    users=Depends(users_coll),
):
    try:
        docs = await users.find({}, _USER_LIST_PROJECTION).sort(
            'username', 1
        ).to_list(length=None)
        return [_user_public(doc) for doc in docs]
    except PyMongoError as exc:
        print(f'[ERROR] list_users DB error: {exc}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )


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
