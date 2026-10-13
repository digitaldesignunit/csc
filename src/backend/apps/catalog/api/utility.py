#!/usr/bin/env python3.13

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os
import re
from pathlib import Path
from typing import Annotated

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from apps.catalog.models import User
from .auth import require_admin

# INIT ROUTER -----------------------------------------------------------------
router = APIRouter()
_BACKEND_DIR = os.path.normpath(
    os.path.abspath(str(Path(__file__).parents[3]))
)


def _logs_dir() -> str:
    return os.path.join(_BACKEND_DIR, 'logs')


def _latest_dated_log(stem: str) -> str:
    """The newest ``<stem>.<YYYY-MM-DD>.log`` in the logs folder: the cron
    jobs write one file a day (decision 8.144 h); the file without a date is
    what older crontabs wrote, used when there is no dated one."""
    pattern = re.compile(rf'^{re.escape(stem)}\.\d{{4}}-\d{{2}}-\d{{2}}\.log$')
    try:
        dated = sorted(name for name in os.listdir(_logs_dir())
                       if pattern.match(name))
    except OSError:
        dated = []
    return dated[-1] if dated else f'{stem}.log'


def _read_last_log_lines(log_filename: str, line_count: int) -> str:
    fp = os.path.normpath(os.path.abspath(
        os.path.join(_logs_dir(), log_filename))
    )
    try:
        with open(fp, 'r') as errorlog:
            lines = [line.rstrip() for line in errorlog]
        return '\n'.join(lines[-line_count:])
    except FileNotFoundError:
        # the name only: the answer must not show where the logs live
        return f'No {log_filename} file found. No errors present.'


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


@router.get('/geometry_log',
            response_description='Get Geometry Runner Cronjob log',
            response_class=PlainTextResponse)
async def get_geometry_cronjob_log(
    request: Request,
    _admin_user: Annotated[User, Depends(require_admin)],
    lines: Annotated[int, Query(ge=1, le=5000)] = 200,
):
    del request, _admin_user
    return _read_last_log_lines(_latest_dated_log('geometry_cronjob'), lines)


@router.get('/component_map_log',
            response_description='Get Component Map Cronjob log',
            response_class=PlainTextResponse)
async def get_component_map_cronjob_log(
    request: Request,
    _admin_user: Annotated[User, Depends(require_admin)],
    lines: Annotated[int, Query(ge=1, le=5000)] = 200,
):
    del request, _admin_user
    return _read_last_log_lines(_latest_dated_log('component_map_cronjob'), lines)
