#!/usr/bin/env python3.9
import os
import json
import hashlib
import shutil
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional, Literal

# THIRD PARTY MODULE IMPORTS --------------------------------------------------
from fastapi import (
    APIRouter, Body, Depends, HTTPException, Request, Response, status, Query,
    UploadFile, File
)
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field, field_validator
from pymongo.errors import PyMongoError

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.catalog.models import (  # NOQA
    ALLOWED_COMPLEXITY_LEVELS,
    ALLOWED_COMPONENT_SORTKEYS,
    ALLOWED_COMPONENT_TYPES,
    ALLOWED_CONDITION_VALUES,
    ALLOWED_MANUFACTURED_PRECISIONS,
    ComponentCount,
    ComponentDescriptors,
    ComponentLocation,
    ComponentModel,
    User,
)
from .auth import get_current_active_user, require_admin
from utility import (
    generate_component_etag,
    generate_etag_for_components,
    generate_geometry_etag,
    check_geometry_conditional_request,
    validate_component_id,
    ensure_file,
    read_upload_limited,
)

# INIT ROUTER -----------------------------------------------------------------

# create router instance
router = APIRouter()


# FASTAPI DEPENDENCIES --------------------------------------------------------

async def get_components_col(request: Request):
    return request.app.mongodb_components


def build_component_match_stage(
    comptype: Optional[str] = None,
    material: Optional[str] = None,
    dataset: Optional[str] = None,
    validated: Optional[int] = None,
    complexity: Optional[int] = None,
    fragment: Optional[bool] = None,
    bbx_min_x: Optional[float] = None,
    bbx_min_y: Optional[float] = None,
    bbx_min_z: Optional[float] = None,
    bbx_max_x: Optional[float] = None,
    bbx_max_y: Optional[float] = None,
    bbx_max_z: Optional[float] = None,
    reserved: Optional[str] = None,
) -> dict:
    """Build MongoDB match stage for component filtering."""
    match_stage = {}

    if comptype:
        match_stage['type'] = {"$regex": f"^{comptype}$", "$options": "i"}
    if material:
        match_stage['material'] = {"$regex": f"^{material}$", "$options": "i"}
    if dataset:
        match_stage['dataset'] = {"$regex": f"^{dataset}$", "$options": "i"}
    if validated == 1:
        match_stage['validated'] = True
    elif validated == -1:
        match_stage['validated'] = False

    # Add complexity filter
    if complexity is not None:
        match_stage['complexity'] = complexity

    # Add fragment filter
    if fragment is not None:
        match_stage['fragment'] = fragment

    # Add reservation status filter
    if reserved == 'true':
        # Fetch components reserved by current user
        # This will be handled in the aggregation pipeline
        match_stage['reserved'] = {"$ne": ""}
    elif reserved == 'false':
        # Fetch components that are not reserved by anyone
        match_stage['reserved'] = ""

    # Add bounding box filters
    bbx_filters = [
        bbx_min_x, bbx_min_y, bbx_min_z,
        bbx_max_x, bbx_max_y, bbx_max_z
    ]
    if any(bbx_filters):
        if bbx_min_x is not None or bbx_max_x is not None:
            bbx_query = {}
            if bbx_min_x is not None:
                bbx_query['$gte'] = bbx_min_x
            if bbx_max_x is not None:
                bbx_query['$lte'] = bbx_max_x
            if bbx_query:
                match_stage['bbx.0'] = bbx_query

        if bbx_min_y is not None or bbx_max_y is not None:
            bbx_query = {}
            if bbx_min_y is not None:
                bbx_query['$gte'] = bbx_min_y
            if bbx_max_y is not None:
                bbx_query['$lte'] = bbx_max_y
            if bbx_query:
                match_stage['bbx.1'] = bbx_query

        if bbx_min_z is not None or bbx_max_z is not None:
            bbx_query = {}
            if bbx_min_z is not None:
                bbx_query['$gte'] = bbx_min_z
            if bbx_max_z is not None:
                bbx_query['$lte'] = bbx_max_z
            if bbx_query:
                match_stage['bbx.2'] = bbx_query

    return match_stage


def check_conditional_request(request: Request, etag: str) -> bool:
    """
    Check if request is a conditional request with If-None-Match header.

    Args:
        request: FastAPI request object
        etag: Current ETag of the resource

    Returns:
        True if resource hasn't changed (should return 304), False otherwise
    """
    if_none_match = request.headers.get('if-none-match')
    if if_none_match and if_none_match == etag:
        return True
    return False


