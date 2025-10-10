#!/usr/bin/env python3.9
import uuid
from datetime import datetime, timezone
from typing import List

# THIRD PARTY MODULE IMPORTS --------------------------------------------------
from fastapi import (
    APIRouter, Depends, HTTPException, Request, status, Query
)
from typing import Annotated
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.catalogue.models import (  # NOQA
    DesignModel,
    CreateDesignRequest,
    UpdateDesignModel,
    DesignComponent,
    User,
)
from .auth import get_current_active_user
from utility import (
    generate_design_etag,
    generate_etag_for_designs
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
    """Get current ISO timestamp."""
    return datetime.now(timezone.utc).isoformat()


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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching designs: {str(e)}"
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching user designs: {str(e)}"
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching design: {str(e)}"
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

        # Create design document with UUID
        now = get_current_timestamp()
        design_id = str(uuid.uuid4())
        design_doc = {
            "_id": design_id,
            "name": design_data.name,
            "description": design_data.description,
            "creator": current_user.id,
            "created": now,
            "lastmodified": now,
            "components": [comp.dict() for comp in design_data.components]
        }

        # Insert design
        await designs_col.insert_one(design_doc)

        # Fetch the created design
        created_design = await designs_col.find_one({"_id": design_id})
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error creating design: {str(e)}"
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
        update_data = {"lastmodified": get_current_timestamp()}

        if design_data.name is not None:
            update_data["name"] = design_data.name
        if design_data.description is not None:
            update_data["description"] = design_data.description
        if design_data.components is not None:
            update_data["components"] = [
                comp.dict() for comp in design_data.components]

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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error updating design: {str(e)}"
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error deleting design: {str(e)}"
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
