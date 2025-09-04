#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os
import json
from contextlib import asynccontextmanager


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import AsyncMongoClient


# LOCAL MODULE IMPORTS --------------------------------------------------------
from utility import (
    sanitize_path,
    get_cors_origins,
    get_db_connectionstring,
    get_preview_directory,
    get_geometry_directory,
)


# ENVIRONMENT SETTINGS --------------------------------------------------------
_HERE = os.path.dirname(sanitize_path(__file__))
_CONFIG_DIR = sanitize_path(os.path.join(_HERE, 'config'))
_CONFIGFILE = sanitize_path(os.path.join(_CONFIG_DIR, 'dbconfig.json'))


def load_jwt_secret(config_path: str) -> str:
    with open(config_path, 'r', encoding='utf-8-sig') as f:
        cfg = json.load(f)
    secret = str(cfg['secret'])
    return secret.replace('\r', '').replace('\n', '').strip()


# FASTAPI SETUP ---------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Load config (secret, algorithm, expiry) once ------------------------
    with open(_CONFIGFILE, 'r') as f:
        cfg = json.load(f)
    app.state.jwt_secret = cfg['secret'].strip()
    app.state.jwt_algorithm = cfg.get('algorithm', 'HS256').strip()
    app.state.jwt_access_minutes = int(
        cfg.get('access_token_expire_minutes', 30)
    )

    # --- MongoDB -------------------------------------------------------------
    app.mongodb_client = AsyncMongoClient(
        get_db_connectionstring(_CONFIGFILE),
        serverSelectionTimeoutMS=5000,
    )
    await app.mongodb_client.aconnect()
    await app.mongodb_client.admin.command('ping')

    app.mongodb = app.mongodb_client['csc']
    app.mongodb_users = app.mongodb['users']
    app.mongodb_components = app.mongodb['components']
    app.mongodb_designs = app.mongodb['designs']

    # Create helpful indexes (idempotent)
    await app.mongodb_users.create_index('email', unique=True)
    await app.mongodb_users.create_index('username', unique=True)

    # --- Directories ---------------------------------------------------------
    app.component_preview_dir = get_preview_directory(_CONFIGFILE)
    app.component_geometry_dir = get_geometry_directory(_CONFIGFILE)

    yield

    # shutdown
    if app.mongodb_client:
        await app.mongodb_client.close()


app = FastAPI(
    title='CSC - Catalogue of Second Chances - Backend API',
    description=(
        'Backend API for Catalogue of Second Chances. '
        'FastAPI + MongoDB (async).'
    ),
    version='0.2.9.0',
    lifespan=lifespan,
)

# CORS ------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(_CONFIGFILE),
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# ROUTERS ---------------------------------------------------------------------
# New, modern router structure under apps/catalogue/api/*
from apps.catalogue.api import api_router  # NOQA - aggregator for sub-routers
app.include_router(api_router, prefix='')
