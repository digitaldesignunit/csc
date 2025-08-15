#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

import os
from contextlib import asynccontextmanager


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import AsyncMongoClient


# LOCAL MODULE IMPORTS --------------------------------------------------------

from apps.catalogue.routers import router as catalogue_router
from utility import (
    sanitize_path,
    get_cors_origins,
    get_db_connectionstring,
    get_preview_directory,
    get_geometry_directory
)


# ENVIRONMENT SETTINGS --------------------------------------------------------

_HERE = os.path.dirname(sanitize_path(__file__))
"""str: Path to directory of this particular file."""

_CONFIG_DIR = sanitize_path(os.path.join(_HERE, "config"))

_CONFIGFILE = sanitize_path(os.path.join(_CONFIG_DIR, "dbconfig.json"))
"""str: Default configuration file."""


# FASTAPI SETUP ---------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    app.mongodb_client = AsyncMongoClient(
        get_db_connectionstring(_CONFIGFILE),
        serverSelectionTimeoutMS=5000
    )

    # Explicit connect + ping to fail early if DB is unavailable
    await app.mongodb_client.aconnect()
    await app.mongodb_client.admin.command("ping")

    app.mongodb = app.mongodb_client['csc']
    app.mongodb_components = app.mongodb['components']
    app.mongodb_users = app.mongodb['users']
    app.mongodb_models = app.mongodb['models']

    app.component_preview_dir = get_preview_directory(_CONFIGFILE)
    app.component_geometry_dir = get_geometry_directory(_CONFIGFILE)

    yield

    # shutdown
    if app.mongodb_client:
        await app.mongodb_client.close()

# Create FastAPI instance
app = FastAPI(
    title='CSC - Catalogue of Second Chances - Backend API',
    description=('Backend API for Catalogue of Second Chances. '
                 'Based on FastAPI, connected to MongoDB Database.'),
    version='0.1.0.12',
    lifespan=lifespan
)

# Add CORS Origins to FastAPI instance
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(_CONFIGFILE),
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*']
)


# ROUTER ----------------------------------------------------------------------

app.include_router(catalogue_router, tags=['catalogue'], prefix='')
