#!/usr/bin/env python3.9
from datetime import datetime, timezone
from typing import List

# THIRD PARTY MODULE IMPORTS --------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from pymongo.errors import PyMongoError
from bson import ObjectId

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.catalogue.models import (  # NOQA
    DesignModel,
    CreateDesignRequest,
    UpdateDesignModel,
    DesignComponent,
    User,
)
from .auth import get_current_active_user


# INIT ROUTER -----------------------------------------------------------------

# create router instance
router = APIRouter()


# FASTAPI DEPENDENCIES --------------------------------------------------------

async def get_designs_col(request: Request):
    return request.app.mongodb_designs


async def get_components_col(request: Request):
    return request.app.mongodb_components


# HELPER FUNCTIONS ------------------------------------------------------------

def get_current_timestamp() -> str:
    """Get current ISO timestamp."""
    return datetime.now(timezone.utc).isoformat()


async def validate_component_ids(
    component_ids: List[str], components_col
) -> bool:
    """Validate that all component IDs exist in the database."""
    try:
        # Convert string IDs to ObjectId for MongoDB query
        object_ids = [ObjectId(cid) for cid in component_ids]

        # Count how many components exist with these IDs
        count = await components_col.count_documents(
            {"_id": {"$in": object_ids}}
        )

        return count == len(component_ids)
    except Exception:
        return False


async def enrich_design_with_creator(design: dict, users_col) -> dict:
    """Enrich design with creator username."""
    try:
        creator_id = design.get('creator')
        if creator_id:
            creator = await users_col.find_one(
                {"_id": ObjectId(creator_id)}
            )
            if creator:
                design['creator_username'] = creator.get(
                    'username', 'Unknown'
                )
            else:
                design['creator_username'] = 'Unknown'
        else:
            design['creator_username'] = 'Unknown'
    except Exception:
        design['creator_username'] = 'Unknown'

    return design


# API ROUTES ------------------------------------------------------------------

@router.get("/designs", response_model=List[dict])
async def get_designs(
    request: Request,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    designs_col=Depends(get_designs_col),
    users_col=Depends(lambda request: request.app.mongodb_users),
):
    """Get all designs (public gallery)."""
    try:
        skip = (page - 1) * size

        # Get designs with pagination
        cursor = designs_col.find().skip(skip).limit(size).sort(
            "lastmodified", -1
        )
        designs = await cursor.to_list(length=size)

        # Enrich with creator usernames
        enriched_designs = []
        for design in designs:
            design['_id'] = str(design['_id'])
            enriched_design = await enrich_design_with_creator(
                design, users_col
            )
            enriched_designs.append(enriched_design)

        return enriched_designs

    except PyMongoError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )


@router.get("/designs/user/{user_id}", response_model=List[dict])
async def get_user_designs(
    user_id: str,
    request: Request,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    designs_col=Depends(get_designs_col),
    users_col=Depends(lambda request: request.app.mongodb_users),
):
    """Get designs created by a specific user."""
    try:
        skip = (page - 1) * size

        # Get user's designs with pagination
        cursor = designs_col.find({"creator": user_id}).skip(skip).limit(
            size
        ).sort("lastmodified", -1)
        designs = await cursor.to_list(length=size)

        # Enrich with creator usernames
        enriched_designs = []
        for design in designs:
            design['_id'] = str(design['_id'])
            enriched_design = await enrich_design_with_creator(
                design, users_col
            )
            enriched_designs.append(enriched_design)

        return enriched_designs

    except PyMongoError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )


@router.get("/designs/{design_id}", response_model=dict)
async def get_design(
    design_id: str,
    request: Request,
    designs_col=Depends(get_designs_col),
    users_col=Depends(lambda request: request.app.mongodb_users),
):
    """Get a single design by ID."""
    try:
        design = await designs_col.find_one({"_id": ObjectId(design_id)})

        if not design:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Design not found"
            )

        design['_id'] = str(design['_id'])
        enriched_design = await enrich_design_with_creator(
            design, users_col
        )

        return enriched_design

    except PyMongoError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Design not found"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid design ID: {str(e)}"
        )


@router.post("/designs", response_model=dict)
async def create_design(
    design_data: CreateDesignRequest,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    designs_col=Depends(get_designs_col),
    components_col=Depends(get_components_col),
    users_col=Depends(lambda request: request.app.mongodb_users),
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

        # Create design document
        now = get_current_timestamp()
        design_doc = {
            "name": design_data.name,
            "description": design_data.description,
            "creator": current_user.id,
            "created": now,
            "lastmodified": now,
            "components": [comp.dict() for comp in design_data.components]
        }

        # Insert design
        result = await designs_col.insert_one(design_doc)
        design_id = str(result.inserted_id)

        # Fetch the created design
        created_design = await designs_col.find_one(
            {"_id": ObjectId(design_id)}
        )
        created_design['_id'] = str(created_design['_id'])
        enriched_design = await enrich_design_with_creator(
            created_design, users_col
        )

        return enriched_design

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
    design_id: str,
    design_data: UpdateDesignModel,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    designs_col=Depends(get_designs_col),
    components_col=Depends(get_components_col),
    users_col=Depends(lambda request: request.app.mongodb_users),
):
    """Update an existing design (owner only)."""
    try:
        # Check if design exists and user is owner
        design = await designs_col.find_one({"_id": ObjectId(design_id)})

        if not design:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Design not found"
            )

        if (design.get('creator') != current_user.id and
                current_user.role != 'admin'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this design"
            )

        # Validate component IDs if components are being updated
        if design_data.components is not None:
            component_ids = [comp.component for comp in design_data.components]
            if not await validate_component_ids(component_ids, components_col):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="One or more component IDs do not exist"
                )

        # Build update document
        update_doc = {"lastmodified": get_current_timestamp()}

        if design_data.name is not None:
            update_doc["name"] = design_data.name
        if design_data.description is not None:
            update_doc["description"] = design_data.description
        if design_data.components is not None:
            update_doc["components"] = [
                comp.dict() for comp in design_data.components
            ]

        # Update design
        await designs_col.update_one(
            {"_id": ObjectId(design_id)},
            {"$set": update_doc}
        )

        # Fetch updated design
        updated_design = await designs_col.find_one(
            {"_id": ObjectId(design_id)}
        )
        updated_design['_id'] = str(updated_design['_id'])
        enriched_design = await enrich_design_with_creator(
            updated_design, users_col
        )

        return enriched_design

    except PyMongoError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Design not found"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error updating design: {str(e)}"
        )


@router.delete("/designs/{design_id}")
async def delete_design(
    design_id: str,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    designs_col=Depends(get_designs_col),
):
    """Delete a design (owner only)."""
    try:
        # Check if design exists and user is owner
        design = await designs_col.find_one({"_id": ObjectId(design_id)})

        if not design:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Design not found"
            )

        if (design.get('creator') != current_user.id and
                current_user.role != 'admin'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this design"
            )

        # Delete design
        await designs_col.delete_one({"_id": ObjectId(design_id)})

        return {"message": "Design deleted successfully"}

    except PyMongoError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Design not found"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error deleting design: {str(e)}"
        )
