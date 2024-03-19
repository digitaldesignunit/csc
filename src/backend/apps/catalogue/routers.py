import os
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request, status # NOQA
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, PlainTextResponse

from .models import ComponentModel, UpdateComponentModel # NOQA

# create router instance
router = APIRouter()


@router.post('/', response_description='Add new component')
async def create_component(request: Request,
                           component: ComponentModel = Body(...)):
    component = jsonable_encoder(component)
    collection = request.app.mongodb_components
    new_component = await collection.insert_one(component)
    created_component = await collection.find_one(
        {'_id': new_component.inserted_id}
    )
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content=created_component)


@router.get('/', response_description='Retrieve all components')
async def get_all_components(request: Request):
    components = []
    async for doc in request.app.mongodb_components.find():
        components.append(doc)
    return components


@router.get('/errorlog',
            response_description='Get error log',
            response_class=PlainTextResponse)
async def get_error_log(request: Request):
    csc_dir = os.path.normpath(os.path.abspath(str(Path(__file__).parents[2])))
    fp = os.path.normpath(os.path.join(csc_dir, 'errors.log'))
    try:
        with open(fp, 'r') as errorlog:
            lines = [line.rstrip() for line in errorlog]
        ptr = '\n'.join(lines)
        return ptr
    except FileNotFoundError:
        return 'No errors.log file found. No errors present.'
