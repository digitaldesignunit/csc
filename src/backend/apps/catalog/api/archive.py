#!/usr/bin/env python3.9
"""
Archive API routes for archiving and restoring components.

Archived components are moved from the 'components' collection to the
'components_archived' collection, and their geometry files are moved
from the main geometry directory to the archive geometry directory.
"""

import os
import shutil
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query, status
from fastapi.responses import JSONResponse, FileResponse
from pymongo.errors import PyMongoError

from apps.catalog.models import ComponentCount, ComponentModel, User
from .auth import require_admin
from .components import build_component_match_stage
from utility.utility import (
    generate_geometry_etag,
    check_geometry_conditional_request,
    validate_component_id,
    ensure_file,
)


# INIT ROUTER -----------------------------------------------------------------

router = APIRouter()


# FASTAPI DEPENDENCIES --------------------------------------------------------

async def get_components_col(request: Request):
    return request.app.mongodb_components


async def get_archived_components_col(request: Request):
    return request.app.mongodb_components_archived


# HELPER FUNCTIONS ------------------------------------------------------------

async def get_archived_components_with_aggregation(
    request: Request,
    match_stage: dict,
    projection: Optional[dict] = None,
    sortkey: str = '_id',
    sort_order: int = 1,
    page: int = 0,
    size: int = 0,
) -> list:
    """
    Retrieve archived components using aggregation pipeline.
    Similar to get_components_with_aggregation but for archived collection.
    """
    coll = await get_archived_components_col(request)

    # Build aggregation pipeline
    pipeline: list = [{'$match': match_stage}]

    # Add projection if specified
    if projection:
        pipeline.append({'$project': projection})

    # Add sorting
    pipeline.append({'$sort': {sortkey: sort_order}})

    # Add pagination if needed
    if page > 0 and size > 0:
        pipeline.append({'$skip': (page - 1) * size})
        pipeline.append({'$limit': size})
    elif page == 0 and size > 0:
        pipeline.append({'$limit': size})

    # Convert ObjectId to string for JSON serialization
    pipeline.append({
        '$addFields': {
            '_id': {'$toString': '$_id'}
        }
    })

    # Execute aggregation
    cursor = await coll.aggregate(pipeline)
    components = [doc async for doc in cursor]

    return components


# ARCHIVE/UNARCHIVE ROUTES ----------------------------------------------------

