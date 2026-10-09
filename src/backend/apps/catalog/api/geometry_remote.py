#!/usr/bin/env python3.13
"""
The geometry runner off the server (decisions 8.45, 8.51, 8.54).

The heavy stages (proxy fits, deviation maps, HKS, previews) may be too much
for the shared host, so ``main_geometry.py --remote`` pulls the snapshots
whose stages are stale, computes them on another machine and uploads the
results here. Admin only (a service account is an ordinary account with the
admin role).

    GET  /geometry/stale            which snapshots have stale stages
    GET  /geometry/work/{sid}       the snapshot, what the worker needs to
                                    run the stages, and the server's view of
                                    their inputs
    POST /geometry/results/{sid}    the derived fields + files; refused with
                                    409 when the source changed meanwhile

Why through the API and not into MongoDB: the derived files (deviation maps,
previews) live on this server's disk, and the server checks on upload that
the inputs the worker computed from still match the snapshot. The server
decides what a result may write (decision 8.54): only typed derived fields of
the stages it carries, never over an assigned value, the ``*_source`` fields
set by the server, a stage stamped only with a result or an error, and every
map file name derived here, never taken from the worker. The stamps are never
taken from the worker either: the server recomputes each stage's input
fingerprint from the stored snapshot with the results applied.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import asyncio
import json
from typing import Annotated, Any, Dict, List, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import ComponentSnapshot, Frame, Proxy, Vec3
from apps.catalog.geometry_runner import (
    build_update,
    commit_files,
    delete_files,
    discard_files,
    stage_files,
)
from apps.catalog.geometry_source import (
    source_fingerprint,
    stored_file_sizes,
    stored_files,
)
from apps.catalog.geometry_stages import (
    HULL_SCORES,
    LEGACY_FIELDS,
    STAGES,
    VERSIONS,
    Env,
    Outcome,
    now_z,
    stage_input,
    stale_stages,
)
from apps.catalog.models import User
from apps.catalog.vocab import ShapeClass
from apps.descriptors.registry import collect_output_keys
from apps.descriptors.specs import ALL_SPECS
from .auth import require_admin

router = APIRouter(tags=['geometry runner'])

HEAVY_STAGES = ('proxies', 'descriptors', 'complexity', 'previews')
MAX_RESULT_JSON_BYTES = 4 * 1024 * 1024
MAX_RESULT_FILE_BYTES = 8 * 1024 * 1024
MAX_RESULT_FILES = 600
ALLOWED_DESCRIPTORS = frozenset(collect_output_keys(ALL_SPECS)) \
    | frozenset(HULL_SCORES)
ERROR_LIMIT = 160
# what a stage must bring: the fields of its result, or an error
REQUIRED = {
    'frame': ('frame', 'bbx'),
    'shape_class': ('shape_class',),
    'proxies': ('fitted_proxies',),
    'descriptors': ('descriptors',),
    'complexity': ('complexity',),
    'previews': (),
}
FIELDS_OF_STAGE = {
    'frame': ('frame', 'bbx', 'descriptors'),
    'shape_class': ('shape_class',),
    'proxies': ('fitted_proxies',),
    'descriptors': ('descriptors',),
    'complexity': ('complexity',),
    'previews': (),
}


def _env(request: Request) -> Env:
    app = request.app
    return Env(meshes_dir=app.snapshot_meshes_dir,
               point_clouds_dir=app.snapshot_point_clouds_dir,
               preview_dir=app.snapshot_preview_dir)


def _stages(value: str) -> List[str]:
    stages = [s.strip() for s in value.split(',') if s.strip()]
    unknown = [s for s in stages if s not in STAGES]
    if unknown:
        raise HTTPException(status_code=422,
                            detail=f'unknown stages {unknown}')
    return stages


def context_of(snapshot: Dict[str, Any], identity: Dict[str, Any]
               ) -> Dict[str, Any]:
    """The inputs of the stages that are not geometry: what a worker
    computed from must still hold when it uploads."""
    return {
        'original_function': identity.get('original_function'),
        'shape_class_source': snapshot.get('shape_class_source'),
        'assigned_shape_class': snapshot.get('shape_class')
        if snapshot.get('shape_class_source') == 'assigned' else None,
        'complexity_source': snapshot.get('complexity_source'),
        'assigned_complexity': snapshot.get('complexity')
        if snapshot.get('complexity_source') == 'assigned' else None,
        'color': snapshot.get('color'),
    }


class RemoteSet(BaseModel):
    """The derived fields a worker may send, typed: a malformed body is a
    422, never a 500. ``*_source`` is not among them (the server sets it)."""
    model_config = ConfigDict(extra='forbid')

    frame: Optional[Frame] = None
    bbx: Optional[Vec3] = None
    shape_class: Optional[ShapeClass] = None
    complexity: Optional[int] = Field(None, ge=0, le=3)
    descriptors: Optional[Dict[str, Any]] = None
    fitted_proxies: Optional[List[Proxy]] = None


class RemoteResult(BaseModel):
    """What a worker uploads for one snapshot."""
    model_config = ConfigDict(extra='forbid')

    stages: List[str]
    source_fingerprint: str
    context: Dict[str, Any]
    versions: Dict[str, int]
    errors: Dict[str, str] = {}
    set: RemoteSet = RemoteSet()


async def _load(request: Request, snapshot_id: str):
    app = request.app
    snapshot = await app.mongodb_component_snapshots.find_one(
        {'_id': snapshot_id})
    if snapshot is None:
        raise HTTPException(status_code=404, detail='Snapshot not found')
    identity = await app.mongodb_component_identities.find_one(
        {'_id': snapshot['identity_id']})
    if identity is None:
        raise HTTPException(status_code=404, detail='Identity not found')
    return snapshot, identity


@router.get('/geometry/stale',
            summary='Snapshots with stale geometry stages (admin)')
async def list_stale(
    request: Request,
    _admin: Annotated[User, Depends(require_admin)],
    stages: str = Query(','.join(HEAVY_STAGES)),
    limit: int = Query(20, ge=1, le=200),
    after: Optional[str] = Query(None, description='continue after this id'),
    retry_errors: bool = Query(False, description='also stages that ended '
                                                  'in an error'),
):
    wanted = _stages(stages)
    env = _env(request)
    query = {'_id': {'$gt': after}} if after else {}
    cursor = request.app.mongodb_component_snapshots.find(query).sort(
        '_id', 1)
    identities: Dict[str, dict] = {}
    found: List[Dict[str, Any]] = []
    last = None
    async for snapshot in cursor:
        last = snapshot['_id']
        identity = identities.get(snapshot['identity_id'])
        if identity is None:
            identity = await request.app.mongodb_component_identities \
                .find_one({'_id': snapshot['identity_id']})
            if identity is None:
                continue
            identities[snapshot['identity_id']] = identity
        due = await asyncio.to_thread(stale_stages, snapshot, identity, env,
                                      wanted, retry_errors)
        if due:
            found.append({'snapshot_id': snapshot['_id'], 'stale': due})
        if len(found) >= limit:
            break
    return {'items': found, 'last': last}


@router.get('/geometry/failed',
            summary='Snapshots with failed geometry stages (admin)')
async def list_failed(
    request: Request,
    _admin: Annotated[User, Depends(require_admin)],
    limit: int = Query(200, ge=1, le=500),
):
    """Every snapshot that carries a stage error, with the stored (short)
    text per stage --- for the admin list (decision 8.60). Retry with
    ``POST /snapshots/{sid}/proxies/recompute``."""
    query = {'$or': [{f'derivation.{stage}.error': {'$type': 'string'}}
                     for stage in STAGES]}
    snapshots = request.app.mongodb_component_snapshots
    rows = await snapshots.find(
        query, {'derivation': 1, 'version': 1, 'status': 1, 'name': 1,
                'identity_id': 1}).sort('_id', 1).to_list(length=limit)
    numbers: Dict[str, Any] = {}
    async for identity in request.app.mongodb_component_identities.find(
            {'_id': {'$in': list({r['identity_id'] for r in rows})}},
            {'catalog_number': 1, 'dataset': 1}):
        numbers[identity['_id']] = identity
    return [{
        'snapshot_id': row['_id'], 'identity_id': row['identity_id'],
        'catalog_number': numbers.get(row['identity_id'], {}).get(
            'catalog_number'),
        'dataset': numbers.get(row['identity_id'], {}).get('dataset'),
        'version': row.get('version'), 'status': row.get('status'),
        'stages': {stage: stamp['error']
                   for stage, stamp in (row.get('derivation') or {}).items()
                   if stamp and stamp.get('error')},
    } for row in rows]


@router.get('/geometry/work/{snapshot_id}',
            summary='A snapshot with what a worker needs (admin)')
async def get_work(
    request: Request,
    snapshot_id: str,
    _admin: Annotated[User, Depends(require_admin)],
    stages: str = Query(','.join(HEAVY_STAGES)),
    retry_errors: bool = Query(False),
):
    snapshot, identity = await _load(request, snapshot_id)
    env = _env(request)
    return jsonable_encoder({
        'snapshot': snapshot,
        'identity': {'_id': identity['_id'],
                     'original_function': identity.get('original_function')},
        'source_fingerprint': await asyncio.to_thread(
            source_fingerprint, snapshot, env.meshes_dir,
            env.point_clouds_dir),
        'files': stored_files(snapshot, env.meshes_dir,
                              env.point_clouds_dir),
        # the same files with their sizes: the key of a cached result (8.122 f)
        'file_sizes': await asyncio.to_thread(
            stored_file_sizes, snapshot, env.meshes_dir,
            env.point_clouds_dir),
        'context': context_of(snapshot, identity),
        'stale': await asyncio.to_thread(
            stale_stages, snapshot, identity, env, _stages(stages),
            retry_errors),
        'versions': VERSIONS,
    })


def _check_result(result: RemoteResult, snapshot: Dict[str, Any],
                  identity: Dict[str, Any], env: Env) -> None:
    unknown = [s for s in result.stages if s not in STAGES]
    if unknown or len(set(result.stages)) != len(result.stages):
        raise HTTPException(status_code=422,
                            detail=f'unknown or repeated stages '
                                   f'{result.stages}')
    outdated = {s: v for s, v in result.versions.items()
                if s in result.stages and VERSIONS[s] != v}
    if outdated or any(s not in result.versions for s in result.stages):
        raise HTTPException(status_code=409, detail={
            'message': 'The worker runs other stage versions than this '
                       'server; update it.',
            'server_versions': VERSIONS, 'worker_versions': result.versions})
    if source_fingerprint(snapshot, env.meshes_dir,
                          env.point_clouds_dir) != result.source_fingerprint:
        raise HTTPException(status_code=409, detail={
            'message': 'The snapshot geometry changed while the worker '
                       'computed; the result is refused (recompute).',
            'reason': 'source'})
    if context_of(snapshot, identity) != result.context:
        raise HTTPException(status_code=409, detail={
            'message': 'Inputs of the stages changed (function, an assigned '
                       'class or complexity, colour); the result is refused '
                       '(recompute).', 'reason': 'context'})
    # an assigned value is never overwritten (8.54)
    for stage, source_key in (('shape_class', 'shape_class_source'),
                              ('complexity', 'complexity_source')):
        if stage in result.stages \
                and snapshot.get(source_key) == 'assigned':
            raise HTTPException(status_code=409, detail={
                'message': f'{stage} is assigned; it is never uploaded.',
                'reason': 'assigned'})
    brought = result.set.model_fields_set
    nulls = sorted(k for k in brought if getattr(result.set, k) is None)
    if nulls:
        raise HTTPException(status_code=422, detail={
            'message': 'A field is sent with a value or not at all.',
            'fields': nulls})
    authored_primary = any(
        p.get('role') == 'primary'
        and (p.get('fit') or {}).get('method') == 'authored'
        for p in (snapshot.get('geometry') or {}).get('proxies') or [])
    for stage in result.stages:
        if stage in result.errors:
            continue
        if not all(k in brought for k in REQUIRED[stage]):
            raise HTTPException(status_code=422, detail={
                'message': 'A stage is uploaded with its result or an '
                           'error, nothing else.', 'stage': stage})
        # no fitted proxy is a result only for a piece whose primary proxy
        # is authored (it is never refitted); else the fit failed
        if stage == 'proxies' and not result.set.fitted_proxies \
                and not authored_primary:
            raise HTTPException(status_code=422, detail={
                'message': 'No proxy is not a result of the proxies stage '
                           'unless the primary proxy is authored.',
                'stage': stage})
    allowed = {key for stage in result.stages
               for key in FIELDS_OF_STAGE[stage]}
    stray = sorted(result.set.model_fields_set - allowed)
    if stray:
        raise HTTPException(status_code=422, detail={
            'message': 'Fields outside the uploaded stages.',
            'fields': stray})
    if any(len(v) > ERROR_LIMIT for v in result.errors.values()) \
            or set(result.errors) - set(result.stages):
        raise HTTPException(status_code=422, detail='Malformed errors.')


def _apply(result: RemoteResult, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """The snapshot with the worker's results applied. The ``*_source``
    fields are set here: a stage that ran for real is ``derived``."""
    merged = dict(snapshot)
    fields = result.set
    skipped = set(result.errors)           # a failed stage brings no result
    if 'frame' in result.stages and 'frame' not in skipped:
        merged['frame'] = fields.frame.model_dump(mode='json')
        merged['bbx'] = list(fields.bbx)
    if 'shape_class' in result.stages and 'shape_class' not in skipped:
        merged['shape_class'] = fields.shape_class
        merged['shape_class_source'] = 'derived'
    if 'complexity' in result.stages and 'complexity' not in skipped:
        merged['complexity'] = fields.complexity
        merged['complexity_source'] = 'derived'
    if fields.descriptors is not None:
        bad = sorted(set(fields.descriptors) - ALLOWED_DESCRIPTORS)
        if bad:
            raise HTTPException(status_code=422, detail={
                'message': 'Unknown descriptors.', 'fields': bad})
        merged['descriptors'] = {**(merged.get('descriptors') or {}),
                                 **fields.descriptors}
    if 'proxies' in result.stages and 'proxies' not in skipped:
        geometry = dict(merged.get('geometry') or {})
        authored = [p for p in geometry.get('proxies') or []
                    if (p.get('fit') or {}).get('method') == 'authored']
        fitted = [p.model_dump(mode='json') for p in fields.fitted_proxies]
        if any((p.get('fit') or {}).get('method') == 'authored'
               for p in fitted):
            raise HTTPException(status_code=422,
                                detail='Authored proxies are never uploaded.')
        geometry['proxies'] = authored + fitted
        merged['geometry'] = geometry
    return merged


def expected_map_names(merged: Dict[str, Any], snapshot_id: str
                       ) -> Dict[str, str]:
    """``{face file: face}`` as the server derives them for every fitted
    proxy: ``proxies/<sid>/<index>/<face>.png`` --- compared exactly, the
    worker's names are never used as paths."""
    names: Dict[str, str] = {}
    for index, proxy in enumerate(
            (merged.get('geometry') or {}).get('proxies') or []):
        if (proxy.get('fit') or {}).get('method') == 'authored':
            continue
        for face, doc in ((proxy.get('deviation_maps') or {})
                          .get('faces') or {}).items():
            expected = f'proxies/{snapshot_id}/{index}/{face}.png'
            if doc.get('file') != expected:
                raise HTTPException(status_code=422, detail={
                    'message': 'A map file is not named as the server '
                               'names it.', 'face': face})
            names[expected] = face
    return names


