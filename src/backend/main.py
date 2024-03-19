#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os
import json


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------

from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient


from apps.catalogue.routers import router as catalogue_router


# UTILITY ---------------------------------------------------------------------

def sanitize_path(fp: str = '') -> str:
    """Sanitizes a filepath an returns the result."""
    return os.path.abspath(os.path.realpath(os.path.normpath(fp)))


# ENVIRONMENT SETTINGS --------------------------------------------------------

_HERE = os.path.dirname(sanitize_path(__file__))
"""str: Path to directory of this particular file."""

_CONFIGFILE = sanitize_path(os.path.join(_HERE, "dbconfig.json"))
"""str: Default configuration file."""


# UTILITY ---------------------------------------------------------------------

def __get_db_connectionstring():
    with open(_CONFIGFILE, 'r') as configfile:
        # Reading from json file
        dbconfig = json.load(configfile)
        server = dbconfig['server']
        user = dbconfig['user']
        pwd = dbconfig['pwd']
    # compose mongodb connection string
    cstr = f'mongodb+srv://{user}:{pwd}@{server}'
    return cstr


# FASTAPI INSTANCE ------------------------------------------------------------

app = FastAPI(
    title='Catalogue of Second Chances API',
    description='CSC API to handle MongoDB stuff',
    version='0.0.1'
)


# EVENTS ----------------------------------------------------------------------

@app.on_event('startup')
async def startup_db_client():
    app.mongodb_client = AsyncIOMotorClient(__get_db_connectionstring())
    app.mongodb = app.mongodb_client['csc']


@app.on_event('shutdown')
async def shutdown_db_client():
    app.mongodb_client.close()


# ROUTER ----------------------------------------------------------------------

app.include_router(catalogue_router, tags=['catalogue'], prefix='')