@router.post(
    '/archive/{component_id}',
    summary='Archive a component (admin only)'
)
async def archive_component(
    request: Request,
    component_id: str,
    admin_user: Annotated[User, Depends(require_admin)],
):
    """
    Archive a component (move from 'components' to 'components_archived').

    This operation:
    1. Releases any existing reservation on the component
    2. Copies the component document to 'components_archived' collection
    3. Moves the geometry folder to the archive directory
    4. Deletes the component from the main 'components' collection

    Note: Preview images are kept in place for display in archive.
    """
    validate_component_id(component_id)
    components_coll = await get_components_col(request)
    archived_coll = await get_archived_components_col(request)

    try:
        # Check if component exists in main collection
        component = await components_coll.find_one({'_id': component_id})
        if not component:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Component not found'
            )

        # Check if already archived
        existing_archived = await archived_coll.find_one({'_id': component_id})
        if existing_archived:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Component is already archived'
            )

        # Release reservation if any (clear the reserved field)
        if component.get('reserved'):
            component['reserved'] = ''

        # Insert into archived collection
        await archived_coll.insert_one(component)

        # Move geometry folder from main to archive directory
        geometry_base_dir = request.app.component_geometry_dir
        geometry_archive_dir = request.app.component_geometry_archive_dir
        source_dir = os.path.join(geometry_base_dir, component_id)
        dest_dir = os.path.join(geometry_archive_dir, component_id)

        if os.path.exists(source_dir):
            # Create archive directory if it doesn't exist
            os.makedirs(geometry_archive_dir, exist_ok=True)
            try:
                shutil.move(source_dir, dest_dir)
            except Exception as e:
                # If geometry move fails, rollback the database changes
                await archived_coll.delete_one({'_id': component_id})
                print(f'[ERROR] archive_component geometry move: {e}')
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail='Failed to move geometry folder'
                )

        # Delete from main collection
        await components_coll.delete_one({'_id': component_id})

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                'message': 'Component archived successfully',
                'component_id': component_id
            }
        )

    except HTTPException:
        raise
    except PyMongoError as e:
        print(f'[ERROR] archive_component DB error: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )
    except Exception as e:
        print(f'[ERROR] archive_component: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )


@router.post(
    '/unarchive/{component_id}',
    summary='Restore a component from archive (admin only)'
)
async def unarchive_component(
    request: Request,
    component_id: str,
    admin_user: Annotated[User, Depends(require_admin)],
):
    """
    Restore a component from archive to the main collection.

    This operation:
    1. Copies the component document from 'components_archived' to 'components'
    2. Moves the geometry folder from archive to main directory
    3. Deletes the component from 'components_archived' collection

    The component retains its original validation status.
    """
    validate_component_id(component_id)
    components_coll = await get_components_col(request)
    archived_coll = await get_archived_components_col(request)

    try:
        # Check if component exists in archived collection
        component = await archived_coll.find_one({'_id': component_id})
        if not component:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Archived component not found'
            )

        # Check if component already exists in main collection
        existing_component = await components_coll.find_one(
            {'_id': component_id}
        )
        if existing_component:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Component already exists in main collection'
            )

        # Insert into main collection
        await components_coll.insert_one(component)

        # Move geometry folder from archive to main directory
        geometry_base_dir = request.app.component_geometry_dir
        geometry_archive_dir = request.app.component_geometry_archive_dir
        source_dir = os.path.join(geometry_archive_dir, component_id)
        dest_dir = os.path.join(geometry_base_dir, component_id)

        if os.path.exists(source_dir):
            try:
                shutil.move(source_dir, dest_dir)
            except Exception as e:
                # If geometry move fails, rollback the database changes
                await components_coll.delete_one({'_id': component_id})
                print(f'[ERROR] unarchive_component geometry move: {e}')
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail='Failed to move geometry folder'
                )

        # Delete from archived collection
        await archived_coll.delete_one({'_id': component_id})

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                'message': 'Component restored successfully',
                'component_id': component_id
            }
        )

    except HTTPException:
        raise
    except PyMongoError as e:
        print(f'[ERROR] unarchive_component DB error: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )
    except Exception as e:
        print(f'[ERROR] unarchive_component: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )


# ARCHIVED COMPONENT LISTING ROUTES -------------------------------------------

@router.get(
    '/archived/componentcount',
    summary='Count archived components (admin only)',
    response_model=ComponentCount
)
async def count_archived_components(
    request: Request,
    admin_user: Annotated[User, Depends(require_admin)],
    comptype: Optional[str] = Query(None, description='Component type filter'),
    material: Optional[str] = Query(None, description='Material type filter'),
    dataset: Optional[str] = Query(None, description='Dataset name filter'),
    validated: int = Query(0, description='1=true, -1=false, 0/other=any'),
    complexity: Optional[int] = Query(None, description='Complexity (0-3)'),
    fragment: Optional[bool] = Query(None, description='Is fragment'),
    bbx_min_x: Optional[float] = Query(None, description='Min X'),
    bbx_min_y: Optional[float] = Query(None, description='Min Y'),
    bbx_min_z: Optional[float] = Query(None, description='Min Z'),
    bbx_max_x: Optional[float] = Query(None, description='Max X'),
    bbx_max_y: Optional[float] = Query(None, description='Max Y'),
    bbx_max_z: Optional[float] = Query(None, description='Max Z'),
):
    """Count archived components with optional filtering."""
    coll = await get_archived_components_col(request)

    query: dict = {}
    if comptype:
        query['type'] = {'$regex': f'^{comptype}$', '$options': 'i'}
    if material:
        query['material'] = {'$regex': f'^{material}$', '$options': 'i'}
    if dataset:
        query['dataset'] = {'$regex': f'^{dataset}$', '$options': 'i'}
    if validated == 1:
        query['validated'] = True
    elif validated == -1:
        query['validated'] = False

    if complexity is not None:
        query['complexity'] = complexity

    if fragment is not None:
        query['fragment'] = fragment

    # Add bounding box filters
    if any([bbx_min_x, bbx_min_y, bbx_min_z, bbx_max_x, bbx_max_y, bbx_max_z]):
        if bbx_min_x is not None or bbx_max_x is not None:
            bbx_query = {}
            if bbx_min_x is not None:
                bbx_query['$gte'] = bbx_min_x
            if bbx_max_x is not None:
                bbx_query['$lte'] = bbx_max_x
            if bbx_query:
                query['bbx.0'] = bbx_query

        if bbx_min_y is not None or bbx_max_y is not None:
            bbx_query = {}
            if bbx_min_y is not None:
                bbx_query['$gte'] = bbx_min_y
            if bbx_max_y is not None:
                bbx_query['$lte'] = bbx_max_y
            if bbx_query:
                query['bbx.1'] = bbx_query

        if bbx_min_z is not None or bbx_max_z is not None:
            bbx_query = {}
            if bbx_min_z is not None:
                bbx_query['$gte'] = bbx_min_z
            if bbx_max_z is not None:
                bbx_query['$lte'] = bbx_max_z
            if bbx_query:
                query['bbx.2'] = bbx_query

    count = await coll.count_documents(query)
    return ComponentCount(count=count)


@router.get(
    '/archived/shallowcomponents',
    summary='List archived components shallow (admin only)'
)
async def get_archived_components_shallow(
    request: Request,
    admin_user: Annotated[User, Depends(require_admin)],
    page: int = Query(0, description='Page number (0=get all, 1+=paginated)'),
    size: int = Query(0, description='Page size (0=get all)'),
    sortkey: str = Query('_id', description='Sort key'),
    comptype: str = Query('', description='Component type filter'),
    material: str = Query('', description='Material type filter'),
    dataset: str = Query('', description='Dataset name filter'),
    validated: int = Query(0, description='1=true, -1=false, 0/other=any'),
    complexity: Optional[int] = Query(None, description='Complexity (0-3)'),
    fragment: Optional[bool] = Query(None, description='Is fragment'),
    bbx_min_x: Optional[float] = Query(None, description='Min X'),
    bbx_min_y: Optional[float] = Query(None, description='Min Y'),
    bbx_min_z: Optional[float] = Query(None, description='Min Z'),
    bbx_max_x: Optional[float] = Query(None, description='Max X'),
    bbx_max_y: Optional[float] = Query(None, description='Max Y'),
    bbx_max_z: Optional[float] = Query(None, description='Max Z'),
):
    """List archived components without geometry/descriptors fields."""
    match_stage = build_component_match_stage(
        comptype=comptype,
        material=material,
        dataset=dataset,
        validated=validated,
        complexity=complexity,
        fragment=fragment,
        bbx_min_x=bbx_min_x,
        bbx_min_y=bbx_min_y,
        bbx_min_z=bbx_min_z,
        bbx_max_x=bbx_max_x,
        bbx_max_y=bbx_max_y,
        bbx_max_z=bbx_max_z,
    )
    components = await get_archived_components_with_aggregation(
        request,
        match_stage,
        projection={'geometry': 0, 'descriptors': 0},
        sortkey=sortkey,
        sort_order=1,
        page=page,
        size=size,
    )
    return JSONResponse(status_code=200, content=components)


# ARCHIVED COMPONENT DETAIL ROUTES --------------------------------------------

@router.get(
    '/archived/components/{component_id}',
    summary='Get archived component by ID (admin only)'
)
async def get_archived_component(
    request: Request,
    component_id: str,
    admin_user: Annotated[User, Depends(require_admin)],
):
    """Retrieve a single archived component with full data."""
    coll = await get_archived_components_col(request)

    component = await coll.find_one({'_id': component_id})
    if not component:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Archived component not found'
        )

    # Parse through ComponentModel to apply exclude_none configuration
    try:
        component_model = ComponentModel(**component)
        component_clean = component_model.model_dump(
            by_alias=True,
            exclude_none=True,
            exclude={'etag'}
        )
        return JSONResponse(status_code=200, content=component_clean)
    except Exception:
        # If model parsing fails, return raw document
        return JSONResponse(status_code=200, content=component)


@router.get(
    '/archived/shallowcomponents/{component_id}',
    summary='Get archived shallow component by ID (admin only)'
)
async def get_archived_shallow_component(
    request: Request,
    component_id: str,
    admin_user: Annotated[User, Depends(require_admin)],
):
    """Retrieve a single archived component without geometry/descriptors."""
    coll = await get_archived_components_col(request)

    projection = {'geometry': 0, 'descriptors': 0}
    doc = await coll.find_one({'_id': component_id}, projection)
    if not doc:
        raise HTTPException(404, 'Not found')
    return JSONResponse(status_code=200, content=doc)


# ARCHIVED GEOMETRY ROUTES ----------------------------------------------------

@router.get(
    '/archived/components/{component_id}/geometry_detailed',
    summary='Get archived component detailed geometry (admin only)'
)
async def get_archived_component_geometry_detailed(
    request: Request,
    component_id: str,
    admin_user: Annotated[User, Depends(require_admin)],
):
    """Retrieve the detailed OBJ mesh for an archived component."""
    validate_component_id(component_id)
    base = request.app.component_geometry_archive_dir
    mesh_path = os.path.join(base, component_id, 'mesh.obj')

    # Generate ETag for the file
    etag = generate_geometry_etag(mesh_path, component_id)

    # Check for conditional request
    if check_geometry_conditional_request(request, etag):
        from fastapi import Response
        return Response(
            status_code=304,
            headers={'ETag': etag}
        )

    return FileResponse(
        ensure_file(mesh_path),
        media_type='text/x-obj',
        filename='mesh.obj',
        headers={'ETag': etag, 'Cache-Control': 'private, max-age=3600'}
    )


@router.get(
    '/archived/components/{component_id}/geometry_reduced',
    summary='Get archived component reduced geometry (admin only)'
)
async def get_archived_component_geometry_reduced(
    request: Request,
    component_id: str,
    admin_user: Annotated[User, Depends(require_admin)],
):
    """Retrieve the reduced OBJ mesh for an archived component."""
    validate_component_id(component_id)
    base = request.app.component_geometry_archive_dir
    mesh_path = os.path.join(base, component_id, 'mesh_reduced.obj')

    # Generate ETag for the file
    etag = generate_geometry_etag(mesh_path, component_id)

    # Check for conditional request
    if check_geometry_conditional_request(request, etag):
        from fastapi import Response
        return Response(
            status_code=304,
            headers={'ETag': etag}
        )

    return FileResponse(
        ensure_file(mesh_path),
        media_type='text/x-obj',
        filename='mesh_reduced.obj',
        headers={'ETag': etag, 'Cache-Control': 'private, max-age=3600'}
    )


# STATISTICS ROUTES -----------------------------------------------------------

@router.get(
    '/archived/types',
    summary='Get unique component types in archive (admin only)'
)
async def get_archived_unique_types(
    request: Request,
    admin_user: Annotated[User, Depends(require_admin)],
):
    """Get a list of unique component types in the archive."""
    coll = await get_archived_components_col(request)
    try:
        types = await coll.distinct('type')
        return JSONResponse(status_code=200, content=types)
    except Exception as e:
        print(f'[ERROR] get_archived_unique_types: {e}')
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get(
    '/archived/materials',
    summary='Get unique material names in archive (admin only)'
)
async def get_archived_unique_materials(
    request: Request,
    admin_user: Annotated[User, Depends(require_admin)],
):
    """Get a list of unique material names in the archive."""
    coll = await get_archived_components_col(request)
    try:
        materials = await coll.distinct('material')
        return JSONResponse(status_code=200, content=materials)
    except Exception as e:
        print(f'[ERROR] get_archived_unique_materials: {e}')
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get(
    '/archived/datasets',
    summary='Get unique dataset names in archive (admin only)'
)
async def get_archived_unique_datasets(
    request: Request,
    admin_user: Annotated[User, Depends(require_admin)],
):
    """Get a list of unique dataset names in the archive."""
    coll = await get_archived_components_col(request)
    try:
        datasets = await coll.distinct('dataset')
        return JSONResponse(status_code=200, content=datasets)
    except Exception as e:
        print(f'[ERROR] get_archived_unique_datasets: {e}')
        raise HTTPException(status_code=500, detail='Internal server error')
