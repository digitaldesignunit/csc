#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

import asyncio
import os
from typing import List


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------

from motor.motor_asyncio import AsyncIOMotorClient


# LOCAL MODULE IMPORTS --------------------------------------------------------

from utility import (
    sanitize_path,
    get_db_connectionstring,
    get_preview_directory
)
from apps.previewgen import create_component_preview


# ENVIRONMENT SETTINGS --------------------------------------------------------

_HERE = os.path.dirname(sanitize_path(__file__))
"""str: Path to directory of this particular file."""

_CONFIG_DIR = sanitize_path(os.path.join(_HERE, "config"))

_CONFIGFILE = sanitize_path(os.path.join(_CONFIG_DIR, "dbconfig.json"))
"""str: Default configuration file."""


async def initialize_preview_generation() -> List[str]:
    """
    Initialize preview generation by comparing component ids in database with
    preview images in preview directory. Return list of missing previews.
    """
    # initialize preview generation directory
    preview_dir = get_preview_directory(_CONFIGFILE)
    # try to create directory if it does not exist
    os.makedirs(preview_dir, exist_ok=True)
    # read all file names in directory and create set from it
    preview_images = set()
    for file_name in os.listdir(preview_dir):
        if os.path.isfile(os.path.join(preview_dir, file_name)):
            preview_images.add(os.path.splitext(file_name)[0])
    # set up database client and select collections
    mongodb_client = AsyncIOMotorClient(
        get_db_connectionstring(_CONFIGFILE)
    )
    mongodb = mongodb_client['csc']
    mongodb_components = mongodb['components']
    # mongodb_models = mongodb['models']
    # retrieve all component ids from database and create set
    component_ids = set()
    async for component in mongodb_components.find({}, {'_id': 1}):
        component_ids.add(str(component['_id']))
    # compare both sets and find component ids with missing previews
    missing_preview_ids = list(component_ids - preview_images)
    # for all missing preview ids, retrieve type, materialthickness and
    # geometry from database
    missing_preview_components = []
    projection = {'type': 1, 'materialthickness': 1, 'geometry': 1}
    for comp_id in missing_preview_ids:
        component = await mongodb_components.find_one(
            {'_id': comp_id},
            projection
        )
        missing_preview_components.append(component)
    # close mongodb client
    mongodb_client.close()
    # return list of missing preview ids
    return missing_preview_components


if __name__ == '__main__':
    preview_dir = get_preview_directory(_CONFIGFILE)
    missing_preview_components = asyncio.run(initialize_preview_generation())
    if not missing_preview_components:
        print('[PREVIEWGEN] All previews are present.')
    else:
        print(f'[PREVIEWGEN] Found {len(missing_preview_components)} '
              'missing previews.')
        # call preview generation for every missing preview id
        for component_data in missing_preview_components:
            print('[PREVIEWGEN] Generating preview for '
                  f'{component_data["_id"]}')
            # call preview generation function
            create_component_preview(
                component_data=component_data,
                preview_dir=preview_dir,
                output_filename=component_data['_id'],
                image_size=800)
            print('[PREVIEWGEN] Preview for '
                  f'{component_data["_id"]} generated.')
