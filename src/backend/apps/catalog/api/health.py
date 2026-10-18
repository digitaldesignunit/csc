#!/usr/bin/env python3.13

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

# LOCAL MODULE IMPORTS --------------------------------------------------------
import read_only
from csc_version import CSC_VERSION, release_tag

from logging_setup import get_logger

log = get_logger(__name__)


# INIT ROUTER -----------------------------------------------------------------
router = APIRouter()


# ROUTES ----------------------------------------------------------------------
@router.get('/version', summary='CSC version of this backend (public)')
async def get_version():
    """The product version and its release tag (used by the deploy health
    check) and whether the read-only flag is set (decision 8.154; the web app
    shows its banner from this)."""
    return {'version': CSC_VERSION, 'tag': release_tag(),
            'read_only': read_only.is_on()}


@router.get('/health/db', summary='Check MongoDB connection')
async def health_check_db(request: Request):
    try:
        await request.app.mongodb.command('ping')
        return {'ok': True, 'read_only': read_only.is_on()}
    except PyMongoError:
        # the driver's text names hosts and can name accounts: the log only
        log.exception('health check')
        return JSONResponse(status_code=503, content={'ok': False})
