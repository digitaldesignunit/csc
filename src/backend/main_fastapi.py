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
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# LOCAL IMPORTS (pre-app) -----------------------------------------------------
from limiter import limiter
from apps.catalog.client_header import (
    MIN_VERSIONS_ENV,
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
_REQUIRED_ENV = [
    'MONGODB_URI',
    'JWT_SECRET',
    'GITHUB_REPO_URL',
    'SMTP_HOST',
    'SMTP_USER',
    'SMTP_PASSWORD',
    'SMTP_FROM_EMAIL',
    'FRONTEND_URL',
    'SNAPSHOT_PREVIEW_DIR',
    'SNAPSHOT_PHOTOS_DIR',
    'SNAPSHOT_MESHES_DIR',
    'SNAPSHOT_POINT_CLOUDS_DIR',
    'SNAPSHOT_PROXIES_DIR',
    'SNAPSHOT_CAPTURE_DIR',
    'EVIDENCE_ATTACHMENTS_DIR',
    'GH_XML_CACHE_DIR',
    'FASTAPI_CORS_ORIGINS',
]

# a bad CSC_GEOMETRY_HEAVY_STAGES fails here, not at the first recompute
from apps.catalog.geometry_stages import heavy_stages_where  # noqa: E402
from apps.catalog.geometry_runner import DUE_INDEX  # noqa: E402
try:
    heavy_stages_where()
except ValueError as _exc:
    print(f'[ERROR] {_exc}')
    sys.exit(1)

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
    # --- Client identification log (X-CSC-Client, spec section 7.4) ---------------
    configure_client_log(os.getenv(
        'CLIENT_LOG_PATH',
        os.path.join(os.path.dirname(__file__), 'logs', 'client_versions.log'),
    ))
    # minimum client versions (decision 8.11); unset = log only
    app.state.min_client_versions = parse_min_versions(
        os.getenv(MIN_VERSIONS_ENV))
    if app.state.min_client_versions:
        print(f'[INFO] Client header enforced: '
              f'{os.getenv(MIN_VERSIONS_ENV)}')

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
    print(
        f'[INFO] Geometry upload limit: '
        f'{app.geometry_upload_limit_bytes // (1024 * 1024)} MB'
    )

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
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


async def _tombstone_handler(request, exc):
    """A withdrawn record seen from outside its dataset (8.17)."""
    return JSONResponse(status_code=200, content=exc.body)


app.add_exception_handler(TombstoneHit, _tombstone_handler)

# Innermost: refuses outdated / unidentified clients with 426 (decision 8.11);
# inside CORS so a refusal still carries CORS headers
app.add_middleware(ClientHeaderEnforcementMiddleware)

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
