#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os
from pathlib import Path
from typing import Annotated

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import (APIRouter, # NOQA
                     Depends,
                     Query,
                     Request)
from fastapi.responses import PlainTextResponse
from apps.catalog.models import User
from .auth import require_admin

# INIT ROUTER -----------------------------------------------------------------
router = APIRouter()


def _read_last_log_lines(log_filename: str, line_count: int) -> str:
    backend_dir = os.path.normpath(
        os.path.abspath(str(Path(__file__).parents[3]))
    )
    fp = os.path.normpath(os.path.abspath(
        os.path.join(backend_dir, 'logs', log_filename))
    )
    try:
        with open(fp, 'r') as errorlog:
            lines = [line.rstrip() for line in errorlog]
        return '\n'.join(lines[-line_count:])
    except FileNotFoundError:
        return f'No {log_filename} file found. No errors present.{fp}'


# UTILITY ROUTES --------------------------------------------------------------
@router.get('/fastapi_log',
            response_description='Get FastAPI Backend log',
            response_class=PlainTextResponse)
async def get_fastapi_log(
    request: Request,
    _admin_user: Annotated[User, Depends(require_admin)],
    lines: Annotated[int, Query(ge=1, le=5000)] = 200,
):
    del request, _admin_user
    return _read_last_log_lines('fastapi.log', lines)


@router.get('/previewgen_log',
            response_description='Get PreviewGen Cronjob log',
            response_class=PlainTextResponse)
async def get_previewgen_log(
    request: Request,
    _admin_user: Annotated[User, Depends(require_admin)],
    lines: Annotated[int, Query(ge=1, le=5000)] = 200,
):
    del request, _admin_user
    return _read_last_log_lines('previewgen_cronjob.log', lines)


@router.get('/descriptors_simple_log',
            response_description='Get Descriptors Simple Cronjob log',
            response_class=PlainTextResponse)
async def get_descriptors_simple_cronjob_log(
    request: Request,
    _admin_user: Annotated[User, Depends(require_admin)],
    lines: Annotated[int, Query(ge=1, le=5000)] = 200,
):
    del request, _admin_user
    return _read_last_log_lines('descriptors_simple_cronjob.log', lines)


@router.get('/descriptor_log',
            response_description='Get Descriptor Cronjob log',
            response_class=PlainTextResponse)
async def get_descriptor_log(
    request: Request,
    _admin_user: Annotated[User, Depends(require_admin)],
    lines: Annotated[int, Query(ge=1, le=5000)] = 200,
):
    del request, _admin_user
    return _read_last_log_lines('descriptors_simple_cronjob.log', lines)
