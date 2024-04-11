#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

import os
import json
from contextlib import asynccontextmanager


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient


# LOCAL MODULE IMPORTS --------------------------------------------------------

from apps.catalogue.routers import router as catalogue_router
from utility import sanitize_path


# ENVIRONMENT SETTINGS --------------------------------------------------------

_HERE = os.path.dirname(sanitize_path(__file__))
"""str: Path to directory of this particular file."""

_CONFIG_DIR = sanitize_path(os.path.join(_HERE, "config"))

_CONFIGFILE = sanitize_path(os.path.join(_CONFIG_DIR, "dbconfig.json"))
"""str: Default configuration file."""


# CONFIG LOADING --------------------------------------------------------------

def __get_db_connectionstring():
    """
    Read MongoDB connection string from config file.
    """
    with open(_CONFIGFILE, 'r') as configfile:
        # Reading from json file
        dbconfig = json.load(configfile)
        server = dbconfig['server']
        user = dbconfig['user']
        pwd = dbconfig['pwd']
    # compose mongodb connection string
    cstr = f'mongodb+srv://{user}:{pwd}@{server}'
    return cstr


def __get_cors_origins():
    """
    Read CORS origins from config file.
    """
    with open(_CONFIGFILE, 'r') as configfile:
        # Reading from json file
        dbconfig = json.load(configfile)
        origins = dbconfig['origins']
    return origins


# FASTAPI SETUP ---------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    app.mongodb_client = AsyncIOMotorClient(__get_db_connectionstring())
    app.mongodb = app.mongodb_client['csc']
    app.mongodb_components = app.mongodb['components']
    app.mongodb_users = app.mongodb['users']
    yield
    # shutdown
    app.mongodb_client.close()

# Create FastAPI instance
app = FastAPI(
    title='Catalogue of Second Chances API',
    description='CSC API to handle MongoDB stuff',
    version='0.0.3',
    lifespan=lifespan
)

# Add CORS Origins to FastAPI instance
app.add_middleware(
    CORSMiddleware,
    allow_origins=__get_cors_origins(),
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*']
)


# ROUTER ----------------------------------------------------------------------

app.include_router(catalogue_router, tags=['catalogue'], prefix='')
