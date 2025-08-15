#!/usr/bin/env python3.9
from typing import Annotated
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.encoders import jsonable_encoder

from apps.catalogue.models import (  # NOQA
    ALLOWED_COMPONENT_SORTKEYS,
    ComponentModel,
    UpdateComponentModel,
    User,
)
from .auth import get_current_active_user, require_admin

router = APIRouter()


# -------- deps --------
async def comps(request: Request):
    return request.app.mongodb_components


# -------- statistics --------
@router.get("/componentcount", summary="Count components")
async def count_components(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    comptype: str = "",
    material: str = "",
    validated: int = 1,
):
    coll = await comps(request)
    query = {}
    if comptype:
        query["type"] = comptype
    if material:
        query["material"] = material
    if validated == 1:
        query["validated"] = True
    elif validated == -1:
        query["validated"] = False
    count = await coll.count_documents(query)
    return JSONResponse(status_code=status.HTTP_200_OK, content=count)


# -------- create --------
@router.post("/", summary="Add a new component")
async def create_component(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component: ComponentModel = ...,
):
    doc = jsonable_encoder(component, by_alias=True)
    coll = await comps(request)
    res = await coll.insert_one(doc)
    created = await coll.find_one({"_id": res.inserted_id})
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=created)


# -------- validate --------
@router.get(
    "/validate/{component_id}",
    summary="Validate component"
)
async def validate_component(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str = "",
):
    coll = await comps(request)
    component = await coll.find_one({"_id": component_id})
    if not component:
        raise HTTPException(404, "Not found")
    if not component.get("validated", False):
        await coll.update_one(
            {"_id": component_id}, {"$set": {"validated": True}}
        )
    updated = await coll.find_one({"_id": component_id})
    return JSONResponse(status_code=200, content=updated)


# -------- shallow --------
@router.get(
        "/shallowcomponents/{component_id}",
        summary="Single shallow component")
async def get_component_shallow(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str = "",
):
    coll = await comps(request)
    projection = {"geometry": 0, "descriptors": 0}
    doc = await coll.find_one({"_id": component_id}, projection)
    if not doc:
        raise HTTPException(404, "Not found")
    return JSONResponse(status_code=200, content=doc)


@router.get("/shallowcomponents", summary="List shallow components")
async def get_components_shallow(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    page: int = 0,
    size: int = 0,
    sortkey: str = "_id",
    comptype: str = "",
    material: str = "",
    validated: int = 1,
):
    coll = await comps(request)
    query = {}
    projection = {"geometry": 0, "descriptors": 0}
    sort_order = 1
    if comptype:
        query["type"] = comptype
    if material:
        query["material"] = material
    if validated == 1:
        query["validated"] = True
    elif validated == -1:
        query["validated"] = False
    if sortkey not in ALLOWED_COMPONENT_SORTKEYS:
        sortkey = "_id"

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


# -------- full components --------
@router.get("/components", summary="List components")
async def get_components(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    page: int = 0,
    size: int = 0,
    sortkey: str = "_id",
    comptype: str = "",
    material: str = "",
    validated: int = 1,
):
    coll = await comps(request)
    query, sort_order = {}, 1
    if comptype:
        query["type"] = comptype
    if material:
        query["material"] = material
    if validated == 1:
        query["validated"] = True
    elif validated == -1:
        query["validated"] = False
    if sortkey not in ALLOWED_COMPONENT_SORTKEYS:
        sortkey = "_id"

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
    return JSONResponse(status_code=200, content=items)


@router.get("/components/{component_id}", summary="Get component by id")
async def get_component(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str = "",
):
    coll = await comps(request)
    doc = await coll.find_one({"_id": component_id})
    if not doc:
        raise HTTPException(404, "Not found")
    return JSONResponse(status_code=200, content=doc)


@router.get(
    "/components/{component_id}/geometry",
    summary="Get component geometry"
)
async def get_component_geometry(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str = "",
):
    coll = await comps(request)
    doc = await coll.find_one({"_id": component_id}, {"geometry": 1})
    if not doc:
        raise HTTPException(404, "Not found")
    return JSONResponse(status_code=200, content=doc)


# -------- asset files on disk --------
def _ensure_file(path: str):
    if not os.path.exists(path):
        raise HTTPException(404, "File not found")
    return path


@router.get("/components/{component_id}/geometry_detailed")
async def get_component_geometry_detailed(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
):
    base = request.app.component_geometry_dir
    mesh_path = os.path.join(base, component_id, "mesh.obj")
    return FileResponse(
        _ensure_file(mesh_path),
        media_type="text/x-obj",
        filename="mesh.obj"
    )


@router.get("/components/{component_id}/material_detailed")
async def get_component_material_detailed(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
):
    base = request.app.component_geometry_dir
    mtl_path = os.path.join(base, component_id, "mesh.mtl")
    return FileResponse(
        _ensure_file(mtl_path),
        media_type="text/x-mtl",
        filename="mesh.mtl"
    )


@router.get("/components/{component_id}/geometry_reduced")
async def get_component_geometry_reduced(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
):
    base = request.app.component_geometry_dir
    mesh_path = os.path.join(base, component_id, "mesh_reduced.obj")
    return FileResponse(
        _ensure_file(mesh_path),
        media_type="text/x-obj",
        filename="mesh_reduced.obj"
    )


@router.get("/components/{component_id}/material_reduced")
async def get_component_material_reduced(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
):
    base = request.app.component_geometry_dir
    mtl_path = os.path.join(base, component_id, "mesh_reduced.mtl")
    return FileResponse(
        _ensure_file(mtl_path),
        media_type="text/x-mtl",
        filename="mesh_reduced.mtl"
    )


@router.get("/components/{component_id}/texture")
async def get_component_texture(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    component_id: str,
):
    base = request.app.component_geometry_dir
    texture_path = os.path.join(base, component_id, "texture.jpg")
    return FileResponse(
        _ensure_file(texture_path),
        media_type="image/jpeg",
        filename=f"{component_id}_texture.jpg"
    )


# -------- destructive op: ADMIN ONLY --------
@router.delete(
    "/components/{component_id}",
    summary="Delete component (admin only)"
)
async def delete_component(
    request: Request,
    admin_user=Depends(require_admin),
    component_id: str = "",
):
    coll = await comps(request)
    res = await coll.delete_one({"_id": component_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"ok": True}
