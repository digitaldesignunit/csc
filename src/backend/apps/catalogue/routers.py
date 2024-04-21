#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from datetime import timedelta
import os
from pathlib import Path
from typing import Annotated


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import (APIRouter, # NOQA
                     Body,
                     HTTPException,
                     Request,
                     status,
                     Depends)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, PlainTextResponse, HTMLResponse
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
from utility import plot_polyline_to_html
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


# MAIN ROUTES -----------------------------------------------------------------

@router.post('/', response_description='Add one new component')
async def create_component(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        component: ComponentModel = Body(...)):
    component = jsonable_encoder(component)
    collection = request.app.mongodb_components
    new_component = await collection.insert_one(component)
    created_component = await collection.find_one(
        {'_id': new_component.inserted_id}
    )
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content=created_component)


@router.get('/validate/{component_id}',
            response_description='Validate Component')
async def validate_component(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        component_id: str):
    collection = request.app.mongodb_components
    component = await collection.find_one({'_id': component_id})
    if component['validated'] is False:
        result = await collection.update_one({'_id': component_id},
                                             {'$set': {'validated': True}})
        print(f'{result.modified_count} was successfully validated!')
    updated_component = await collection.find_one({'_id': component_id})
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=updated_component)


@router.get('/components/{component_id}',
            response_description='Retrieve one component by id')
async def get_component(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        component_id: str):
    collection = request.app.mongodb_components
    component = await collection.find_one({'_id': component_id})
    return JSONResponse(component)


@router.get('/components',
            response_description='Retrieve multiple components')
async def get_components(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)],
        page: int = 0,
        size: int = 0,
        sortkey: str = '_id',
        comptype: str = '',
        validated: int = 1):
    # get database
    db = request.app.mongodb_components
    # compose filter query and set sort order
    filter_q = {}
    sort_order = 1
    # filter component type
    if comptype and comptype in ALLOWED_COMPONENT_TYPES:
        filter_q.update({'type': comptype})
    # check to only get validated components
    if validated == 1:
        filter_q.update({'validated': True})
    elif validated == -1:
        filter_q.update({'validated': False})
    if not sortkey or sortkey not in ALLOWED_COMPONENT_SORTKEYS:
        sortkey = '_id'
    # execute query either to get all components or to get a paginated subset
    if not page and not size:
        components = []
        async for doc in db.find(filter_q).sort(sortkey, sort_order):
            components.append(doc)
        return components
    else:
        return (
            await db.find(filter_q)
            .sort(sortkey, sort_order)
            .skip((page - 1) * size if page > 0 else 0)
            .limit(size)
            .to_list(size)
        )


@router.get('/componentcount',
            response_description='Count all components')
async def count_components(
        request: Request,
        current_user: Annotated[User, Depends(get_current_active_user)]):
    count = await request.app.mongodb_components.count_documents({})
    return count


# UTILITY ROUTES --------------------------------------------------------------

@router.get('/errorlog',
            response_description='Get error log',
            response_class=PlainTextResponse)
async def get_error_log(request: Request):
    csc_dir = os.path.normpath(os.path.abspath(str(Path(__file__).parents[2])))
    fp = os.path.normpath(os.path.join(csc_dir, 'errors.log'))
    try:
        with open(fp, 'r') as errorlog:
            lines = [line.rstrip() for line in errorlog]
        ptr = '\n'.join(lines[-200:])
        return ptr
    except FileNotFoundError:
        return 'No errors.log file found. No errors present.'


@router.get('/preview',
            response_description='Preview datasets from database.',
            response_class=HTMLResponse)
async def get_preview(request: Request):
    images = []
    i = 0
    async for doc in request.app.mongodb_components.find().sort('_id', 1):
        if i + 1 >= 20:
            break
        image_html = plot_polyline_to_html(
                                coordinates=doc['geometry']['polyline'],
                                name=doc['_id'],
                                scalefactor=0.1)
        images.append(image_html)
        i += 1
    resp = '<br>'.join(images)
    return HTMLResponse(resp)
