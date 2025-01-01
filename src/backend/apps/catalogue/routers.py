#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from datetime import timedelta
import os
from pathlib import Path
from typing import Annotated, List


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import (APIRouter, # NOQA
                     Body,
                     HTTPException,
                     Request,
                     status,
                     Depends)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, PlainTextResponse, FileResponse
from fastapi.security import OAuth2PasswordRequestForm


# LOCAL MODULE IMPORTS --------------------------------------------------------
from .models import (ALLOWED_COMPONENT_TYPES, # NOQA
                     ALLOWED_COMPONENT_SORTKEYS,
                     Token,
                     TokenData,
                     User,
                     UserInDB,
                     ComponentModel,
                     UpdateComponentModel)
from .auth import (ACCESS_TOKEN_EXPIRE_MINUTES,
                   authenticate_user,
                   create_access_token,
                   get_current_active_user,
                   )


# INIT ROUTER -----------------------------------------------------------------

# create router instance
router = APIRouter()


# AUTH ------------------------------------------------------------------------

@router.post("/token")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    user = authenticate_user(form_data.username,
                             form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="Bearer")


# STATISTIC ROUTES ------------------------------------------------------------

@router.get('/componentcount',
            response_description='Count all components')
async def count_components(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)]):
    count = await request.app.mongodb_components.count_documents({})
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=count)


# ADD COMPONENT ROUTES --------------------------------------------------------

@router.post('/', response_description='Add one new component')
async def create_component(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        component: ComponentModel = Body(...)) -> ComponentModel:
    component = jsonable_encoder(component)
    collection = request.app.mongodb_components
    new_component = await collection.insert_one(component)
    created_component = await collection.find_one(
        {'_id': new_component.inserted_id}
    )
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content=created_component)


# VALIDATION ROUTES -----------------------------------------------------------

@router.get('/validate/{component_id}',
            response_description='Validate Component')
async def validate_component(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        component_id: str) -> ComponentModel:
    collection = request.app.mongodb_components
    component = await collection.find_one({'_id': component_id})
    if component['validated'] is False:
        result = await collection.update_one({'_id': component_id},
                                             {'$set': {'validated': True}})
        print(f'{result.modified_count} was successfully validated!')
    updated_component = await collection.find_one({'_id': component_id})
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=updated_component)


# SHALLOW COMPONENT ROUTES ----------------------------------------------------

@router.get('/shallowcomponents/{component_id}',
            response_description='Retrieve one shallow component by id')
async def get_component_shallow(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        component_id: str) -> ComponentModel:
    collection = request.app.mongodb_components
    query = {'_id': component_id}
    projection = {'geometry': 0, 'descriptors': 0}
    component = await collection.find_one(query, projection)
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=component)


@router.get('/shallowcomponents',
            response_description='Retrieve multiple shallow components')
async def get_components_shallow(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        page: int = 0,
        size: int = 0,
        sortkey: str = '_id',
        comptype: str = '',
        material: str = '',
        validated: int = 1) -> List[ComponentModel]:
    # get database
    db = request.app.mongodb_components
    # compose filter query and set sort order
    query = {}
    projection = {'geometry': 0, 'descriptors': 0}
    sort_order = 1
    # filter component type
    if comptype and comptype in ALLOWED_COMPONENT_TYPES:
        query.update({'type': comptype})
    # filter material
    if material:
        query.update({'material': material})
    # check to only get validated components
    if validated == 1:
        query.update({'validated': True})
    elif validated == -1:
        query.update({'validated': False})
    if not sortkey or sortkey not in ALLOWED_COMPONENT_SORTKEYS:
        sortkey = '_id'
    # execute query either to get all components or to get a paginated subset
    if not page and not size:
        components = []
        async for doc in db.find(query, projection).sort(sortkey, sort_order):
            components.append(doc)
    else:
        components = (
            await db.find(query, projection)
            .sort(sortkey, sort_order)
            .skip((page - 1) * size if page > 0 else 0)
            .limit(size)
            .to_list(size)
        )
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=components)


# COMPONENT ROUTES ------------------------------------------------------------

