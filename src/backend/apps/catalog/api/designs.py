#!/usr/bin/env python3.9
from typing import List
import json
import hashlib

# THIRD PARTY MODULE IMPORTS --------------------------------------------------
from fastapi import (
    APIRouter, Depends, HTTPException, Request, status, Query
)
from typing import Annotated
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.catalog.models import (  # NOQA
    DesignModel,
    CreateDesignRequest,
    UpdateDesignModel,
    User,
)
from .auth import get_current_active_user
from utility import (
    generate_design_etag,
    generate_etag_for_designs,
    get_current_timestamp_z
)

# INIT ROUTER -----------------------------------------------------------------

# create router instance
router = APIRouter()


# FASTAPI DEPENDENCIES --------------------------------------------------------

async def get_designs_col(request: Request):
    return request.app.mongodb_designs


async def get_components_col(request: Request):
    return request.app.mongodb_components


async def get_users_col(request: Request):
    return request.app.mongodb_users


# HELPER FUNCTIONS ------------------------------------------------------------

def get_current_timestamp() -> str:
    """Deprecated; use get_current_timestamp_z from utility instead."""
    return get_current_timestamp_z()


def check_conditional_request(request: Request, etag: str) -> bool:
    """
    Check if request is a conditional request with If-None-Match header.

    Args:
        request: FastAPI request object
        etag: Current ETag of the resource

    Returns:
        True if resource hasn't changed (should return 304), False otherwise
    """
    if_none_match = request.headers.get('If-None-Match')
    if if_none_match and if_none_match == etag:
        return True
    return False


async def validate_component_ids(
    component_ids: List[str], components_col
) -> bool:
    """Validate that all component IDs exist in the database."""
    try:
        # Query using GUID strings directly (not ObjectIds)
        count = await components_col.count_documents(
            {"_id": {"$in": component_ids}}
        )
        return count == len(component_ids)
    except Exception:
        return False


async def enrich_design_with_creator(design: dict, users_col) -> dict:
    """Add creator username to design data."""
    try:
        if 'creator' in design and design['creator']:
            user = await users_col.find_one({"_id": design['creator']})
            if user:
                design['creator_username'] = user.get('username', 'Unknown')
            else:
                design['creator_username'] = 'Unknown'
        else:
            design['creator_username'] = 'Unknown'
    except Exception:
        design['creator_username'] = 'Unknown'

    return design


# DESIGN ROUTES ---------------------------------------------------------------

