#!/usr/bin/env python3.9
import os
from typing import Annotated, Optional

# THIRD PARTY MODULE IMPORTS --------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.encoders import jsonable_encoder
from pymongo.errors import PyMongoError

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.catalogue.models import (  # NOQA
    ALLOWED_COMPONENT_SORTKEYS,
    ComponentCount,
    ComponentDescriptors,
    ComponentModel,
    UpdateComponentModel,
    User,
)
from .auth import get_current_active_user, require_admin


# INIT ROUTER -----------------------------------------------------------------

# create router instance
router = APIRouter()


# FASTAPI DEPENDENCIES --------------------------------------------------------

async def get_components_col(request: Request):
    return request.app.mongodb_components


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
        raise HTTPException(status_code=500, detail=f'DB error: {e}')

    return {'count': count}


# ADD COMPONENT ROUTES --------------------------------------------------------

@router.post('/', summary='Add a new component')
async def create_component(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component: ComponentModel = ...,
):
    doc = jsonable_encoder(component, by_alias=True)
    coll = await get_components_col(request)
    res = await coll.insert_one(doc)
    created = await coll.find_one({'_id': res.inserted_id})
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=created)


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
    page: int = Query(0, description='Page number (0-based)'),
    size: int = Query(0, description='Page size'),
    sortkey: str = Query('_id', description='Sort key'),
    comptype: str = Query('', description='Component type filter'),
    material: str = Query('', description='Material type filter'),
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
    query = {}
    projection = {'geometry': 0, 'descriptors': 0}
    sort_order = 1
    if comptype:
        query['type'] = {"$regex": f"^{comptype}$", "$options": "i"}
    if material:
        query['material'] = {"$regex": f"^{material}$", "$options": "i"}
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

    if sortkey not in ALLOWED_COMPONENT_SORTKEYS:
        sortkey = '_id'

    if not page and not size:
        items = [doc async for doc
                 in coll.find(query, projection).sort(sortkey, sort_order)]
    else:
        cursor = (
            coll.find(query, projection)
            .sort(sortkey, sort_order)
            .skip((page - 1) * size if page > 0 else 0)
            .limit(size)
        )
        items = [doc async for doc in cursor]
    return JSONResponse(status_code=200, content=items)


# FULL COMPONENT ROUTES -------------------------------------------------------

async def enrich_components_with_usernames(
    components: list,
    users_coll
) -> list:
    """
    Enrich components with username information for reserved components.
    """
    enriched_components = []

    for component in components:
        # Convert ObjectId to string for JSON serialization
        component['_id'] = str(component['_id'])

        # If component is reserved, add username information
        if component.get('reserved'):
            try:
                user_doc = await users_coll.find_one(
                    {'_id': component['reserved']}
                )
                if user_doc:
                    component['reserved_by_username'] = (
                        user_doc.get('username', 'Unknown')
                    )
                else:
                    component['reserved_by_username'] = 'Unknown User'
            except Exception:
                component['reserved_by_username'] = 'Unknown User'

        enriched_components.append(component)

    return enriched_components


@router.get('/components', summary='List components')
async def get_components(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    page: int = Query(0, description='Page number (0-based)'),
    size: int = Query(0, description='Page size'),
    sortkey: str = Query('_id', description='Sort key'),
    comptype: str = Query('', description='Component type filter'),
    material: str = Query('', description='Material type filter'),
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
    query, sort_order = {}, 1
    if comptype:
        query['type'] = {"$regex": f"^{comptype}$", "$options": "i"}
    if material:
        query['material'] = {"$regex": f"^{material}$", "$options": "i"}
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

    if sortkey not in ALLOWED_COMPONENT_SORTKEYS:
        sortkey = '_id'

    if not page and not size:
        items = [doc async for doc
                 in coll.find(query).sort(sortkey, sort_order)]
    else:
        cursor = (
            coll.find(query)
            .sort(sortkey, sort_order)
            .skip((page - 1) * size if page > 0 else 0)
            .limit(size)
        )
        items = [doc async for doc in cursor]

    # Enrich components with username information
    users_coll = request.app.mongodb_users
    enriched_items = await enrich_components_with_usernames(items, users_coll)

    return JSONResponse(status_code=200, content=enriched_items)


@router.get('/components/{component_id}', summary='Get component by id')
async def get_component(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str = '',
):
    coll = await get_components_col(request)
    doc = await coll.find_one({'_id': component_id})
    if not doc:
        raise HTTPException(404, 'Not found')

    # Enrich component with username information
    users_coll = request.app.mongodb_users
    enriched_docs = await enrich_components_with_usernames([doc], users_coll)

    return JSONResponse(status_code=200, content=enriched_docs[0])


@router.get('/schema/component', summary='Get ComponentModel schema')
async def get_component_schema():
    """Get the OpenAPI schema for ComponentModel"""
    from apps.catalogue.models import ComponentModel
    return ComponentModel.model_json_schema()


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


def _ensure_file(path: str):
    if not os.path.exists(path):
        raise HTTPException(404, 'File not found')
    return path


@router.get('/components/{component_id}/geometry_detailed')
async def get_component_geometry_detailed(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
):
    base = request.app.component_geometry_dir
    mesh_path = os.path.join(base, component_id, 'mesh.obj')
    return FileResponse(
        _ensure_file(mesh_path),
        media_type='text/x-obj',
        filename='mesh.obj'
    )


@router.get('/components/{component_id}/material_detailed')
async def get_component_material_detailed(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
):
    base = request.app.component_geometry_dir
    mtl_path = os.path.join(base, component_id, 'mesh.mtl')
    return FileResponse(
        _ensure_file(mtl_path),
        media_type='text/x-mtl',
        filename='mesh.mtl'
    )


@router.get('/components/{component_id}/geometry_reduced')
async def get_component_geometry_reduced(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
):
    base = request.app.component_geometry_dir
    mesh_path = os.path.join(base, component_id, 'mesh_reduced.obj')
    return FileResponse(
        _ensure_file(mesh_path),
        media_type='text/x-obj',
        filename='mesh_reduced.obj'
    )


@router.get('/components/{component_id}/material_reduced')
async def get_component_material_reduced(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
):
    base = request.app.component_geometry_dir
    mtl_path = os.path.join(base, component_id, 'mesh_reduced.mtl')
    return FileResponse(
        _ensure_file(mtl_path),
        media_type='text/x-mtl',
        filename='mesh_reduced.mtl'
    )


@router.get('/components/{component_id}/texture')
async def get_component_texture(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
):
    base = request.app.component_geometry_dir
    texture_path = os.path.join(base, component_id, 'texture.jpg')
    return FileResponse(
        _ensure_file(texture_path),
        media_type='image/jpeg',
        filename=f'{component_id}_texture.jpg'
    )


@router.get('/components/{component_id}/preview_image')
async def get_component_preview_image(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
):
    base = request.app.component_preview_dir
    preview_image_path = os.path.join(base, f'{component_id}.webp')
    return FileResponse(
        _ensure_file(preview_image_path),
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
    coll = await get_components_col(request)
    res = await coll.delete_one({'_id': component_id})
    if res.deleted_count == 0:
        raise HTTPException(404, 'Not found')
    return {'ok': True}
