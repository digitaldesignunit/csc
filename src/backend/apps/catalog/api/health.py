#!/usr/bin/env python3.13

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Request
from pymongo.errors import PyMongoError

# LOCAL MODULE IMPORTS --------------------------------------------------------
from csc_version import CSC_VERSION, release_tag


# INIT ROUTER -----------------------------------------------------------------
router = APIRouter()


# ROUTES ----------------------------------------------------------------------
@router.get('/version', summary='CSC version of this backend (public)')
async def get_version():
    """The product version and its release tag; used by the deploy health check."""
    return {'version': CSC_VERSION, 'tag': release_tag()}


@router.get('/health/db', summary='Check MongoDB connection')
async def health_check_db(request: Request):
    try:
        await request.app.mongodb.command('ping')
        return {'ok': True}
    except PyMongoError as e:
        return {'ok': False, 'error': str(e)}