@router.get("/designs", response_model=List[dict])
async def get_designs(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    designs_col=Depends(get_designs_col),
    users_col=Depends(get_users_col),
):
    """Get all designs with pagination and ETag support."""
    try:
        # Calculate skip value for pagination
        skip = (page - 1) * size

        # Fetch designs from database
        cursor = designs_col.find({}).skip(skip).limit(size)
        designs = await cursor.to_list(length=size)

        # Convert ObjectId to string and enrich with creator info
        designs_clean = []
        for design in designs:
            design['_id'] = str(design['_id'])
            enriched_design = await enrich_design_with_creator(
                design, users_col)
            designs_clean.append(enriched_design)

        # Generate ETag for the design list
        etag = generate_etag_for_designs(designs_clean)

        # Check for conditional request
        if check_conditional_request(request, etag):
            return JSONResponse(
                status_code=304,
                content=None,
                headers={'ETag': etag}
            )

        # Return designs with ETag header
        return JSONResponse(
            status_code=200,
            content=designs_clean,
            headers={
                'ETag': etag,
                'Cache-Control': 'public, max-age=3600'  # 1 hour cache
            }
        )

    except PyMongoError as e:
        print(f'[ERROR] get_designs DB error: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )
    except Exception as e:
        print(f'[ERROR] get_designs: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )


@router.get("/designs/user/{user_id}", response_model=List[dict])
async def get_user_designs(
    request: Request,
    user_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    designs_col=Depends(get_designs_col),
    users_col=Depends(get_users_col),
):
    """Get designs by user ID with pagination and ETag support."""
    try:
        # Calculate skip value for pagination
        skip = (page - 1) * size

        # Fetch user's designs from database
        cursor = designs_col.find({"creator": user_id}).skip(skip).limit(
            size)
        designs = await cursor.to_list(length=size)

        # Convert ObjectId to string and enrich with creator info
        designs_clean = []
        for design in designs:
            design['_id'] = str(design['_id'])
            enriched_design = await enrich_design_with_creator(
                design, users_col)
            designs_clean.append(enriched_design)

        # Generate ETag for the design list
        etag = generate_etag_for_designs(designs_clean)

        # Check for conditional request
        if check_conditional_request(request, etag):
            return JSONResponse(
                status_code=304,
                content=None,
                headers={'ETag': etag}
            )

        # Return designs with ETag header
        return JSONResponse(
            status_code=200,
            content=designs_clean,
            headers={
                'ETag': etag,
                'Cache-Control': 'public, max-age=3600'  # 1 hour cache
            }
        )

    except PyMongoError as e:
        print(f'[ERROR] get_user_designs DB error: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )
    except Exception as e:
        print(f'[ERROR] get_user_designs: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )


@router.get("/designs/{design_id}", response_model=dict)
async def get_design(
    request: Request,
    design_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    designs_col=Depends(get_designs_col),
    users_col=Depends(get_users_col),
):
    """Get a single design by ID with ETag support."""
    try:
        design = await designs_col.find_one({"_id": design_id})

        if not design:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Design not found"
            )

        design['_id'] = str(design['_id'])
        enriched_design = await enrich_design_with_creator(design, users_col)

        # Generate ETag for the individual design
        etag = generate_design_etag(enriched_design)

        # Check for conditional request
        if check_conditional_request(request, etag):
            return JSONResponse(
                status_code=304,
                content=None,
                headers={'ETag': etag}
            )

        # Return design with ETag header
        return JSONResponse(
            status_code=200,
            content=enriched_design,
            headers={
                'ETag': etag,
                'Cache-Control': 'public, max-age=3600'  # 1 hour cache
            }
        )

    except PyMongoError as e:
        print(f'[ERROR] get_design DB error: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f'[ERROR] get_design: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )


@router.post("/designs", response_model=dict)
async def create_design(
    request: Request,
    design_data: CreateDesignRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    designs_col=Depends(get_designs_col),
    components_col=Depends(get_components_col),
    users_col=Depends(get_users_col),
):
    """Create a new design."""
    try:
        # Validate component IDs exist
        component_ids = [comp.component for comp in design_data.components]
        if not await validate_component_ids(component_ids, components_col):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more component IDs do not exist"
            )
        # Enforce limits for additional geometry
        additional_geometry = getattr(design_data, 'additional_geometry', [])
        if additional_geometry is None:
            additional_geometry = []
        if len(additional_geometry) > 25:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum of 25 additional geometries exceeded"
            )

        # Rough size check (approximate JSON size) for 10MB limit
        try:
            approx_size_bytes = len(
                json.dumps(
                    design_data.model_dump(
                        by_alias=True,
                        exclude_none=True
                    )
                )
            )
        except Exception:
            approx_size_bytes = 0
        if approx_size_bytes > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Design payload exceeds 10MB limit"
            )

        # Create design document (UUID provided by client)
        now = get_current_timestamp_z()
        design_doc = {
            "_id": design_data.id,
            "name": design_data.name,
            "description": design_data.description,
            "creator": current_user.id,
            "created": now,
            "lastmodified": now,
            "components": [
                comp.model_dump(
                    by_alias=True, exclude_none=True, exclude={'etag'}
                )
                for comp in design_data.components
            ],
            "additional_geometry": [
                item.model_dump(
                    by_alias=True, exclude_none=True, exclude={'etag'}
                )
                for item in additional_geometry
            ]
        }

        # Insert design
        await designs_col.insert_one(design_doc)

        # Fetch the created design
        created_design = await designs_col.find_one({"_id": design_data.id})
        created_design['_id'] = str(created_design['_id'])
        enriched_design = await enrich_design_with_creator(
            created_design, users_col
        )

        # Generate ETag for the new design
        etag = generate_design_etag(enriched_design)

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=enriched_design,
            headers={
                'ETag': etag,
                'Cache-Control': 'public, max-age=3600'
            }
        )

    except PyMongoError as e:
        print(f'[ERROR] create_design DB error: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f'[ERROR] create_design: {e}')
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Failed to create design'
        )