async def get_components_with_aggregation(
    request: Request,
    match_stage: dict,
    projection: Optional[dict] = None,
    sortkey: str = '_id',
    sort_order: int = 1,
    page: int = 0,
    size: int = 0,
    include_username: bool = True,
    current_user_id: Optional[str] = None
) -> list:
    """
    Get components using MongoDB aggregation pipeline with optional
    username enrichment.

    Args:
        request: FastAPI request object
        match_stage: MongoDB match stage for filtering
        projection: Optional projection to limit returned fields
        sortkey: Field to sort by
        sort_order: Sort order (1 for ascending, -1 for descending)
                 page: Page number (0=get all, 1+=paginated)
        size: Page size
        include_username: Whether to include username enrichment

    Returns:
        List of components with optional username enrichment
    """
    coll = await get_components_col(request)

    # Guard against invalid sortkeys
    if sortkey not in ALLOWED_COMPONENT_SORTKEYS:
        sortkey = '_id'

    # Build aggregation pipeline
    pipeline = [{'$match': match_stage}]

    # Add username enrichment if requested
    if include_username:
        users_coll = request.app.mongodb_users
        pipeline.extend([
            {
                '$lookup': {
                    'from': users_coll.name,
                    'localField': 'reserved',
                    'foreignField': '_id',
                    'as': 'user_info'
                }
            },
            {
                '$addFields': {
                    'reserved_by_username': {
                        '$cond': {
                            'if': {'$gt': [{'$size': '$user_info'}, 0]},
                            'then': {
                                '$arrayElemAt': ['$user_info.username', 0]
                            },
                            'else': None
                        }
                    }
                }
            },
            {'$unset': 'user_info'}  # Remove temporary user_info array
        ])

        # Add filter for components reserved by current user if requested
        if current_user_id and match_stage.get('reserved') == {"$ne": ""}:
            pipeline.append({
                '$match': {'reserved': current_user_id}
            })

    # Add projection if specified
    if projection:
        pipeline.append({'$project': projection})

    # Add sorting
    pipeline.append({'$sort': {sortkey: sort_order}})

    # Add pagination if needed
    if page > 0 and size > 0:
        pipeline.extend([
            {'$skip': (page - 1) * size},
            {'$limit': size},
        ])
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


# STATISTIC ROUTES ------------------------------------------------------------

@router.get(
        '/componentcount',
        summary='Count components',
        response_model=ComponentCount)
async def count_components(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    comptype: Optional[str] = Query(None, description='Component type filter'),
    material: Optional[str] = Query(None, description='Material type filter'),
    dataset: Optional[str] = Query(None, description='Dataset name filter'),
    validated: int = Query(1, description='1=true, -1=false, 0/other=any'),
    complexity: Optional[int] = Query(None, description='Complexity (0-3)'),
    fragment: Optional[bool] = Query(None, description='Is fragment'),
    bbx_min_x: Optional[float] = Query(None, description='Min X'),
    bbx_min_y: Optional[float] = Query(None, description='Min Y'),
    bbx_min_z: Optional[float] = Query(None, description='Min Z'),
    bbx_max_x: Optional[float] = Query(None, description='Max X'),
    bbx_max_y: Optional[float] = Query(None, description='Max Y'),
    bbx_max_z: Optional[float] = Query(None, description='Max Z'),
):
    coll = await get_components_col(request)
    query: dict = {}
    if comptype:
        query['type'] = comptype
    if material:
        query['material'] = material
    if dataset:
        query['dataset'] = dataset
    if validated == 1:
        query['validated'] = True
    elif validated == -1:
        query['validated'] = False

    # Add complexity filter
    if complexity is not None:
        query['complexity'] = complexity

    # Add fragment filter
    if fragment is not None:
        query['fragment'] = fragment

    # Add bounding box filters
    if any([bbx_min_x, bbx_min_y, bbx_min_z, bbx_max_x, bbx_max_y, bbx_max_z]):
        bbx_query = {}
        if bbx_min_x is not None:
            bbx_query['$gte'] = bbx_min_x
        if bbx_max_x is not None:
            bbx_query['$lte'] = bbx_max_x
        if bbx_query:
            query['bbx.0'] = bbx_query

        bbx_query = {}
        if bbx_min_y is not None:
            bbx_query['$gte'] = bbx_min_y
        if bbx_max_y is not None:
            bbx_query['$lte'] = bbx_max_y
        if bbx_query:
            query['bbx.1'] = bbx_query

        bbx_query = {}
        if bbx_min_z is not None:
            bbx_query['$gte'] = bbx_min_z
        if bbx_max_z is not None:
            bbx_query['$lte'] = bbx_max_z
        if bbx_query:
            query['bbx.2'] = bbx_query

    try:
        count = await coll.count_documents(query)
    except PyMongoError as e:
        print(f'[ERROR] componentcount DB error: {e}')
        raise HTTPException(status_code=500, detail='Internal server error')

    return {'count': count}


