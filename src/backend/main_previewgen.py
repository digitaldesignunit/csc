#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

import asyncio
import os
from typing import List, Tuple


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------

from motor.motor_asyncio import AsyncIOMotorClient


# LOCAL MODULE IMPORTS --------------------------------------------------------

from utility import (
    sanitize_path,
    get_db_connectionstring,
    get_preview_directory,
    create_logging_timestamp as logts
)
from apps.previewgen import (
    create_component_preview_image,
    crop_preview_whitespace,
    save_preview_image
)


# ENVIRONMENT SETTINGS --------------------------------------------------------

_HERE = os.path.dirname(sanitize_path(__file__))
"""str: Path to directory of this particular file."""

_CONFIG_DIR = sanitize_path(os.path.join(_HERE, "config"))

_CONFIGFILE = sanitize_path(os.path.join(_CONFIG_DIR, "dbconfig.json"))
"""str: Default configuration file."""


async def initialize_preview_generation() -> Tuple[List[dict], List[str]]:
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
    stale_preview_ids = list(preview_images - component_ids)
    # for all missing preview ids, retrieve type, materialthickness and
    # geometry from database
    missing_preview_components = []
    projection = {
        'type': 1,
        'materialthickness': 1,
        'geometry': 1,
        'color': 1}
    for comp_id in missing_preview_ids:
        component = await mongodb_components.find_one(
            {'_id': comp_id},
            projection
        )
        missing_preview_components.append(component)
    # close mongodb client
    mongodb_client.close()
    # return list of missing preview ids
    return missing_preview_components, stale_preview_ids


if __name__ == '__main__':
    preview_dir = get_preview_directory(_CONFIGFILE)
    missing_preview_components, stale_preview_ids = asyncio.run(
        initialize_preview_generation()
    )
    if not missing_preview_components:
        print('[PREVIEWGEN] No stale preview images found.')
    else:
        # delete all stale preview images
        for comp_id in stale_preview_ids:
            os.remove(os.path.join(preview_dir, f'{comp_id}.webp'))
            print(f'[PREVIEWGEN] {logts()} Deleted stale preview image '
                  f'for {comp_id}.')
    if not missing_preview_components:
        print('[PREVIEWGEN] {logts()} All previews are present.')
    else:
        print(f'[PREVIEWGEN] {logts()} Found {len(missing_preview_components)}'
              ' missing previews.')
        # call preview generation for every missing preview id
        for component_data in missing_preview_components:
            print(f'[PREVIEWGEN] {logts()} Generating preview for '
                  f'{component_data["_id"]}')
            # call preview generation function
            save_preview_image(
                crop_preview_whitespace(
                    create_component_preview_image(
                        component_data=component_data,
                        size=800
                        ),
                    padding=2
                ),
                folder=preview_dir,
                filename=component_data['_id']
            )
            print(f'[PREVIEWGEN] {logts()} Preview for '
                  f'{component_data["_id"]} generated.')