@router.get('/components',
            response_description='Retrieve multiple components')
async def get_components(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        page: int = 0,
        size: int = 0,
        sortkey: str = '_id',
        comptype: str = '',
        material: str = '',
        validated: int = 1) -> List[ComponentModel]:
    # get database
    db = request.app.mongodb_components
    # compose filter query and set sort order
    query = {}
    sort_order = 1
    # filter component type
    if comptype and comptype in ALLOWED_COMPONENT_TYPES:
        query.update({'type': comptype})
    # filter material
    if material:
        query.update({'material': material})
    # check to only get validated components
    if validated == 1:
        query.update({'validated': True})
    elif validated == -1:
        query.update({'validated': False})
    if not sortkey or sortkey not in ALLOWED_COMPONENT_SORTKEYS:
        sortkey = '_id'
    # execute query either to get all components or to get a paginated subset
    if not page and not size:
        components = []
        async for doc in db.find(query).sort(sortkey, sort_order):
            components.append(doc)
    else:
        components = (
            await db.find(query)
            .sort(sortkey, sort_order)
            .skip((page - 1) * size if page > 0 else 0)
            .limit(size)
            .to_list(size)
        )
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=components)


@router.get('/components/{component_id}',
            response_description='Retrieve one component by id')
async def get_component(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        component_id: str) -> ComponentModel:
    collection = request.app.mongodb_components
    component = await collection.find_one({'_id': component_id})
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=component)


# COMPONENT DETAIL ROUTES -----------------------------------------------------

@router.get('/components/{component_id}/geometry',
            response_description='Retrieve one components geometry by id')
async def get_component_geometry(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        component_id: str) -> ComponentModel:
    collection = request.app.mongodb_components
    query = {'_id': component_id}
    projection = {'geometry': 1}
    component = await collection.find_one(query, projection)
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=component)


@router.get('/components/{component_id}/geometry_detailed',
            response_description='Retrieve one components detailed '
                                 'geometry by id')
async def get_component_geometry_detailed(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        component_id: str) -> FileResponse:
    """
    Fetch the mesh.obj file for a component by component_id.
    The path to the mesh file is: {geometry_dir}/{component_id}/mesh.obj
    """
    # Grab the base directory for geometry files from your FastAPI app config
    geometry_dir = request.app.component_geometry_dir
    # Build the path to mesh.obj
    mesh_path = os.path.join(geometry_dir, component_id, 'mesh.obj')
    # Check if the file exists
    if not os.path.exists(mesh_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=('Mesh (mesh.obj) file not found '
                    f'for component {component_id}')
        )
    # Return the .obj file
    return FileResponse(
        path=mesh_path,
        media_type='text/x-obj',
        filename='mesh.obj'
    )


@router.get('/components/{component_id}/material_detailed',
            response_description='Retrieve one components detailed '
                                 'material .mtl file by id')
async def get_component_material_detailed(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        component_id: str) -> FileResponse:
    """
    Fetch the mesh.mtl file for a component by component_id.
    The path to the mesh file is: {geometry_dir}/{component_id}/mesh.mtl
    """
    # Grab the base directory for geometry files from your FastAPI app config
    geometry_dir = request.app.component_geometry_dir
    # Build the path to mesh.obj
    mtl_path = os.path.join(geometry_dir, component_id, 'mesh.mtl')
    # Check if the file exists
    if not os.path.exists(mtl_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=('Material (.mtl) file not found for '
                    f'component {component_id}')
        )
    # Return the .obj file
    return FileResponse(
        path=mtl_path,
        media_type='text/x-mtl',
        filename='mesh.mtl'
    )


@router.get('/components/{component_id}/geometry_reduced',
            response_description='Retrieve one components reduced mesh '
                                 'geometry by id')
