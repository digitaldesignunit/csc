#!/usr/bin/env python3.13

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os
import sys
from contextlib import asynccontextmanager


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo import AsyncMongoClient
from pymongo.errors import (
    AutoReconnect,
    ConnectionFailure,
    NetworkTimeout,
    ServerSelectionTimeoutError,
)
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# LOCAL IMPORTS (pre-app) -----------------------------------------------------
from limiter import shared_limiter, use_store
from apps.catalog.body_limit import BodyLimitMiddleware
from apps.catalog.client_header import (
    ClientHeaderEnforcementMiddleware,
    ClientHeaderLogMiddleware,
    configure_client_log,
    parse_min_versions,
)
from apps.catalog.api.catalog_common import (
    ensure_catalog_number_counter,
    seed_materials,
)
from apps.catalog.api.access import TombstoneHit
from csc_version import CSC_VERSION
from logging_setup import configure as configure_logging, get_logger


# LOCAL MODULE IMPORTS --------------------------------------------------------
from utility import (
    get_cors_origins,
    get_db_connectionstring,
    get_database_name,
    get_snapshot_preview_directory,
    get_snapshot_photos_directory,
    get_snapshot_meshes_directory,
    get_snapshot_point_clouds_directory,
    get_snapshot_proxies_directory,
    get_snapshot_capture_directory,
    get_evidence_attachments_directory,
    get_evidence_upload_limit_bytes,
    get_snapshot_photo_upload_limit_bytes,
    get_snapshot_photo_max_output_bytes,
    get_snapshot_photo_max_long_edge_px,
    get_gh_xml_cache_directory,
    get_geometry_upload_limit_bytes,
)


# STARTUP VALIDATION ----------------------------------------------------------
# One settings object (decision 8.156): a missing or bad variable stops the
# start here, with its name and never its value.
from apps.catalog.geometry_runner import DUE_INDEX  # noqa: E402
from settings import SettingsError, get_settings  # noqa: E402
try:
    settings = get_settings().require_api()
    parse_min_versions(settings.csc_min_client_versions)
except (SettingsError, ValueError) as _exc:
    sys.exit(f'[FATAL] {_exc}')

log = get_logger(__name__)


