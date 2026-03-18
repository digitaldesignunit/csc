#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os
import sys
from contextlib import asynccontextmanager


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import AsyncMongoClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# LOCAL IMPORTS (pre-app) -----------------------------------------------------
from limiter import limiter


# LOCAL MODULE IMPORTS --------------------------------------------------------
from utility import (
    get_cors_origins,
    get_db_connectionstring,
    get_preview_directory,
    get_geometry_directory,
    get_geometry_archive_directory,
    get_gh_xml_cache_directory,
)


# STARTUP VALIDATION ----------------------------------------------------------
_REQUIRED_ENV = [
    'MONGODB_URI',
    'JWT_SECRET',
    'GITHUB_REPO_URL',
    'GITHUB_CSC_GH_TOKEN',
    'SMTP_HOST',
    'SMTP_USER',
    'SMTP_PASSWORD',
    'SMTP_FROM_EMAIL',
    'FRONTEND_URL',
    'PREVIEW_DIR',
    'GEOMETRY_DIR',
    'GEOMETRY_ARCHIVE_DIR',
    'GH_XML_CACHE_DIR',
    'FASTAPI_CORS_ORIGINS',
]

_missing = [v for v in _REQUIRED_ENV if not os.getenv(v)]
if _missing:
    print(
        f'[FATAL] Missing required environment variables: {_missing}',
        file=sys.stderr,
    )
    sys.exit(1)


# FASTAPI SETUP ---------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- JWT config ----------------------------------------------------------
    app.state.jwt_secret = os.environ['JWT_SECRET']
    app.state.jwt_algorithm = os.getenv('JWT_ALGORITHM', 'HS256')
    app.state.jwt_access_minutes = int(
        os.getenv('JWT_ACCESS_TOKEN_EXPIRE_MINUTES', '30')
    )

    # --- MongoDB -------------------------------------------------------------
    app.mongodb_client = AsyncMongoClient(
        get_db_connectionstring(),
        serverSelectionTimeoutMS=5000,
    )
    await app.mongodb_client.aconnect()
    await app.mongodb_client.admin.command('ping')

    app.mongodb = app.mongodb_client['csc']
    app.mongodb_users = app.mongodb['users']
    app.mongodb_components = app.mongodb['components']
    app.mongodb_components_archived = app.mongodb['components_archive']
    app.mongodb_designs = app.mongodb['designs']

    # Create helpful indexes (idempotent)
    await app.mongodb_users.create_index('email', unique=True)
    await app.mongodb_users.create_index('username', unique=True)

    # --- Directories ---------------------------------------------------------
    app.component_preview_dir = get_preview_directory()
    app.component_geometry_dir = get_geometry_directory()
    app.component_geometry_archive_dir = get_geometry_archive_directory()
    app.gh_xml_cache_dir = get_gh_xml_cache_directory()

    yield

    # shutdown
    if app.mongodb_client:
        await app.mongodb_client.close()


app = FastAPI(
    title='CSC - Catalog of Second Chances - Backend API',
    description=(
        'Backend API for Catalog of Second Chances. '
        'FastAPI + MongoDB (async).'
    ),
    version='0.4.3.0',
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS ------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# ROUTERS ---------------------------------------------------------------------
# New, modern router structure under apps/catalog/api/*
from apps.catalog.api import api_router  # NOQA - aggregator for sub-routers
app.include_router(api_router, prefix='')