async def get_component_geometry_reduced(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        component_id: str) -> FileResponse:
    """
    Fetch the mesh_reduced.obj file for a component by component_id.
    The path to the mesh file is:
    {geometry_dir}/{component_id}/mesh_reduced.obj
    """
    # Grab the base directory for geometry files from your FastAPI app config
    geometry_dir = request.app.component_geometry_dir
    # Build the path to mesh_reduced.obj
    mesh_path = os.path.join(geometry_dir, component_id, 'mesh_reduced.obj')
    # Check if the file exists
    if not os.path.exists(mesh_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=('Reduced mesh (mesh_reduced.obj) file not found'
                    f'for component {component_id}')
        )
    # Return the .obj file
    return FileResponse(
        path=mesh_path,
        media_type='text/x-obj',
        filename='mesh_reduced.obj'
    )


@router.get('/components/{component_id}/material_reduced',
            response_description='Retrieve one components reduced material '
                                 '.mtl file by id')
async def get_component_material_reduced(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        component_id: str) -> FileResponse:
    """
    Fetch the mesh_reduced.mtl file for a component by component_id.
    The path to the mesh file is:
    {geometry_dir}/{component_id}/mesh_reduced.mtl
    """
    # Grab the base directory for geometry files from your FastAPI app config
    geometry_dir = request.app.component_geometry_dir
    # Build the path to mesh_reduced.mtl
    mtl_path = os.path.join(geometry_dir, component_id, 'mesh_reduced.mtl')
    # Check if the file exists
    if not os.path.exists(mtl_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=('Reduced material (.mtl) file not found for '
                    f'component {component_id}')
        )
    # Return the .obj file
    return FileResponse(
        path=mtl_path,
        media_type='text/x-mtl',
        filename='mesh_reduced.mtl'
    )


@router.get('/components/{component_id}/texture',
            response_description='Retrieve one components texture.jpg '
                                 'file by id')
async def get_component_texture(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        component_id: str) -> FileResponse:
    """
    Fetch the mesh.mtl file for a component by component_id.
    The path to the mesh file is: {geometry_dir}/{component_id}/texture.jpg
    """
    # Grab the base directory for geometry files from your FastAPI app config
    geometry_dir = request.app.component_geometry_dir
    # Build the path to mesh.obj
    texture_path = os.path.join(geometry_dir, component_id, 'texture.jpg')
    # Check if the file exists
    if not os.path.exists(texture_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=('Texture (.jpg) file not found for '
                    f'component {component_id}')
        )
    # Return the .obj file
    return FileResponse(
        path=texture_path,
        media_type='image/jpeg',
        filename=f'{component_id}_texture.jpg'
    )


@router.get('/components/{component_id}/descriptors',
            response_description='Retrieve one components descriptors by id')
async def get_component_descriptors(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        component_id: str) -> ComponentModel:
    collection = request.app.mongodb_components
    query = {'_id': component_id}
    projection = {'descriptors': 1}
    component = await collection.find_one(query, projection)
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=component)


# UTILITY ROUTES --------------------------------------------------------------

@router.get('/fastapi_log',
            response_description='Get FastAPI Backend log',
            response_class=PlainTextResponse)
async def get_fastapi_log(request: Request):
    csc_dir = os.path.normpath(os.path.abspath(str(Path(__file__).parents[2])))
    fp = os.path.normpath(os.path.abspath(
        os.path.join(csc_dir, 'logs', 'fastapi.log')))
    try:
        with open(fp, 'r') as errorlog:
            lines = [line.rstrip() for line in errorlog]
        ptr = '\n'.join(lines[-200:])
        return ptr
    except FileNotFoundError:
        return 'No fastapi.log file found. No errors present.' + fp


@router.get('/previewgen_log',
            response_description='Get PreviewGen Cronjob log',
            response_class=PlainTextResponse)
async def get_previewgen_log(request: Request):
    csc_dir = os.path.normpath(os.path.abspath(str(Path(__file__).parents[2])))
    fp = os.path.normpath(os.path.abspath(
        os.path.join(csc_dir, 'logs', 'previewgen_cronjob.log'))
    )
    try:
        with open(fp, 'r') as errorlog:
            lines = [line.rstrip() for line in errorlog]
        ptr = '\n'.join(lines[-200:])
        return ptr
    except FileNotFoundError:
        return 'No previewgen_cronjob.log file found. No errors present.' + fp