@router.post('/geometry/results/{snapshot_id}',
             summary='Upload derived results of a worker (admin)')
async def post_results(
    request: Request,
    snapshot_id: str,
    _admin: Annotated[User, Depends(require_admin)],
):
    """Multipart: ``result`` (RemoteResult as JSON) and ``files`` (the
    deviation maps named ``proxies/<sid>/<i>/<face>.png``, and
    ``preview.webp``). Read here, not by declared form parameters, so that
    the size limits are explicit: Starlette's default of 1 MiB per part
    would answer a large hull with a 400 that names no cause."""
    try:
        form = await request.form(max_part_size=MAX_RESULT_JSON_BYTES,
                                  max_files=MAX_RESULT_FILES + 1)
    except Exception as exc:                               # noqa: BLE001
        raise HTTPException(status_code=413,
                            detail='The upload is too large.') from exc
    result = form.get('result')
    files = [f for f in form.getlist('files') if hasattr(f, 'read')]
    if not isinstance(result, str):
        raise HTTPException(status_code=422, detail='The result is missing.')
    if len(result.encode('utf-8')) > MAX_RESULT_JSON_BYTES:
        raise HTTPException(status_code=413, detail='The result is too large')
    if len(files) > MAX_RESULT_FILES:
        raise HTTPException(status_code=413, detail='Too many files')
    try:
        body = RemoteResult.model_validate(json.loads(result))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422,
                            detail='The result is malformed.') from exc
    snapshot, identity = await _load(request, snapshot_id)
    env = _env(request)
    _check_result(body, snapshot, identity, env)
    merged = _apply(body, snapshot)
    try:
        ComponentSnapshot.model_validate(merged)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise HTTPException(
            status_code=422,
            detail=f'{".".join(str(p) for p in first["loc"])}: '
                   f'{first["msg"]}') from exc

    named = expected_map_names(merged, snapshot_id) \
        if 'proxies' in body.stages and 'proxies' not in body.errors else {}
    outcome = Outcome()
    for upload in files:
        name = upload.filename or ''
        data = await upload.read(MAX_RESULT_FILE_BYTES + 1)
        if len(data) > MAX_RESULT_FILE_BYTES:
            raise HTTPException(status_code=413, detail='A file is too large')
        if name == 'preview.webp' and 'previews' in body.stages \
                and 'previews' not in body.errors:
            outcome.preview = data
        elif name in named:
            outcome.write_files[name] = data
        else:
            raise HTTPException(status_code=422,
                                detail='An unexpected file was uploaded.')
    missing = sorted(set(named) - set(outcome.write_files))
    if missing:
        raise HTTPException(status_code=422, detail={
            'message': 'Deviation maps named by the proxy are missing.',
            'count': len(missing)})
    if 'previews' in body.stages and 'previews' not in body.errors \
            and outcome.preview is None:
        raise HTTPException(status_code=422,
                            detail='The preview is missing.')

    # the server's own stamps: version of the worker's stage, input
    # recomputed here from the stored snapshot with the results applied
    derivation = dict(merged.get('derivation') or {})
    for stage in body.stages:
        derivation[stage] = {
            'version': VERSIONS[stage],
            'input': await asyncio.to_thread(
                stage_input, stage, merged, identity, env),
            'at': now_z(), 'error': body.errors.get(stage)}
        outcome.ran.append(stage)
    merged['derivation'] = derivation
    keys = {'derivation'}
    for stage in body.stages:
        if stage in body.errors:
            continue
        keys.update({'frame': ('frame', 'bbx', 'descriptors'),
                     'shape_class': ('shape_class', 'shape_class_source'),
                     'proxies': ('geometry',),
                     'descriptors': ('descriptors',),
                     'complexity': ('complexity', 'complexity_source'),
                     'previews': ()}[stage])
    if 'descriptors' in body.stages and body.set.descriptors is not None:
        keys.add('descriptors')      # a partial result stays, as on the cron
    outcome.set = {key: merged[key] for key in keys if key in merged}
    if 'frame' in body.stages and 'frame' not in body.errors:
        outcome.unset = [k for k in LEGACY_FIELDS if k in snapshot]
    if 'proxies' in body.stages and 'proxies' not in body.errors:
        outcome.delete_files = [
            face['file'] for proxy in (snapshot.get('geometry') or {})
            .get('proxies') or []
            if (proxy.get('fit') or {}).get('method') != 'authored'
            for face in ((proxy.get('deviation_maps') or {}).get('faces')
                         or {}).values() if face['file'] not in named]

    app = request.app
    pairs = await asyncio.to_thread(stage_files, outcome,
                                    app.snapshot_proxies_dir,
                                    app.snapshot_preview_dir, snapshot_id)
    try:
        written = await app.mongodb_component_snapshots.update_one(
            {'_id': snapshot_id, 'etag': snapshot.get('etag')},
            build_update(snapshot, outcome))
    except BaseException:
        discard_files(pairs)
        raise
    if written.matched_count == 0:
        discard_files(pairs)
        raise HTTPException(status_code=409, detail={
            'message': 'The snapshot changed while the result was stored; '
                       'recompute.', 'reason': 'concurrent'})
    await asyncio.to_thread(commit_files, pairs)
    await asyncio.to_thread(delete_files, outcome, app.snapshot_proxies_dir)
    return {'ok': True, 'snapshot_id': snapshot_id, 'stages': body.stages}