@router.patch("/designs/{design_id}", response_model=dict)
async def update_design(
    request: Request,
    design_id: str,
    design_data: UpdateDesignModel,
    current_user: Annotated[User, Depends(get_current_active_user)],
    designs_col=Depends(get_designs_col),
    components_col=Depends(get_components_col),
    users_col=Depends(get_users_col),
):
    """Update an existing design."""
    try:
        # Check if design exists and user owns it
        existing_design = await designs_col.find_one({"_id": design_id})
        if not existing_design:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Design not found"
            )

        if existing_design.get('creator') != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own designs"
            )

        # Validate component IDs if provided
        if design_data.components:
            component_ids = [comp.component for comp in design_data.components]
            if not await validate_component_ids(component_ids, components_col):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="One or more component IDs do not exist"
                )

        # Prepare update data
        update_data = {"lastmodified": get_current_timestamp_z()}

        if design_data.name is not None:
            update_data["name"] = design_data.name
        if design_data.description is not None:
            update_data["description"] = design_data.description
        if design_data.components is not None:
            update_data["components"] = [
                comp.model_dump(
                    by_alias=True, exclude_none=True, exclude={'etag'}
                )
                for comp in design_data.components
            ]
        if getattr(design_data, 'additional_geometry', None) is not None:
            ag = getattr(design_data, 'additional_geometry')
            if ag is None:
                ag = []
            if len(ag) > 25:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Maximum of 25 additional geometries exceeded"
                )
            # Approximate size check combining existing + update data
            try:
                prospective = dict(existing_design)
                prospective.update(update_data)
                prospective["additional_geometry"] = [
                    item.model_dump(
                        by_alias=True, exclude_none=True, exclude={'etag'}
                    )
                    for item in ag
                ]
                approx_size_bytes = len(json.dumps(prospective))
            except Exception:
                approx_size_bytes = 0
            if approx_size_bytes > 10 * 1024 * 1024:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Design payload exceeds 10MB limit"
                )
            update_data["additional_geometry"] = [
                item.model_dump(
                    by_alias=True, exclude_none=True, exclude={'etag'}
                )
                for item in ag
            ]

        # Update design
        await designs_col.update_one(
            {"_id": design_id},
            {"$set": update_data}
        )

        # Fetch the updated design
        updated_design = await designs_col.find_one({"_id": design_id})
        updated_design['_id'] = str(updated_design['_id'])
        enriched_design = await enrich_design_with_creator(
            updated_design, users_col
        )

        # Generate ETag for the updated design
        etag = generate_design_etag(enriched_design)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=enriched_design,
            headers={
                'ETag': etag,
                'Cache-Control': 'public, max-age=3600'
            }
        )

    except PyMongoError as e:
        print(f'[ERROR] update_design DB error: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f'[ERROR] update_design: {e}')
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Failed to update design'
        )


@router.delete("/designs/{design_id}")
async def delete_design(
    request: Request,
    design_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    designs_col=Depends(get_designs_col),
):
    """Delete a design."""
    try:
        # Check if design exists and user owns it
        existing_design = await designs_col.find_one({"_id": design_id})
        if not existing_design:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Design not found"
            )

        if existing_design.get('creator') != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete your own designs"
            )

        # Delete design
        await designs_col.delete_one({"_id": design_id})

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Design deleted successfully"}
        )

    except PyMongoError as e:
        print(f'[ERROR] delete_design DB error: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f'[ERROR] delete_design: {e}')
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Failed to delete design'
        )


@router.get('/schema/design', summary='Get DesignModel schema')
async def get_design_schema(request: Request):
    """Get the OpenAPI schema for DesignModel"""

    schema = DesignModel.model_json_schema()

    # Generate ETag for schema (hash of the schema content)
    schema_string = json.dumps(schema, sort_keys=True, separators=(',', ':'))
    etag = hashlib.md5(schema_string.encode('utf-8')).hexdigest()

    # Check for conditional request
    if check_conditional_request(request, etag):
        return JSONResponse(
            status_code=304,
            content=None,
            headers={'ETag': etag}
        )

    # Return schema with ETag header
    return JSONResponse(
        status_code=200,
        content=schema,
        headers={
            'ETag': etag,
            'Cache-Control': 'public, max-age=86400'  # 24 hour cache
        }
    )
