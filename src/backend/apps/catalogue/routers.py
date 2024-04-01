# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import base64
import io
import os
from pathlib import Path


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------

from fastapi import APIRouter, Body, HTTPException, Request, status # NOQA
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, PlainTextResponse, HTMLResponse

import matplotlib.pyplot as plt

# LOCAL MODULE IMPORTS --------------------------------------------------------

from .models import ComponentModel, UpdateComponentModel # NOQA


# UTILITY ---------------------------------------------------------------------

def mm_to_inches(mm):
    """Convert millimeters to inches."""
    return mm / 25.4


def plot_polyline_to_html(coordinates,
                          name='Polyline from Coordinates',
                          image_width_mm=1500,
                          image_height_mm=1500,
                          scalefactor=0.1,
                          pixel_width=350):
    """
    Plot a polyline based on a list of [x, y] coordinates and returns HTML
    markup displaying the generated image. Image dimensions are specified in
    millimeters and can be resized to a specific pixel width.

    Args:
    - coordinates (list of lists): A list where each element is a list of
      [x, y] coordinates.
    - image_width_mm (int, optional): Width of the output image in millimeters.
      Defaults to 200.
    - image_height_mm (int, optional): Height of the output image in
      millimeters. Defaults to 100.
    - pixel_width (int, optional): Desired width of the output image in pixels
      for resizing.

    Returns:
    - A string containing HTML markup for displaying the generated image.
    """
    # Convert mm dimensions to inches for matplotlib
    image_width_in = mm_to_inches(image_width_mm * scalefactor)
    image_height_in = mm_to_inches(image_height_mm * scalefactor)

    # If pixel_width is specified, calculate DPI to maintain the desired width
    dpi = 96  # Default DPI
    if pixel_width is not None:
        dpi = pixel_width / image_width_in

    coordinates = [[c[0] * scalefactor, c[1] * scalefactor]
                   for c in coordinates]

    # Create the figure with the specified dimensions
    fig, ax = plt.subplots(figsize=(image_width_in, image_height_in), dpi=dpi)
    x_values, y_values = zip(*coordinates)
    ax.plot(x_values, y_values, marker='o')
    ax.set_title(name)
    ax.set_xlabel('X Coordinate')
    ax.set_ylabel('Y Coordinate')

    # Save the plot to a bytes buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig)  # Close the figure to free up memory

    # Encode the buffer to Base64 and decode to UTF-8 for HTML embedding
    img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    html = f'<img src="data:image/png;base64,{img_base64}"/>'

    return html


# INIT ROUTER -----------------------------------------------------------------

# create router instance
router = APIRouter()


# MAIN ROUTES -----------------------------------------------------------------

@router.get('/',
            response_description='Retrieve all components')
async def get_all_components_base(request: Request):
    components = []
    # loop over all components in async loop to avoid to_list call with limit
    async for doc in request.app.mongodb_components.find().sort('_id', 1):
        components.append(doc)
    return components


@router.post('/', response_description='Add one new component')
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


@router.get('/components/{component_id}',
            response_description='Retrieve one component by id')
async def get_component(request: Request, component_id: str):
    collection = request.app.mongodb_components
    component = await collection.find_one({'_id': component_id})
    return JSONResponse(component)


@router.get('/components',
            response_description='Retrieve all components')
async def get_all_components(request: Request,
                             page: int = 0,
                             size: int = 0):
    if not page and not size:
        components = []
        # loop over all components in async loop
        # to avoid to_list call with limit
        async for doc in request.app.mongodb_components.find().sort('_id', 1):
            components.append(doc)
        return components
    else:
        return (
            await request.app.mongodb_components.find()
            .sort('_id', 1)
            .skip((page - 1) * size)
            .limit(size)
            .to_list(size)
        )


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
        ptr = '\n'.join(lines)
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
                                coordinates=doc['geometry'][0],
                                name=doc['_id'],
                                scalefactor=0.1)
        images.append(image_html)
        i += 1
    resp = '<br>'.join(images)
    return HTMLResponse(resp)
