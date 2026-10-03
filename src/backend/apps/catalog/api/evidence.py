#!/usr/bin/env python3.13
"""
Evidence: create, bulk, read, list, introspection, properties and the
timeline (data model spec section 3.3, 4.1, 4.4, 7.1, 7.2; plan P6).

* ``POST /identities/{id}/evidence`` --- one record, a draft (or pending with
  ``?submit=1``); ``POST /evidence/bulk`` --- several, all or none
* ``GET /identities/{id}/evidence``, ``GET /evidence``, ``GET /evidence/
  pending``, ``GET /evidence/{id}`` (ETag / 304, ``?as_of=``)
* ``GET /evidence/methods``, ``GET /evidence/quantities``, the JSON Schemas
* ``GET /identities/{id}/properties``, ``GET /snapshots/{sid}/properties``
* ``GET /identities/{id}/timeline``

The lifecycle, corrections and verification are in ``evidence_lifecycle``,
attachments in ``evidence_attachments``.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import hashlib
from typing import Annotated, Any, Dict, List, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pymongo.errors import PyMongoError

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.evidence.projection import (
    evidence_tombstone,
    project_evidence,
)
from apps.catalog.evidence.registry import (
    SPEC_BY_NAME,
    describe_method,
    describe_quantities,
)
from apps.catalog.models import User
from apps.catalog.permissions import dataset_roles, withdrawn_projection
from apps.catalog.properties import contexts_for
from apps.catalog.read_models import Tombstone
from apps.catalog.timeline import build_timeline
from apps.catalog.vocab import STATUSES, SOURCE_TIERS, VerificationState
from .access import (
    and_match,
    dataset_of,
    ensure_identity_visible,
    ensure_snapshot_visible,
    identity_ever_published,
    load_datasets,
    load_identity,
    viewer_of,
    visible_identity_match,
    visible_snapshot_docs,
)
from .auth import get_current_active_user, get_optional_current_user
from .catalog_common import (
    not_modified_response,
    validate_uuid,
)
from .evidence_fold import evidence_fold_view
from .evidence_service import (
    EvidenceBulk,
    EvidenceCreate,
    EvidenceView,
    VerificationBody,
    ReasonBody,
    client_data,
    evidence_body,
    ensure_evidence_visible,
    projector as _projector,
    require_contributor,
    gate_identity,
    new_evidence_doc,
    prepare,
    viewer_context,
)

router = APIRouter()

DEFAULT_PAGE = 100
MAX_PAGE = 500


# INTROSPECTION ---------------------------------------------------------------
@router.get('/evidence/methods',
            summary='The evidence methods with their payload schemas')
async def list_methods():
    """The registry (spec 4.5): per method its tier, standard, headline
    quantities, derived-result models and the JSON Schema of its payload.
    The field descriptions are the help texts of the web form."""
    return JSONResponse(status_code=200, content=[
        describe_method(spec) for spec in SPEC_BY_NAME.values()])


@router.get('/evidence/quantities',
            summary='The quantity vocabulary with units and mappings')
async def list_quantities():
    """Units (canonical and accepted), scope, tier ranking, closed value
    lists and the mapping columns of spec 7.8."""
    return JSONResponse(status_code=200, content=describe_quantities())


# CODEGEN ---------------------------------------------------------------------
class PropertiesView(BaseModel):
    identity_id: str
    as_of: Optional[str] = None
    properties: Dict[str, Any]
    outranked_evidence_ids: Dict[str, List[str]]


class PendingEvidenceItem(BaseModel):
    """Row for the moderation queue ``GET /evidence/pending``."""
    id: str
    identity_id: str
    method: str
    status: str
    observed_at: str
    quantity: str
    verification_state: VerificationState
    created: str
    supersedes: Optional[str] = None
    recorded_by_username: Optional[str] = None
    catalog_number: Optional[int] = None
    original_function: Optional[str] = None
    material: Optional[str] = None
    dataset: Optional[str] = None
    identity_published: bool = True
    pending_snapshot_id: Optional[str] = None


class EvidenceTypesEnvelope(BaseModel):
    """Codegen only: what the evidence routes serve
    (``/schema/evidence`` --> frontend ``EvidenceModels.ts``)."""
    evidence: EvidenceView
    properties: PropertiesView
    pending: PendingEvidenceItem
    tombstone: Tombstone


class EvidenceInputEnvelope(BaseModel):
    """Codegen only: what the evidence routes take, and the payload of
    every method (``/schema/create-evidence`` --> ``EvidenceCreateModels.ts``)."""
    create: EvidenceCreate
    bulk: EvidenceBulk
    verification: VerificationBody
    reason: ReasonBody


def _payload_envelope():
    from pydantic import create_model
    return create_model(
        'EvidencePayloads', **{
            name: (spec.payload_model, ...)
            for name, spec in SPEC_BY_NAME.items()})


@router.get('/schema/evidence', include_in_schema=False)
async def get_evidence_json_schema():
    return EvidenceTypesEnvelope.model_json_schema(by_alias=True)


@router.get('/schema/create-evidence', include_in_schema=False)
async def get_create_evidence_json_schema():
    schema = EvidenceInputEnvelope.model_json_schema(by_alias=True)
    payloads = _payload_envelope().model_json_schema(by_alias=True)
    schema['properties']['payloads'] = {'$ref': '#/$defs/EvidencePayloads'}
    schema['required'] = [*schema.get('required', []), 'payloads']
    defs = schema.setdefault('$defs', {})
    for name, definition in (payloads.get('$defs') or {}).items():
        defs.setdefault(name, definition)
    defs['EvidencePayloads'] = {k: v for k, v in payloads.items()
                                if k != '$defs'}
    return schema


# CREATE ----------------------------------------------------------------------
@router.post('/identities/{identity_id}/evidence', status_code=201,
             summary='Record evidence about a component (a draft)')
async def create_evidence(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    identity_id: str,
    body: EvidenceCreate,
    submit: bool = Query(False, description='create it pending'),
):
    """contributor(D). The server recomputes what the method computes
    (median, F / A, l/d class, grid points ...) and refuses a value that
    disagrees; warnings come back with the record. 409 for a withdrawn
    component or an observation after a terminal exit (I28)."""
    validate_uuid(identity_id, label='identity id')
    identity = await load_identity(request, identity_id)
    viewer = await require_contributor(request, current_user,
                                       'create_evidence', identity)
    gate_identity(identity)
    prepared = await prepare(request, identity, client_data(body))
    doc = new_evidence_doc(identity_id, prepared, body, current_user,
                           status='pending' if submit else 'draft')
    await request.app.mongodb_component_evidence.insert_one(dict(doc))
    return JSONResponse(status_code=201, content=await evidence_body(
        request, viewer, doc, identity))


@router.post('/evidence/bulk', status_code=201,
             summary='Several records at once, all or none')
async def create_evidence_bulk(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: EvidenceBulk,
):
    """contributor(D) of every target. Fan-out (three rebound areas, one
    inspection noting several findings) and apply-to-several (a claim for
    a batch of pieces) end here (7.6). Every record is validated before
    the first is inserted; one problem rejects the whole request and names
    the record by its position."""
    identities: Dict[str, Dict[str, Any]] = {}
    docs: List[Dict[str, Any]] = []
    viewer = viewer_of(current_user)
    for index, item in enumerate(body.records):
        validate_uuid(item.identity_id, label='identity id')
        identity = identities.get(item.identity_id)
        if identity is None:
            identity = await load_identity(request, item.identity_id)
            viewer = await require_contributor(
                request, current_user, 'create_evidence', identity)
            gate_identity(identity)
            identities[item.identity_id] = identity
        prepared = await prepare(
            request, identity, client_data(_without_identity(item)),
            index=index)
        docs.append(new_evidence_doc(
            item.identity_id, prepared, item, current_user,
            status='pending' if body.submit else 'draft'))
    coll = request.app.mongodb_component_evidence
    inserted: List[str] = []
    try:
        for doc in docs:
            await coll.insert_one(dict(doc))
            inserted.append(doc['_id'])
    except Exception:
        if inserted:
            await coll.delete_many({'_id': {'$in': inserted}})
        raise
    return JSONResponse(status_code=201, content={'records': [
        await evidence_body(request, viewer, doc,
                            identities[doc['identity_id']])
        for doc in docs]})


def _without_identity(item) -> EvidenceCreate:
    """A bulk item as a plain create body (the identity is its own key)."""
    return EvidenceCreate.model_validate(
        item.model_dump(exclude={'identity_id'}))


# READ ------------------------------------------------------------------------
def _when(name: str, value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    from apps.catalog.timeutil import parse_ts
    try:
        parse_ts(value)
    except ValueError as exc:
        raise HTTPException(status_code=422,
                            detail=f'{name}: not an ISO-8601 date: '
                                   f'{value!r}') from exc
    return value


def _instant(name: str, value: str, *, end_of_day: bool = False):
    """A ``since`` / ``until`` bound in the form observed_at is stored in
    (UTC, ``...Z``), so a bound with an offset or a bare date compares
    right as a string. A bare ``until`` date means the whole day: the bound
    is the next midnight and exclusive. Returns ``(instant, exclusive)``."""
    from datetime import timedelta
    from apps.catalog.timeutil import parse_ts
    _when(name, value)
    moment = parse_ts(value)
    bare = len(value.strip()) == 10
    if end_of_day and bare:
        moment += timedelta(days=1)
    return moment.strftime('%Y-%m-%dT%H:%M:%SZ'), end_of_day and bare


def _record_filters(*, method: Optional[str], tier: Optional[str],
                    quantity: Optional[str], since: Optional[str],
                    until: Optional[str], status: str,
                    superseded: bool) -> Dict[str, Any]:
    """Mongo match shared by the evidence lists."""
    if method is not None and method not in SPEC_BY_NAME:
        raise HTTPException(status_code=422, detail=f'unknown method '
                                                    f'{method!r}')
    if tier is not None and tier not in SOURCE_TIERS:
        raise HTTPException(status_code=422, detail=f'unknown tier {tier!r}')
    if status != 'all' and status not in STATUSES:
        raise HTTPException(status_code=422,
                            detail=f'status: one of {list(STATUSES)} or all')
    match: Dict[str, Any] = {}
    if status != 'all':
        match['status'] = status
    if not superseded:
        match['superseded_by'] = None
    if method:
        match['method'] = method
    if tier:
        match['source_tier'] = tier
    if quantity:
        match['$or'] = [{'summary.quantity': quantity},
                        {'derived.quantity': quantity}]
    window: Dict[str, Any] = {}
    if since:
        window['$gte'] = _instant('since', since)[0]
    if until:
        bound, exclusive = _instant('until', until, end_of_day=True)
        window['$lt' if exclusive else '$lte'] = bound
    if window:
        match['observed_at'] = window
    return match


@router.get('/identities/{identity_id}/evidence',
            summary='Evidence of a component')
async def list_identity_evidence(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    identity_id: str,
    method: Optional[str] = Query(None),
    tier: Optional[str] = Query(None, description='source tier'),
    quantity: Optional[str] = Query(None, description='summary or derived'),
    since: Optional[str] = Query(
        None, description='observed_at from (UTC; a bare date is its '
                          'midnight)'),
    until: Optional[str] = Query(
        None, description='observed_at to (a bare date includes that '
                          'whole day)'),
    status: str = Query('published', description='a status, or all'),
    include: Optional[str] = Query(
        None, description='comma list: context (the state of the piece each '
                          'record belongs to), superseded (corrected ones)'),
):
    """Published, non-superseded records by default; what the caller may
    see of the others follows section 7.0 (a withdrawn record outside D is
    a tombstone row)."""
    validate_uuid(identity_id, label='identity id')
    identity = await ensure_identity_visible(request, identity_id,
                                             current_user)
    flags = {part.strip() for part in (include or '').split(',')}
    match = _record_filters(method=method, tier=tier, quantity=quantity,
                            since=since, until=until, status=status,
                            superseded='superseded' in flags)
    try:
        docs = await request.app.mongodb_component_evidence.find(
            {'identity_id': identity_id, **match}).sort(
            [('observed_at', 1), ('_id', 1)]).to_list(length=None)
    except PyMongoError as exc:
        print(f'[ERROR] list_identity_evidence DB error: {exc}')
        raise HTTPException(status_code=500, detail='Internal server error')
    viewer = viewer_of(current_user)
    project = await _projector(request, viewer, identity)
    snapshots = None
    if 'context' in flags:
        snapshots = await request.app.mongodb_component_snapshots.find(
            {'identity_id': identity_id},
            {'_id': 1, 'version': 1, 'status': 1, 'superseded_by': 1,
             'effective_from': 1, 'effective_from_precision': 1}
        ).to_list(length=None)
    items = []
    for doc in docs:
        seen = project(doc)
        if seen == 'full':
            items.append(await evidence_body(
                request, viewer, doc, identity, listing=True,
                with_context='context' in flags, snapshots=snapshots))
        elif seen == 'tombstone':
            items.append(evidence_tombstone(doc, identity))
    return JSONResponse(status_code=200, content=items)


@router.get('/evidence/pending',
            summary='Moderation queue: pending evidence of the caller\'s '
                    'datasets')
async def list_pending_evidence(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """``status == pending`` in the datasets the caller moderates (admin:
    all), oldest first. A row says whether its component is published yet
    (publishing it is refused until then, I26) and names the snapshot that
    waits with it (8.9)."""
    viewer = viewer_of(current_user)
    moderated = {d.id for d in (await load_datasets(request)).values()
                 if 'moderator' in dataset_roles(viewer, d)}
    docs = await request.app.mongodb_component_evidence.find(
        {'status': 'pending'}).sort('created', 1).to_list(length=None)
    identities = request.app.mongodb_component_identities
    items = []
    cache: Dict[str, Optional[Dict[str, Any]]] = {}
    for doc in docs:
        iid = doc['identity_id']
        if iid not in cache:
            cache[iid] = await identities.find_one(
                {'_id': iid}, {'catalog_number': 1, 'original_function': 1,
                               'material': 1, 'dataset': 1,
                               'current_snapshot_id': 1})
        identity = cache[iid]
        if identity is None or identity.get('dataset') not in moderated:
            continue
        published = await identity_ever_published(request, identity)
        waiting = None
        if not published:
            snap = await request.app.mongodb_component_snapshots.find_one(
                {'identity_id': iid, 'status': 'pending'}, {'_id': 1})
            waiting = snap['_id'] if snap else None
        items.append(PendingEvidenceItem(
            id=doc['_id'], identity_id=iid, method=doc['method'],
            status=doc['status'], observed_at=doc['observed_at'],
            quantity=doc['summary']['quantity'],
            verification_state=(doc.get('verification') or {}).get(
                'state') or 'unverified',
            created=doc['created'], supersedes=doc.get('supersedes'),
            recorded_by_username=doc.get('recorded_by_username'),
            catalog_number=identity.get('catalog_number'),
            original_function=identity.get('original_function'),
            material=identity.get('material'),
            dataset=identity.get('dataset'), identity_published=published,
            pending_snapshot_id=waiting).model_dump(mode='json'))
    return JSONResponse(status_code=200, content=items)


@router.get('/evidence', summary='Evidence across the catalog')
async def list_evidence(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    dataset: Optional[str] = Query(None),
    method: Optional[str] = Query(None),
    tier: Optional[str] = Query(None),
    quantity: Optional[str] = Query(None),
    min: Optional[float] = Query(None, description='result value or range '
                                                   'reaches at least this'),
    max: Optional[float] = Query(None, description='result value or range '
                                                   'starts at most here'),
    status: str = Query('published'),
    verification: Optional[VerificationState] = Query(None),
    limit: int = Query(DEFAULT_PAGE, ge=1, le=MAX_PAGE),
    skip: int = Query(0, ge=0),
):
    """Records of every component the caller can see, oldest observation
    first; the visibility rules of 7.0 apply per record. People appear as
    in any list: no e-mail addresses."""
    match = _record_filters(method=method, tier=tier, quantity=quantity,
                            since=None, until=None, status=status,
                            superseded=False)
    if verification:
        match['verification.state'] = verification
    clauses: List[Dict[str, Any]] = (
        [{'$or': match.pop('$or')}] if '$or' in match else [])
    if min is not None:
        clauses.append({'$or': [{'summary.value': {'$gte': min}},
                                {'summary.range.1': {'$gte': min}}]})
    if max is not None:
        clauses.append({'$or': [{'summary.value': {'$lte': max}},
                                {'summary.range.0': {'$lte': max}}]})
    viewer = viewer_of(current_user)
    identity_match: Dict[str, Any] = {}
    if dataset:
        identity_match['dataset'] = dataset
    identities = request.app.mongodb_component_identities
    if status == 'published':
        # a published record is visible exactly when its component is, and
        # that is a match (3.6): the page is cut in the database
        identity_match = and_match(
            identity_match, await visible_identity_match(request, viewer))
    ids = [d['_id'] async for d in identities.find(identity_match,
                                                   {'_id': 1})]
    if clauses:
        match['$and'] = clauses
    match['identity_id'] = {'$in': ids}
    docs = request.app.mongodb_component_evidence.find(match).sort(
        [('observed_at', 1), ('_id', 1)])
    if status == 'published':
        page = await docs.skip(skip).limit(limit).to_list(length=limit)
        owners = {d['_id']: d for d in await identities.find(
            {'_id': {'$in': list({r['identity_id'] for r in page})}}
        ).to_list(length=None)}
        contexts: Dict[str, Any] = {}
        rows: List[Dict[str, Any]] = []
        for doc in page:
            owner = owners[doc['identity_id']]
            if doc['identity_id'] not in contexts:
                contexts[doc['identity_id']] = (
                    await viewer_context(request, viewer, owner),
                    owner.get('withdrawn') and withdrawn_projection(
                        viewer, await dataset_of(request,
                                                 owner.get('dataset')),
                        component_visible=True))
            context, withdrawn = contexts[doc['identity_id']]
            if owner.get('withdrawn') and withdrawn != 'full':
                rows.append(evidence_tombstone(doc, owner))
            else:
                rows.append(await evidence_body(
                    request, viewer, doc, owner, listing=True,
                    context=context))
        return JSONResponse(status_code=200, content=rows)
    items: List[Dict[str, Any]] = []
    projectors: Dict[str, Any] = {}
    identity_docs: Dict[str, Dict[str, Any]] = {}
    seen_rows = 0
    async for doc in docs:
        iid = doc['identity_id']
        if iid not in projectors:
            identity_docs[iid] = await identities.find_one({'_id': iid})
            projectors[iid] = await _projector(request, viewer,
                                               identity_docs[iid])
        seen = projectors[iid](doc)
        if seen is None:
            continue
        seen_rows += 1
        if seen_rows <= skip:
            continue
        if seen == 'full':
            items.append(await evidence_body(request, viewer, doc,
                                             identity_docs[iid],
                                             listing=True))
        else:
            items.append(evidence_tombstone(doc, identity_docs[iid]))
        if len(items) >= limit:
            break
    return JSONResponse(status_code=200, content=items)


@router.get('/evidence/{evidence_id}', summary='One evidence record')
async def get_evidence(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    evidence_id: str,
    include: Optional[str] = Query(None, description='context'),
    as_of: Optional[str] = Query(
        None, description='the record as it was at this ISO date (members '
                          'of D and admin; section 3.8)'),
):
    """200 with the record as the caller may see it; a tombstone for a
    withdrawn record outside the dataset (8.17); ``ETag`` / ``304``."""
    viewer = viewer_of(current_user)
    record, identity = await ensure_evidence_visible(
        request, evidence_id, current_user, allow_tombstone=True)
    if as_of is not None:
        from .change_log import as_of_body
        dataset = await dataset_of(request, identity.get('dataset'))
        if not dataset_roles(viewer, dataset):
            raise HTTPException(status_code=403,
                                detail='Earlier versions are for members of '
                                       'the dataset.')
        rolled = await as_of_body(request, 'evidence', record, as_of)
        tier, email_ok = await viewer_context(request, viewer, identity)
        # the same projection as every other read (8.70 d): the roll-back
        # restores old values, which may name people
        return JSONResponse(status_code=200, content=project_evidence(
            rolled, tier, email_ok=email_ok))
    with_context = 'context' in {p.strip() for p in (include or '').split(',')}
    if with_context:
        # the context follows the snapshots, not the record: never a 304
        body = await evidence_body(request, viewer, record, identity,
                                   with_context=True)
        return JSONResponse(status_code=200, content=body,
                            headers={'Cache-Control': 'no-store'})
    tier, email_ok = await viewer_context(request, viewer, identity)
    etag = hashlib.sha256('::'.join([
        record.get('etag') or '', tier, str(email_ok)]).encode(
        'utf-8')).hexdigest()
    if request.headers.get('if-none-match') == etag:
        return not_modified_response(etag)
    body = await evidence_body(request, viewer, record, identity)
    return JSONResponse(status_code=200, content=body,
                        headers={'ETag': etag,
                                 'Cache-Control': 'private, max-age=0'})


# PROPERTIES ------------------------------------------------------------------
@router.get('/identities/{identity_id}/properties',
            summary='Folded properties of a component')
async def get_identity_properties(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    identity_id: str,
    as_of: Optional[str] = Query(
        None, description='recompute the identity-scoped quantities from the '
                          'records observed up to this date (computed, not '
                          'stored; no inheritance)'),
):
    """The identity block of section 4.4 and ``outranked_evidence_ids``:
    per quantity, the records a higher source tier outranked --- an archival
    claim next to a core test, not a correction."""
    validate_uuid(identity_id, label='identity id')
    identity = await ensure_identity_visible(request, identity_id,
                                             current_user)
    return JSONResponse(status_code=200, content=await evidence_fold_view(
        request, identity, as_of=_when('as_of', as_of)))


@router.get('/snapshots/{snapshot_id}/properties',
            summary='Properties of one state of a component')
async def get_snapshot_properties(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    snapshot_id: str,
):
    """The snapshot block (the materialized as-of fold): the snapshot-scoped
    quantities whose records resolve to this state."""
    validate_uuid(snapshot_id, label='snapshot id')
    snapshot = await ensure_snapshot_visible(request, snapshot_id,
                                             current_user,
                                             allow_tombstone=True)
    return JSONResponse(status_code=200, content={
        'snapshot_id': snapshot_id, 'identity_id': snapshot['identity_id'],
        'properties': snapshot.get('properties') or {}})


# TIMELINE --------------------------------------------------------------------
@router.get('/identities/{identity_id}/timeline',
            summary='What happened to a component, merged')
async def get_timeline(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    identity_id: str,
):
    """Archived cycles, the origin, every state and correction, every
    evidence record (where it falls: before cataloguing, in the history,
    after the piece left circulation), changes of the metadata and the exit.
    What the caller may not see is left out; a withdrawn record outside the
    dataset is a bare row; outside the dataset a metadata change shows only
    its date (8.36)."""
    validate_uuid(identity_id, label='identity id')
    identity = await ensure_identity_visible(request, identity_id,
                                             current_user)
    viewer = viewer_of(current_user)
    dataset = await dataset_of(request, identity.get('dataset'))
    member = bool(dataset_roles(viewer, dataset))
    snapshots = await request.app.mongodb_component_snapshots.find(
        {'identity_id': identity_id},
        {'_id': 1, 'version': 1, 'status': 1, 'name': 1, 'superseded_by': 1,
         'supersedes': 1, 'effective_from': 1,
         'effective_from_precision': 1, 'status_changed_at': 1,
         'added_by_user_id': 1, 'created': 1, 'lastmodified': 1,
         'identity_id': 1}).sort('version', 1).to_list(length=None)
    visible_snaps = await visible_snapshot_docs(
        request, current_user, identity, snapshots, tombstones=True)
    docs = await request.app.mongodb_component_evidence.find(
        {'identity_id': identity_id}).sort(
        [('observed_at', 1), ('_id', 1)]).to_list(length=None)
    project = await _projector(request, viewer, identity)
    rows: List[Dict[str, Any]] = []
    full: List[Dict[str, Any]] = []
    for doc in docs:
        seen = project(doc)
        if seen == 'full':
            rows.append(doc)
            full.append(doc)
        elif seen == 'tombstone':
            tomb = evidence_tombstone(doc, identity)
            rows.append({'_id': doc['_id'], 'status': 'withdrawn',
                         'observed_at': tomb['withdrawn_at'],
                         'summary': {}})
    contexts = contexts_for(identity, snapshots, full)
    changes = await request.app.mongodb_change_log.find(
        {'record_id': identity_id, 'record_kind': 'identity'}).sort(
        'at', 1).to_list(length=None)
    events = build_timeline(identity, visible_snaps, rows, contexts, changes,
                            members=member)
    return JSONResponse(status_code=200, content={
        'identity_id': identity_id, 'events': events})
