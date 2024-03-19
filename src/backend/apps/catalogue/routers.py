from fastapi import APIRouter, Body, HTTPException, Request, status # NOQA
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from .models import ComponentModel, UpdateComponentModel # NOQA

# create router instance
router = APIRouter()


@router.post('/', response_description='Add new component')
async def create_component(request: Request,
                           component: ComponentModel = Body(...)):
    component = jsonable_encoder(component)
    collection = request.app.mongodb['components']
    new_component = await collection.insert_one(component)
    created_component = await collection.find_one(
        {'_id': new_component.inserted_id}
    )
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content=created_component)


@router.get('/', response_description='Retrieve all components')
async def get_all_components(request: Request):
    components = []
    async for doc in request.app.mongodb.components.find():
        components.append(doc)
    return components