@router.get('/components/stats', summary='Get aggregated component statistics')
async def get_components_stats(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    comptype: Optional[str] = Query(None, description='Component type filter'),
    material: Optional[str] = Query(None, description='Material type filter'),
    dataset: Optional[str] = Query(None, description='Dataset name filter'),
    validated: int = Query(1, description='1=true, -1=false, 0/other=any'),
    complexity: Optional[int] = Query(None, description='Complexity (0-3)'),
    fragment: Optional[bool] = Query(None, description='Is fragment'),
    bbx_min_x: Optional[float] = Query(None, description='Min X'),
    bbx_min_y: Optional[float] = Query(None, description='Min Y'),
    bbx_min_z: Optional[float] = Query(None, description='Min Z'),
    bbx_max_x: Optional[float] = Query(None, description='Max X'),
    bbx_max_y: Optional[float] = Query(None, description='Max Y'),
    bbx_max_z: Optional[float] = Query(None, description='Max Z'),
    limit_dim: int = Query(10, description='Top-N limit for long tail dims'),
):
    coll = await get_components_col(request)

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

    # One-pass aggregation using $facet
    pipeline = [
        {"$match": match_stage},
        {
            "$facet": {
                "total": [{"$count": "count"}],
                "byType": [
                    {"$group": {"_id": "$type", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ],
                "byMaterial": [
                    {"$group": {"_id": "$material", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ],
                "byDataset": [
                    {"$group": {"_id": "$dataset", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ],
                "byComplexity": [
                    {"$group": {"_id": "$complexity", "count": {"$sum": 1}}},
                    {"$sort": {"_id": 1}},
                ],
                "byValidated": [
                    {"$group": {"_id": "$validated", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ],
                "byFragment": [
                    {"$group": {"_id": "$fragment", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ],
                "byAssembly": [
                    {"$group": {"_id": "$assembly", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ],
                "reserved": [
                    {
                        "$group": {
                            "_id": {
                                "$cond": [
                                    {"$ne": ["$reserved", ""]}, True, False
                                ]
                            },
                            "count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"count": -1}},
                ],
                "descriptorsKeys": [
                    {"$project": {"pairs": {"$objectToArray": {"$ifNull": ["$descriptors", {}]}}}},  # NOQA401
                    {"$unwind": "$pairs"},
                    {"$group": {"_id": "$pairs.k", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ],
                "createdMonthly": [
                    {
                        "$group": {
                            "_id": {
                                "$dateToString": {
                                    "format": "%Y-%m",
                                    "date": {"$toDate": "$created"},
                                }
                            },
                            "count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"_id": 1}},
                ],
                "bbx": [
                    {"$project": {"x": {"$arrayElemAt": ["$bbx", 0]}, "y": {"$arrayElemAt": ["$bbx", 1]}, "z": {"$arrayElemAt": ["$bbx", 2]}}},  # NOQA401
                    {"$bucket": {"groupBy": "$x", "boundaries": [0, 0.5, 1, 2, 5, 10, 20, 50, 100, 1000], "default": ">=1000", "output": {"count": {"$sum": 1}}}},  # NOQA401
                ],
            }
        },
    ]

    try:
        cursor = await coll.aggregate(pipeline)
        docs = [doc async for doc in cursor]
        raw = docs[0] if docs else {}

        def norm_list(items):
            out = []
            for it in items or []:
                label = it.get('_id')
                if isinstance(label, bool):
                    label = 'true' if label else 'false'
                elif label is None:
                    label = 'unknown'
                out.append(
                    {"label": str(label),
                     "count": int(it.get('count', 0))}
                )
            return out

        total = (int((raw.get('total') or [{}])[0].get('count', 0))
                 if raw.get('total') else 0)

        # Apply Top-N + others for long tail dimensions
        def topn(items):
            rows = norm_list(items)
            if limit_dim and len(rows) > limit_dim:
                head = rows[:limit_dim]
                others_count = sum(r["count"] for r in rows[limit_dim:])
                head.append({"label": "others", "count": others_count})
                return head
            return rows

        content = {
            "total": total,
            "byType": norm_list(raw.get('byType')),
            "byMaterial": topn(raw.get('byMaterial')),
            "byDataset": topn(raw.get('byDataset')),
            "byComplexity": norm_list(raw.get('byComplexity')),
            "byValidated": norm_list(raw.get('byValidated')),
            "byFragment": norm_list(raw.get('byFragment')),
            "byAssembly": norm_list(raw.get('byAssembly')),
            "reserved": norm_list(raw.get('reserved')),
            "descriptorsKeys": topn(raw.get('descriptorsKeys')),
            "createdMonthly": norm_list(raw.get('createdMonthly')),
            "bbxX": norm_list(raw.get('bbx')),
        }

        return JSONResponse(status_code=200, content=content)
    except Exception as e:
        print(f'[ERROR] components stats aggregation: {e}')
        raise HTTPException(status_code=500, detail='Internal server error')


# UNIQUE VALUE ROUTES --------------------------------------------------------

@router.get('/datasets', summary='Get unique dataset names')
async def get_unique_datasets(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """Get a unique list of all dataset names in the database."""
    coll = await get_components_col(request)

    try:
        pipeline = [
            {"$group": {"_id": "$dataset"}},
            {"$sort": {"_id": 1}}
        ]
        cursor = await coll.aggregate(pipeline)
        datasets = [doc["_id"] async for doc in cursor if doc.get("_id")]
        return JSONResponse(status_code=200, content=datasets)
    except Exception as e:
        print(f'[ERROR] get_unique_datasets: {e}')
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get('/componenttypes', summary='Get unique component types')
async def get_unique_component_types(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """Get a unique list of all component types in the database."""
    coll = await get_components_col(request)

    try:
        pipeline = [
            {"$group": {"_id": "$type"}},
            {"$sort": {"_id": 1}}
        ]
        cursor = await coll.aggregate(pipeline)
        types = [doc["_id"] async for doc in cursor if doc.get("_id")]
        return JSONResponse(status_code=200, content=types)
    except Exception as e:
        print(f'[ERROR] get_unique_component_types: {e}')
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get('/materials', summary='Get unique material names')
async def get_unique_materials(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """Get a unique list of all material names in the database."""
    coll = await get_components_col(request)

    try:
        pipeline = [
            {"$group": {"_id": "$material"}},
            {"$sort": {"_id": 1}}
        ]
        cursor = await coll.aggregate(pipeline)
        materials = [doc["_id"] async for doc in cursor if doc.get("_id")]
        return JSONResponse(status_code=200, content=materials)
    except Exception as e:
        print(f'[ERROR] get_unique_materials: {e}')
        raise HTTPException(status_code=500, detail='Internal server error')


# ADD COMPONENT ROUTES --------------------------------------------------------

@router.post('/components/add/', summary='Add a new component')
async def create_component(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component: ComponentModel = ...,
):
    # Exclude etag from database storage - it's only for HTTP caching.
    doc = component.model_dump(
        by_alias=True,
        exclude_none=True,
        exclude={'etag'}
    )
    coll = await get_components_col(request)
    # Check if component with this ID already exists
    existing_component = await coll.find_one({'_id': doc['_id']})
    if existing_component:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(f'Component with ID {doc["_id"]} '
                    'already exists')
        )
    try:
        res = await coll.insert_one(doc)
        created = await coll.find_one({'_id': res.inserted_id})
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=created)
    except PyMongoError as e:
        # Handle MongoDB errors, including duplicate key errors
        error_str = str(e).lower()
        if ('duplicate key error' in error_str or
                'duplicate key' in error_str):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(f'Component with ID {doc["_id"]} '
                        'already exists')
            )
        else:
            print(f'[ERROR] create_component DB error: {e}')
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Internal server error'
            )


# VALIDATION ROUTES -----------------------------------------------------------

@router.get(
    '/validate/{component_id}',
    summary='Validate component (admin only)'
)
async def validate_component(
    request: Request,
    admin_user: Annotated[User, Depends(require_admin)],
    component_id: str = '',
):
    coll = await get_components_col(request)
    component = await coll.find_one({'_id': component_id})
    if not component:
        raise HTTPException(404, 'Not found')
    if not component.get('validated', False):
        await coll.update_one(
            {'_id': component_id}, {'$set': {'validated': True}}
        )
    updated = await coll.find_one({'_id': component_id})
    return JSONResponse(status_code=200, content=updated)


# SHALLOW COMPONENT ROUTES ----------------------------------------------------

@router.get(
        '/shallowcomponents/{component_id}',
        summary='Single shallow component')
async def get_component_shallow(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str = '',
):
    coll = await get_components_col(request)
    projection = {'geometry': 0, 'descriptors': 0}
    doc = await coll.find_one({'_id': component_id}, projection)
    if not doc:
        raise HTTPException(404, 'Not found')
    return JSONResponse(status_code=200, content=doc)


@router.get('/shallowcomponents', summary='List shallow components')
async def get_components_shallow(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    page: int = Query(0, description='Page number (0=get all, 1+=paginated)'),
    size: int = Query(0, description='Page size (0=get all)'),
    sortkey: str = Query('_id', description='Sort key'),
    sortorder: Literal['asc', 'desc'] = Query(
        'asc',
        description='Sort order: asc or desc',
    ),
    comptype: str = Query('', description='Component type filter'),
    material: str = Query('', description='Material type filter'),
    dataset: str = Query('', description='Dataset name filter'),
    validated: int = Query(1, description='1=true, -1=false, 0/other=any'),
    complexity: Optional[int] = Query(None, description='Complexity (0-3)'),
    fragment: Optional[bool] = Query(None, description='Is fragment'),
    reserved: Optional[str] = Query(
        None,
        description=('Reservation filter: "true"=reserved by current user, '
                     '"false"=not reserved, None=any')
    ),
    bbx_min_x: Optional[float] = Query(None, description='Min X'),
    bbx_min_y: Optional[float] = Query(None, description='Min Y'),
    bbx_min_z: Optional[float] = Query(None, description='Min Z'),
    bbx_max_x: Optional[float] = Query(None, description='Max X'),
    bbx_max_y: Optional[float] = Query(None, description='Max Y'),
    bbx_max_z: Optional[float] = Query(None, description='Max Z'),
):
    sort_order = -1 if sortorder == 'desc' else 1

    match_stage = build_component_match_stage(
        comptype=comptype,
        material=material,
        dataset=dataset,
        validated=validated,
        complexity=complexity,
        fragment=fragment,
        reserved=reserved,
        bbx_min_x=bbx_min_x,
        bbx_min_y=bbx_min_y,
        bbx_min_z=bbx_min_z,
        bbx_max_x=bbx_max_x,
        bbx_max_y=bbx_max_y,
        bbx_max_z=bbx_max_z,
    )
    components = await get_components_with_aggregation(
        request,
        match_stage,
        projection={'geometry': 0, 'descriptors': 0},
        sortkey=sortkey,
        sort_order=sort_order,
        page=page,
        size=size,
        include_username=True,
        current_user_id=current_user.id,
    )
    return JSONResponse(status_code=200, content=components)


# FULL COMPONENT ROUTES -------------------------------------------------------

@router.get('/components', summary='List components')
async def get_components(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    page: int = Query(0, description='Page number (0=get all, 1+=paginated)'),
    size: int = Query(0, description='Page size (0=get all)'),
    sortkey: str = Query('_id', description='Sort key'),
    sortorder: Literal['asc', 'desc'] = Query(
        'asc',
        description='Sort order: asc or desc',
    ),
    comptype: str = Query('', description='Component type filter'),
    material: str = Query('', description='Material type filter'),
    dataset: str = Query('', description='Dataset name filter'),
    validated: int = Query(1, description='1=true, -1=false, 0/other=any'),
    complexity: Optional[int] = Query(None, description='Complexity (0-3)'),
    fragment: Optional[bool] = Query(None, description='Is fragment'),
    reserved: Optional[str] = Query(
        None,
        description=('Reservation filter: "true"=reserved by current user, '
                     '"false"=not reserved, None=any')
    ),
    bbx_min_x: Optional[float] = Query(None, description='Min X'),
    bbx_min_y: Optional[float] = Query(None, description='Min Y'),
    bbx_min_z: Optional[float] = Query(None, description='Min Z'),
    bbx_max_x: Optional[float] = Query(None, description='Max X'),
    bbx_max_y: Optional[float] = Query(None, description='Max Y'),
    bbx_max_z: Optional[float] = Query(None, description='Max Z'),
):
    sort_order = -1 if sortorder == 'desc' else 1

    match_stage = build_component_match_stage(
        comptype=comptype,
        material=material,
        dataset=dataset,
        validated=validated,
        complexity=complexity,
        fragment=fragment,
        reserved=reserved,
        bbx_min_x=bbx_min_x,
        bbx_min_y=bbx_min_y,
        bbx_min_z=bbx_min_z,
        bbx_max_x=bbx_max_x,
        bbx_max_y=bbx_max_y,
        bbx_max_z=bbx_max_z,
    )
    components = await get_components_with_aggregation(
        request,
        match_stage,
        projection={},
        sortkey=sortkey,
        sort_order=sort_order,
        page=page,
        size=size,
        include_username=True,
        current_user_id=current_user.id,
    )

    # Parse through ComponentModel to apply exclude_none configuration
    components_clean = []
    for component in components:
        try:
            component_model = ComponentModel(**component)
            components_clean.append(component_model.model_dump(
                by_alias=True, exclude_none=True))
        except Exception:
            # If parsing fails, use original component data
            components_clean.append(component)

    # Generate ETag for the component list
    etag = generate_etag_for_components(components_clean)

    # Check for conditional request
    if check_conditional_request(request, etag):
        return JSONResponse(
            status_code=304,
            content=None,
            headers={'ETag': etag}
        )

    # Return components with ETag header
    return JSONResponse(
        status_code=200,
        content=components_clean,
        headers={
            'ETag': etag,
            'Cache-Control': 'private, max-age=3600'
        }
    )


@router.get('/components/{component_id}', summary='Get component by id')
async def get_component(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str = '',
):
    match_stage = {'_id': component_id}
    components = await get_components_with_aggregation(
        request,
        match_stage,
        include_username=True
    )

    if not components:
        raise HTTPException(404, 'Not found')

    component = components[0]

    # Parse through ComponentModel to apply exclude_none configuration
    try:
        component_model = ComponentModel(**component)
        component_clean = component_model.model_dump(
            by_alias=True,
            exclude_none=True)
    except Exception:
        # If parsing fails, use original component data
        component_clean = component

    # Generate ETag for the individual component
    etag = generate_component_etag(component_clean)

    # Check for conditional request
    if check_conditional_request(request, etag):
        return JSONResponse(
            status_code=304,
            content=None,
            headers={'ETag': etag}
        )

    # Return component with ETag header
    return JSONResponse(
        status_code=200,
        content=component_clean,
        headers={
            'ETag': etag,
            'Cache-Control': 'private, max-age=3600'
        }
    )


# EDIT METADATA: ADMIN ONLY ---------------------------------------------------

class ComponentMetadataUpdate(BaseModel):
    """
    Admin-editable component metadata. All fields are optional; only those
    explicitly provided are updated. Structural/derived fields (geometry,
    bbx, iframe, pca_frame, reserved, validated, descriptors, processes,
    attributes, marker_points, _id, created) are intentionally excluded.
    """
    name: Optional[str] = Field(
        default=None,
        max_length=200,
        description='Human readable component name',
    )
    componenttype: Optional[str] = Field(
        default=None,
        alias='type',
        description='Component type (one of ALLOWED_COMPONENT_TYPES)',
    )
    material: Optional[str] = Field(
        default=None,
        max_length=100,
        description='Material type',
    )
    dataset: Optional[str] = Field(
        default=None,
        max_length=200,
        description='Dataset name',
    )
    complexity: Optional[int] = Field(
        default=None,
        description='Complexity level (0-3)',
    )
    fragment: Optional[bool] = Field(
        default=None,
        description='Whether this component is a fragment',
    )
    assembly: Optional[bool] = Field(
        default=None,
        description='Whether this component is an assembly',
    )
    color: Optional[List[int]] = Field(
        default=None,
        description='RGB color as [R, G, B] integers (0-255)',
    )
    location: Optional[ComponentLocation] = Field(
        default=None,
        description='Geographic location (lat/lon coordinates)',
    )
    # Admin-editable provenance / lineage fields.
    condition: Optional[int] = Field(
        default=None,
        description=(
            'Condition grade: 0=destroyed/retired, 1=poor, 2=average, '
            '3=good. Must be one of ALLOWED_CONDITION_VALUES.'
        ),
    )
    manufactured_at: Optional[str] = Field(
        default=None,
        max_length=40,
        description=(
            'ISO-8601 timestamp describing when the component was '
            'originally manufactured.'
        ),
    )
    manufactured_precision: Optional[str] = Field(
        default=None,
        description=(
            'Precision qualifier for manufactured_at. Must be one of '
            'ALLOWED_MANUFACTURED_PRECISIONS (exact, month, year, unknown).'
        ),
    )
    salvage_source: Optional[str] = Field(
        default=None,
        max_length=500,
        description='Short free-text description of salvage origin.',
    )
    salvaged_at: Optional[str] = Field(
        default=None,
        max_length=40,
        description=(
            'ISO-8601 timestamp describing when the component was '
            'salvaged.'
        ),
    )
    parent_component: Optional[str] = Field(
        default=None,
        description=(
            'Optional UUID of parent component. '
            'Use empty string or null to clear.'
        ),
    )

    class Config:
        populate_by_name = True
        extra = 'forbid'

    @field_validator('componenttype')
    @classmethod
    def _check_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in ALLOWED_COMPONENT_TYPES:
            raise ValueError(
                f'type must be one of {ALLOWED_COMPONENT_TYPES}'
            )
        return v

    @field_validator('complexity')
    @classmethod
    def _check_complexity(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        if v not in ALLOWED_COMPLEXITY_LEVELS:
            raise ValueError(
                f'complexity must be one of {ALLOWED_COMPLEXITY_LEVELS}'
            )
        return v

    @field_validator('color')
    @classmethod
    def _check_color(cls, v: Optional[List[int]]) -> Optional[List[int]]:
        if v is None:
            return v
        if len(v) != 3:
            raise ValueError('color must have exactly 3 elements [R, G, B]')
        for c in v:
            if not isinstance(c, int) or c < 0 or c > 255:
                raise ValueError(
                    'color components must be integers in 0-255'
                )
        return v

    @field_validator('material', 'dataset', 'name')
    @classmethod
    def _strip_strings(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if v == '':
            raise ValueError('value must not be empty')
        return v

    @field_validator('condition')
    @classmethod
    def _check_condition(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        if v not in ALLOWED_CONDITION_VALUES:
            raise ValueError(
                f'condition must be one of {ALLOWED_CONDITION_VALUES}'
            )
        return v

    @field_validator('manufactured_precision')
    @classmethod
    def _check_manufactured_precision(
        cls, v: Optional[str]
    ) -> Optional[str]:
        if v is None:
            return v
        if v not in ALLOWED_MANUFACTURED_PRECISIONS:
            raise ValueError(
                'manufactured_precision must be one of '
                f'{ALLOWED_MANUFACTURED_PRECISIONS}'
            )
        return v

    @field_validator('salvage_source')
    @classmethod
    def _check_salvage_source(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        return v or None

    @field_validator('parent_component')
    @classmethod
    def _check_parent_component(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == '':
            return None
        try:
            uuid.UUID(str(v))
        except (ValueError, AttributeError, TypeError):
            raise ValueError(
                'parent_component must be a valid UUID string'
            )
        return str(v)


@router.patch(
    '/components/{component_id}',
    summary='Update component metadata (admin only)',
)
async def update_component_metadata(
    request: Request,
    admin_user: Annotated[User, Depends(require_admin)],
    component_id: str,
    payload: ComponentMetadataUpdate = Body(...),
):
    """
    Partial update of admin-editable component metadata.

    Only fields explicitly provided in the request body are modified.
    `lastmodified` is refreshed automatically when at least one field
    changes. Structural and derived fields (geometry, bounding box,
    frames, reservation, validation, etc.) cannot be edited via this
    endpoint and must be modified through their dedicated routes.
    """
    validate_component_id(component_id)

    coll = await get_components_col(request)
    existing = await coll.find_one({'_id': component_id})
    if not existing:
        raise HTTPException(404, 'Not found')

    # Build $set using alias names (maps componenttype -> 'type').
    # exclude_unset=True is the proper PATCH semantics: only fields the
    # client explicitly sent are written, and an explicit null clears the
    # field. Fields the client omitted are left untouched.
    update_data: Dict[str, Any] = payload.model_dump(
        by_alias=True,
        exclude_unset=True,
    )

    if not update_data:
        raise HTTPException(400, 'No updatable fields provided')

    update_data['lastmodified'] = datetime.now(timezone.utc).isoformat(
    ).replace('+00:00', 'Z')

    try:
        await coll.update_one(
            {'_id': component_id},
            {'$set': update_data},
        )
    except PyMongoError as e:
        print(f'[ERROR] update_component_metadata DB error: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )

    updated = await coll.find_one({'_id': component_id})
    return JSONResponse(status_code=200, content=updated)


@router.get('/schema/component', summary='Get ComponentModel schema')
async def get_component_schema(request: Request):
    """Get the OpenAPI schema for ComponentModel"""

    schema = ComponentModel.model_json_schema()

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
            'Cache-Control': 'public, max-age=86400'  # 24h cache for schema
        }
    )


# COMPONENT DETAIL ROUTES -----------------------------------------------------

@router.get(
    '/components/{component_id}/geometry',
    summary='Get component geometry'
)
async def get_component_geometry(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str = '',
):
    coll = await get_components_col(request)
    doc = await coll.find_one({'_id': component_id}, {'geometry': 1})
    if not doc:
        raise HTTPException(404, 'Not found')
    return JSONResponse(status_code=200, content=doc)


@router.get('/components/{component_id}/geometry_detailed')
async def get_component_geometry_detailed(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
):
    validate_component_id(component_id)
    base = request.app.component_geometry_dir
    mesh_path = os.path.join(base, component_id, 'mesh.obj')

    # Generate ETag for the file
    etag = generate_geometry_etag(mesh_path, component_id)

    # Check for conditional request
    if check_geometry_conditional_request(request, etag):
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


@router.get('/components/{component_id}/material_detailed')
async def get_component_material_detailed(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
):
    """
    DEPRECATED: Material files are no longer generated.
    Returns 404 as materials are now embedded as vertex colors in OBJ files.
    """
    raise HTTPException(404, 'Material files no longer supported. '
                             'Colors embedded as vertex colors in OBJ files.')


@router.get('/components/{component_id}/geometry_reduced')
async def get_component_geometry_reduced(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
):
    validate_component_id(component_id)
    base = request.app.component_geometry_dir
    mesh_path = os.path.join(base, component_id, 'mesh_reduced.obj')

    # Generate ETag for the file
    etag = generate_geometry_etag(mesh_path, component_id)

    # Check for conditional request
    if check_geometry_conditional_request(request, etag):
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


@router.get('/components/{component_id}/material_reduced')
async def get_component_material_reduced(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
):
    """
    DEPRECATED: Material files are no longer generated.
    Returns 404 as materials are now embedded as vertex colors in OBJ files.
    """
    raise HTTPException(404, 'Material files no longer supported. '
                             'Colors embedded as vertex colors in OBJ files.')


@router.get('/components/{component_id}/texture')
async def get_component_texture(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
):
    """
    DEPRECATED: Texture files are no longer generated.
    Returns 404 as colors are now embedded as vertex colors in OBJ files.
    """
    raise HTTPException(404, 'Texture files no longer supported. '
                             'Colors embedded as vertex colors in OBJ files.')


@router.get('/components/{component_id}/preview_image')
async def get_component_preview_image(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
):
    validate_component_id(component_id)
    base = request.app.component_preview_dir
    preview_image_path = os.path.join(base, f'{component_id}.webp')
    return FileResponse(
        ensure_file(preview_image_path),
        media_type='image/webp',
        filename=f'{component_id}.webp'
    )


@router.get(
    '/components/{component_id}/descriptors',
    summary='Retrieve descriptors for a component',
    response_model=ComponentDescriptors,
)
async def get_component_descriptors(
    component_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    components=Depends(get_components_col),
):
    doc = await components.find_one(
        {'_id': component_id},
        {'_id': 1, 'descriptors': 1},           # include _id explicitly
    )
    if not doc:
        raise HTTPException(status_code=404, detail='Component not found')
    return doc


# ADD GEOMETRY ROUTES ---------------------------------------------------------

@router.post(
    '/components/{component_id}/geometry/add_reduced',
    summary='Add reduced geometry to existing component'
)
async def add_reduced_geometry(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
    mesh_file: UploadFile = File(..., description='Reduced mesh OBJ file'),
):
    """
    Add reduced geometry files to an existing component.
    Accepts mesh_reduced.obj with embedded vertex colors.
    """
    validate_component_id(component_id)
    # Check if component exists
    coll = await get_components_col(request)
    component = await coll.find_one({'_id': component_id})
    if not component:
        raise HTTPException(404, 'Component not found')

    # Validate file types
    if not mesh_file.filename.endswith('.obj'):
        raise HTTPException(400, 'Mesh file must be a .obj file')

    # Create component geometry directory
    base_dir = request.app.component_geometry_dir
    component_dir = os.path.join(base_dir, component_id)
    os.makedirs(component_dir, exist_ok=True)

    try:
        # Save reduced mesh file
        mesh_path = os.path.join(component_dir, 'mesh_reduced.obj')
        with open(mesh_path, 'wb') as f:
            content = await read_upload_limited(
                mesh_file, request.app.geometry_upload_limit_bytes
            )
            f.write(content)

        return JSONResponse(
            status_code=200,
            content={'message': 'Reduced geometry file uploaded successfully'}
        )
    except Exception as e:
        print(f'[ERROR] add_reduced_geometry: {e}')
        raise HTTPException(500, 'Failed to save geometry file')


@router.post(
    '/components/{component_id}/geometry/add_detailed',
    summary='Add detailed geometry to existing component'
)
async def add_detailed_geometry(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
    mesh_file: UploadFile = File(..., description='Detailed mesh OBJ file'),
):
    """
    Add detailed geometry files to an existing component.
    Accepts mesh.obj with embedded vertex colors.
    """
    validate_component_id(component_id)
    # Check if component exists
    coll = await get_components_col(request)
    component = await coll.find_one({'_id': component_id})
    if not component:
        raise HTTPException(404, 'Component not found')

    # Validate file types
    if not mesh_file.filename.endswith('.obj'):
        raise HTTPException(400, 'Mesh file must be a .obj file')

    # Create component geometry directory
    base_dir = request.app.component_geometry_dir
    component_dir = os.path.join(base_dir, component_id)
    os.makedirs(component_dir, exist_ok=True)

    try:
        # Save detailed mesh file
        mesh_path = os.path.join(component_dir, 'mesh.obj')
        with open(mesh_path, 'wb') as f:
            content = await read_upload_limited(
                mesh_file, request.app.geometry_upload_limit_bytes
            )
            f.write(content)

        return JSONResponse(
            status_code=200,
            content={
                'message': 'Detailed geometry file uploaded successfully'
            }
        )
    except Exception as e:
        print(f'[ERROR] add_detailed_geometry: {e}')
        raise HTTPException(500, 'Failed to save geometry file')


# DELETE: ADMIN ONLY ----------------------------------------------------------

@router.delete(
    '/components/{component_id}',
    summary='Delete component (admin only)'
)
async def delete_component(
    request: Request,
    admin_user=Depends(require_admin),
    component_id: str = '',
):
    """
    Delete a component and its associated files.

    This operation:
    1. Deletes the component's geometry directory (containing OBJ files)
    2. Deletes the component's preview image file (.webp)
    3. Removes the component from the database

    If file deletion fails, the operation continues and deletes the
    database record anyway.
    """
    validate_component_id(component_id)
    # Get component geometry directory path
    geometry_base_dir = request.app.component_geometry_dir
    component_dir = os.path.join(geometry_base_dir, component_id)

    # Delete geometry directory if it exists
    if os.path.exists(component_dir):
        try:
            shutil.rmtree(component_dir)
        except Exception as e:
            # Log the error but continue with other deletions
            print(f'Warning: Failed to delete geometry directory '
                  f'{component_dir}: {e}')

    # Get component preview file path and delete if it exists
    preview_base_dir = request.app.component_preview_dir
    preview_file_path = os.path.join(preview_base_dir, f'{component_id}.webp')

    if os.path.exists(preview_file_path):
        try:
            os.remove(preview_file_path)
        except Exception as e:
            # Log the error but continue with database deletion
            print(f'Warning: Failed to delete preview file '
                  f'{preview_file_path}: {e}')

    # Delete component from database
    coll = await get_components_col(request)
    res = await coll.delete_one({'_id': component_id})
    if res.deleted_count == 0:
        raise HTTPException(404, 'Not found')

    return {'ok': True}