# FASTAPI SETUP ---------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings)

    # --- Client identification log (X-CSC-Client, spec section 7.4) ---------------
    configure_client_log(settings.client_log_path)
    # minimum client versions (decision 8.11); unset = log only
    app.state.min_client_versions = parse_min_versions(
        settings.csc_min_client_versions)
    if app.state.min_client_versions:
        log.info('Client header enforced: %s', settings.csc_min_client_versions)

    # --- JWT config ----------------------------------------------------------
    app.state.jwt_secret = settings.jwt_secret.get_secret_value()
    app.state.jwt_access_minutes = settings.jwt_access_token_expire_minutes

    # --- Rate limit counters (decision 8.152) ----------------------------------
    use_store(settings)

    # --- MongoDB -------------------------------------------------------------
    app.mongodb_client = AsyncMongoClient(
        get_db_connectionstring(),
        serverSelectionTimeoutMS=5000,
        maxPoolSize=20,
    )
    await app.mongodb_client.aconnect()
    await app.mongodb_client.admin.command('ping')

    app.mongodb = app.mongodb_client[get_database_name()]
    app.mongodb_users = app.mongodb['users']
    app.mongodb_component_id_transmission = app.mongodb[
        'component_id_transmission'
    ]
    app.mongodb_component_identities = app.mongodb['component_identities']
    app.mongodb_component_snapshots = app.mongodb['component_snapshots']
    app.mongodb_component_map_cache = app.mongodb['component_map_cache']
    app.mongodb_component_evidence = app.mongodb['component_evidence']
    app.mongodb_counters = app.mongodb['counters']
    app.mongodb_datasets = app.mongodb['datasets']
    app.mongodb_purged_records = app.mongodb['purged_records']
    app.mongodb_invitations = app.mongodb['invitations']
    app.mongodb_materials = app.mongodb['materials']
    app.mongodb_change_log = app.mongodb['change_log']

    # Create helpful indexes (idempotent)
    await app.mongodb_users.create_index('email', unique=True)
    await app.mongodb_users.create_index('username', unique=True)
    # verification links are looked up by the hash of their token (S10)
    await app.mongodb_users.create_index('verification_token_sha256',
                                         sparse=True)
    await app.mongodb_datasets.create_index('members.user_id')
    await app.mongodb_invitations.create_index('code_sha256', unique=True)
    await app.mongodb_invitations.create_index('email')
    await app.mongodb_change_log.create_index([('record_id', 1), ('at', 1)])
    await app.mongodb_change_log.create_index([('identity_id', 1), ('at', -1)])
    await app.mongodb_component_snapshots.create_index(
        'derivation_due', name='derivation_due_marked',
        partialFilterExpression=DUE_INDEX['partialFilterExpression'])
    await app.mongodb_component_evidence.create_index('identity_id')
    await app.mongodb_component_evidence.create_index(
        [('status', 1), ('method', 1)])
    await app.mongodb_component_evidence.create_index('supersedes')
    await app.mongodb_component_evidence.create_index(
        'payload.sampling.paired_rebound_id', sparse=True)
    await seed_materials(app.mongodb_materials)
    await ensure_catalog_number_counter(app.mongodb)

    # --- Directories ---------------------------------------------------------
    app.snapshot_preview_dir = get_snapshot_preview_directory()
    app.snapshot_photos_dir = get_snapshot_photos_directory()
    app.snapshot_meshes_dir = get_snapshot_meshes_directory()
    app.snapshot_point_clouds_dir = get_snapshot_point_clouds_directory()
    # deviation maps (proxies/<snapshot_id>/<i>/<face>.png, spec 3.5) and
    # capture fixtures (decision 7.7), both written by the geometry runner
    app.snapshot_proxies_dir = get_snapshot_proxies_directory()
    app.snapshot_capture_dir = get_snapshot_capture_directory()
    # evidence attachments (evidence/<id>/<index>.<ext>, spec 3.5, 7.3)
    app.evidence_attachments_dir = get_evidence_attachments_directory()
    app.evidence_upload_limit_bytes = get_evidence_upload_limit_bytes()
    app.snapshot_photo_upload_limit_bytes = (
        get_snapshot_photo_upload_limit_bytes()
    )
    app.snapshot_photo_max_output_bytes = (
        get_snapshot_photo_max_output_bytes()
    )
    app.snapshot_photo_max_long_edge_px = (
        get_snapshot_photo_max_long_edge_px()
    )
    os.makedirs(app.snapshot_preview_dir, exist_ok=True)
    os.makedirs(app.snapshot_photos_dir, exist_ok=True)
    os.makedirs(app.snapshot_meshes_dir, exist_ok=True)
    os.makedirs(app.snapshot_point_clouds_dir, exist_ok=True)
    os.makedirs(app.snapshot_proxies_dir, exist_ok=True)
    os.makedirs(app.snapshot_capture_dir, exist_ok=True)
    os.makedirs(app.evidence_attachments_dir, exist_ok=True)
    app.gh_xml_cache_dir = get_gh_xml_cache_directory()
    app.geometry_upload_limit_bytes = get_geometry_upload_limit_bytes()
    log.info('Geometry upload limit: %d MB',
             app.geometry_upload_limit_bytes // (1024 * 1024))

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
    version=CSC_VERSION,
    lifespan=lifespan,
)
app.state.limiter = shared_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


async def _tombstone_handler(request, exc):
    """A withdrawn record seen from outside its dataset (8.17)."""
    return JSONResponse(status_code=200, content=exc.body)


app.add_exception_handler(TombstoneHit, _tombstone_handler)

DB_UNAVAILABLE_RETRY_SECONDS = 5


async def _db_unavailable_handler(request, exc):
    """The database cannot be reached (a dropped connection after the host
    slept, an Atlas hiccup): 503 with Retry-After, so a client knows to try
    again, and the traceback in the log instead of an anonymous 500. The log
    line names the route template and never the path (it can hold ids typed
    by users)."""
    route = request.scope.get('route')
    log.error('database unavailable: %s %s', request.method,
              getattr(route, 'path', '-'), exc_info=exc)
    return JSONResponse(
        status_code=503,
        headers={'Retry-After': str(DB_UNAVAILABLE_RETRY_SECONDS)},
        content={'detail': 'The database is not available; try again in a '
                           'few seconds.'})


for _error in (AutoReconnect, ServerSelectionTimeoutError, NetworkTimeout,
               ConnectionFailure):
    app.add_exception_handler(_error, _db_unavailable_handler)

# Innermost: refuses outdated / unidentified clients with 426 (decision 8.11);
# inside CORS so a refusal still carries CORS headers
app.add_middleware(ClientHeaderEnforcementMiddleware)

# Request bodies are capped before a route reads them (decision 8.163); inside
# CORS, so the 413 carries the CORS headers
app.add_middleware(BodyLimitMiddleware)

# CORS ------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=['GET', 'POST', 'PATCH', 'PUT', 'DELETE'],
    allow_headers=['*'],
)

# Outermost: logs every request's X-CSC-Client header, refusals included
app.add_middleware(ClientHeaderLogMiddleware)

# ROUTERS ---------------------------------------------------------------------
# New, modern router structure under apps/catalog/api/*
from apps.catalog.api import api_router  # NOQA - aggregator for sub-routers
app.include_router(api_router, prefix='')
