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
from fastapi.responses import JSONResponse, PlainTextResponse
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
            response_description='Retrieve one component by id')
async def get_component_shallow(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        component_id: str) -> ComponentModel:
    collection = request.app.mongodb_components
    query = {'_id': component_id}
    projection = {'geometry': 0}
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
        validated: int = 1) -> List[ComponentModel]:
    # get database
    db = request.app.mongodb_components
    # compose filter query and set sort order
    query = {}
    projection = {'geometry': 0}
    sort_order = 1
    # filter component type
    if comptype and comptype in ALLOWED_COMPONENT_TYPES:
        query.update({'type': comptype})
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
        validated: int = 1) -> List[ComponentModel]:
    # get database
    db = request.app.mongodb_components
    # compose filter query and set sort order
    query = {}
    sort_order = 1
    # filter component type
    if comptype and comptype in ALLOWED_COMPONENT_TYPES:
        query.update({'type': comptype})
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

@router.get('/componentgeometry/{component_id}',
            response_description='Retrieve one component geometry by id')
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


# UTILITY ROUTES --------------------------------------------------------------

@router.get('/fastapi_log',
            response_description='Get FastAPI Backend log',
            response_class=PlainTextResponse)
async def get_fastapi_log(request: Request):
    csc_dir = os.path.normpath(os.path.abspath(str(Path(__file__).parents[2])))
    fp = os.path.normpath(os.path.join(csc_dir, '/logs/fastapi.log'))
    try:
        with open(fp, 'r') as errorlog:
            lines = [line.rstrip() for line in errorlog]
        ptr = '\n'.join(lines[-200:])
        return ptr
    except FileNotFoundError:
        return 'No fastapi.log file found. No errors present.'


@router.get('/previewgen_log',
            response_description='Get PreviewGen Cronjob log',
            response_class=PlainTextResponse)
async def get_previewgen_log(request: Request):
    csc_dir = os.path.normpath(os.path.abspath(str(Path(__file__).parents[2])))
    fp = os.path.normpath(
        os.path.join(csc_dir, '/logs/previewgen_cronjob.log')
    )
    try:
        with open(fp, 'r') as errorlog:
            lines = [line.rstrip() for line in errorlog]
        ptr = '\n'.join(lines[-200:])
        return ptr
    except FileNotFoundError:
        return 'No previewgen_cronjob.log file found. No errors present.'
