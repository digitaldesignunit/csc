#!/usr/bin/env python3.9
from typing import Annotated

# THIRD PARTY MODULE IMPORTS --------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.catalogue.models import (  # NOQA
    User,
)
from .auth import get_current_active_user


# INIT ROUTER -----------------------------------------------------------------

# create router instance
router = APIRouter()


# FASTAPI DEPENDENCIES --------------------------------------------------------

async def get_components_col(request: Request):
    return request.app.mongodb_components


# RESERVATION ROUTES ----------------------------------------------------------

@router.post(
    '/reserve/{component_id}',
    summary='Reserve a component for the current user',
    status_code=status.HTTP_200_OK
)
async def reserve_component(
    component_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: Request,
):
    """
    Reserve a component for the current user.

    The component must not already be reserved by another user.
    Returns the updated component information.
    """
    coll = await get_components_col(request)

    try:
        # Check if component exists and get current reservation status
        component = await coll.find_one({'_id': component_id})
        if not component:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Component not found'
            )

        # Check if component is already reserved
        if component.get('reserved'):
            if component['reserved'] == current_user.id:
                # User already has this component reserved
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        'message': 'Component already reserved by you',
                        'component_id': component_id,
                        'reserved_by': current_user.id
                    }
                )
            else:
                # Component is reserved by another user
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail='Component is already reserved by another user'
                )

        # Reserve the component for the current user
        result = await coll.update_one(
            {'_id': component_id},
            {'$set': {'reserved': current_user.id}}
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Failed to reserve component'
            )

        # Return success response
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                'message': 'Component reserved successfully',
                'component_id': component_id,
                'reserved_by': current_user.id
            }
        )

    except PyMongoError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Database error: {str(e)}'
        )


@router.get(
    '/reserve/{user_identifier}',
    summary='List all components reserved by a user',
    response_model=list
)
async def get_user_reserved_components(
    user_identifier: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: Request,
):
    """
    Get all components reserved by a user.

    The user_identifier can be either:
    - A UUID (user ID)
    - A username

    Users can only see their own reserved components unless they are admin.
    """
    coll = await get_components_col(request)

    try:
        # Build query to find user by UUID or username
        user_query = {
            '$or': [
                {'_id': user_identifier},
                {'username': user_identifier}
            ]
        }

        # Get user information
        users_coll = request.app.mongodb_users
        user_doc = await users_coll.find_one(user_query)

        if not user_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='User not found'
            )

        user_id = user_doc['_id']
        username = user_doc.get('username', 'Unknown')

        # Check if current user can access this information
        # Users can only see their own reserved components unless they are
        # admin
        if current_user.id != user_id and current_user.role != 'admin':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='You can only view your own reserved components'
            )

        # Find all components reserved by this user
        reserved_components = []
        async for doc in coll.find({'reserved': user_id}):
            # Convert ObjectId to string for JSON serialization
            doc['_id'] = str(doc['_id'])
            reserved_components.append(doc)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                'user_id': user_id,
                'username': username,
                'reserved_count': len(reserved_components),
                'components': reserved_components
            }
        )

    except PyMongoError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Database error: {str(e)}'
        )


@router.delete(
    '/reserve/{component_id}',
    summary='Release a reserved component',
    status_code=status.HTTP_200_OK
)
async def release_component(
    component_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: Request,
):
    """
    Release a component reservation.

    Users can only release their own reservations.
    Admins can release any reservation.
    """
    coll = await get_components_col(request)

    try:
        # Check if component exists and get current reservation status
        component = await coll.find_one({'_id': component_id})
        if not component:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Component not found'
            )

        # Check if component is reserved
        if not component.get('reserved'):
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    'message': 'Component is not reserved',
                    'component_id': component_id
                }
            )

        # Check if current user can release this reservation
        if (current_user.id != component['reserved'] and
                current_user.role != 'admin'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=('You can only release your own reservations')
            )

        # Release the component
        result = await coll.update_one(
            {'_id': component_id},
            {'$unset': {'reserved': ''}}
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Failed to release component'
            )

        # Return success response
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                'message': 'Component released successfully',
                'component_id': component_id
            }
        )

    except PyMongoError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Database error: {str(e)}'
        )
