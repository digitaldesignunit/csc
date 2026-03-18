#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

import asyncio
import os
import shutil
from typing import List, Tuple


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------

from pymongo import AsyncMongoClient


# LOCAL MODULE IMPORTS --------------------------------------------------------

from utility import (
    get_db_connectionstring,
    get_geometry_directory,
    create_logging_timestamp as logts
)


async def initialize_geometry_maintenance() -> Tuple[List[str], List[str]]:
    """
    Initialize geometry maintenance by comparing component ids in database
    with geometry subdirectories in geometry directory.
    Return list of geometry subdirs that have no id equivalent in the db.
    """
    # initialize geometry directory
    geometry_dir = get_geometry_directory()
    # try to create directory if it does not exist
    os.makedirs(geometry_dir, exist_ok=True)
    # read all subdirectory names in directory and create set from it
    geometry_subdirs = set()
    for dir_name in os.listdir(geometry_dir):
        dir_path = os.path.join(geometry_dir, dir_name)
        if os.path.isdir(dir_path):
            geometry_subdirs.add(dir_name)
    # set up database client and select collections
    mongodb_client = AsyncMongoClient(
        get_db_connectionstring()
    )
    mongodb = mongodb_client['csc']
    mongodb_components = mongodb['components']
    # retrieve all component ids from database and create set
    component_ids = {
        str(c['_id']) async for c in mongodb_components.find({}, {'_id': 1})
    }
    # compare both sets and find geometry subdirs with no component in database
    stale_geometry_ids = list(geometry_subdirs - component_ids)
    # close mongodb client
    await mongodb_client.close()
    # return list of stale geometry ids
    return stale_geometry_ids


if __name__ == '__main__':
    geometry_dir = get_geometry_directory()
    stale_geometry_ids = asyncio.run(
        initialize_geometry_maintenance()
    )
    if stale_geometry_ids:
        # delete all stale geometry subdirectories and their contents
        for comp_id in stale_geometry_ids:
            dir_path = os.path.join(geometry_dir, comp_id)
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                shutil.rmtree(dir_path)
                ts = logts()
                print(f'[GEOMMAINT] {ts} Deleted stale geometry subdirectory '
                      f'for {comp_id}.')
    else:
        ts = logts()
        print(f'[GEOMMAINT] {ts} No stale geometry subdirectories found.')
