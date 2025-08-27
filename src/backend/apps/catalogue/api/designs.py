#!/usr/bin/env python3.9
import os
from typing import Annotated, Optional

# THIRD PARTY MODULE IMPORTS --------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.encoders import jsonable_encoder
from pymongo.errors import PyMongoError

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.catalogue.models import (  # NOQA
    ALLOWED_COMPONENT_SORTKEYS,
    ComponentCount,
    ComponentDescriptors,
    ComponentModel,
    UpdateComponentModel,
    User,
)
from .auth import get_current_active_user, require_admin


# INIT ROUTER -----------------------------------------------------------------

# create router instance
router = APIRouter()


# FASTAPI DEPENDENCIES --------------------------------------------------------

async def get_designs_col(request: Request):
    return request.app.mongodb_designs

