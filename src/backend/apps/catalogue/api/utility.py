#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os
from pathlib import Path

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import (APIRouter, # NOQA
                     Body,
                     HTTPException,
                     Request,
                     status,
                     Depends)
from fastapi.responses import PlainTextResponse

router = APIRouter()


# UTILITY ROUTES --------------------------------------------------------------
@router.get('/fastapi_log',
            response_description='Get FastAPI Backend log',
            response_class=PlainTextResponse)
async def get_fastapi_log(request: Request):
    backend_dir = os.path.normpath(
        os.path.abspath(str(Path(__file__).parents[3]))
    )
    fp = os.path.normpath(os.path.abspath(
        os.path.join(backend_dir, 'logs', 'fastapi.log')))
    try:
        with open(fp, 'r') as errorlog:
            lines = [line.rstrip() for line in errorlog]
        ptr = '\n'.join(lines[-200:])
        return ptr
    except FileNotFoundError:
        return 'No fastapi.log file found. No errors present.' + fp


@router.get('/previewgen_log',
            response_description='Get PreviewGen Cronjob log',
            response_class=PlainTextResponse)
async def get_previewgen_log(request: Request):
    backend_dir = os.path.normpath(
        os.path.abspath(str(Path(__file__).parents[3]))
    )
    fp = os.path.normpath(os.path.abspath(
        os.path.join(backend_dir, 'logs', 'previewgen_cronjob.log'))
    )
    try:
        with open(fp, 'r') as errorlog:
            lines = [line.rstrip() for line in errorlog]
        ptr = '\n'.join(lines[-200:])
        return ptr
    except FileNotFoundError:
        return 'No previewgen_cronjob.log file found. No errors present.' + fp
