#!/usr/bin/env python3.13
"""
What every evidence route shares (data model spec section 3.3, 7.0, 7.2;
plan P6): the models a client sends, loading and projecting a record for a
viewer, the gates of I9 / I26 / I28, the pairing facts, and building the
stored document.

Routes are thin: they load, ``require`` the permission, call
``prepare_record`` (pure, ``apps/catalog/evidence/registry.py``), add what
needs the database, write, log (I30) and recompute the fold.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import (
    Actor,
    Evidence,
    Standard,
    Timestamp,
    Vec3,
)
from apps.catalog.etag import compute_snapshot_etag
from apps.catalog.evidence.projection import (
    evidence_tombstone,
    project_evidence,
    viewer_tier,
)
from apps.catalog.evidence.registry import (
    RESULT_FIELDS,
    PreparedRecord,
    SPEC_BY_NAME,
    paired_rebound_id,
    prepare_record,
    record_warnings,
)
from apps.catalog.evidence.types import (
    EvidenceInvalid,
    PairingFacts,
    Problem,
)
from apps.catalog.models import User
from apps.catalog.permissions import (
    Viewer,
    dataset_roles,
    record_projection,
    withdrawn_projection,
)
from apps.catalog.properties import contexts_for
from apps.catalog.vocab import (
    TERMINAL_EXIT_KINDS,
    EvidenceMethod,
    PositionKind,
    Precision,
    SummaryKind,
    UncertaintyType,
)
from apps.catalog.timeutil import parse_ts
from .access import (
    TombstoneHit,
    component_visible,
    dataset_of,
    deny_read,
    load_identity,
    raise_if_purged,
    require,
    viewer_of,
)
from .catalog_common import now_iso, validate_uuid

MAX_BULK = 200
Scalar = Union[float, int, str]


# WHAT A CLIENT SENDS ---------------------------------------------------------
class PositionInput(BaseModel):
    """Where on the piece (3.3.2). ``kind: none`` with a description is
    always enough; a point is picked on the 3D viewer and needs the snapshot
    whose stored coordinates it uses."""
    model_config = ConfigDict(extra='forbid')

    kind: Optional[PositionKind] = Field(
        None, description='point, region, face or none; a rebound grid is '
                          'always a region')
    snapshot_id: Optional[str] = Field(
        None, description='The snapshot whose stored coordinates `point` '
                          'is in (authored, never derived)')
    point: Optional[Vec3] = Field(
        None, description='Picked point in stored coordinates; for a rebound '
                          'grid the server sets the grid centre')
    description: Optional[str] = Field(
        None, description='Where on the piece, in words, e.g. "north face, '
                          'mid-span"')


class UncertaintyInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: UncertaintyType = Field(
        description='expanded widens the folded range; the others are '
                    'recorded only')
    value: Optional[float] = Field(None, ge=0.0, description='In the unit '
                                                             'of the result')
    k: Optional[float] = Field(None, gt=0.0, description='Coverage factor')


class SummaryInput(BaseModel):
    """The record's one headline result. Left out where the method derives
    it (rebound, core, visual inspection, layout); a claim states it."""
    model_config = ConfigDict(extra='forbid')

    quantity: str = Field(description='A quantity of the vocabulary '
                                      '(GET /evidence/quantities)')
    value: Optional[Scalar] = Field(None, description='A measured value')
    range: Optional[List[Scalar]] = Field(
        None, description='[low, high], or the claimed classes of a '
                          'categorical quantity')
    unit: Optional[str] = Field(
        None, description='The unit the values are in; converted to the '
                          'canonical unit and remembered as unit_entered')
    unit_entered: Optional[str] = Field(
        None, description='Set by the server')
    kind: Optional[SummaryKind] = Field(
        None, description='measured or claimed; the method decides')
    uncertainty: Optional[UncertaintyInput] = None


class DerivedModelInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    kind: str = Field(description='A model kind of the method '
                                  '(GET /evidence/methods, derived_models)')
    reference: Optional[str] = Field(None, description='The document or '
                                                       'report it rests on')
    note: Optional[str] = Field(None, description='E.g. the table row a '
                                                  'class was read from')


class DerivedInput(BaseModel):
    """A result derived from the record's by a named model (8.41)."""
    model_config = ConfigDict(extra='forbid')

    quantity: str
    value: Optional[Scalar] = None
    range: Optional[List[Scalar]] = None
    unit: Optional[str] = None
    kind: str = 'derived'
    model: DerivedModelInput


class EvidenceCreate(BaseModel):
    """One evidence record as a client sends it (``POST /identities/{id}/
    evidence``, a record of a bulk, a correction). Everything the method can
    compute is optional; what is sent must agree with the server's value."""
    model_config = ConfigDict(extra='forbid')

    method: EvidenceMethod
    standard: Optional[Standard] = Field(
        None, description='Defaults to the standard of the method')
    observed_at: Optional[Timestamp] = Field(
        None, description='When the result was produced (a core: the test '
                          'date, taken from the payload)')
    observed_at_precision: Precision = 'exact'
    sampled_at: Optional[Timestamp] = Field(
        None, description='When the component was sampled (a core: the '
                          'drilling date, taken from the payload)')
    sampled_at_precision: Optional[Precision] = None
    performed_by: List[Actor] = Field(default_factory=list)
    position: Optional[PositionInput] = None
    summary: Optional[SummaryInput] = None
    derived: List[DerivedInput] = Field(default_factory=list)
    payload: Dict[str, Any] = Field(
        description='Per method: GET /evidence/methods, payload_schema')
    notes: Optional[str] = None
    self_attested: bool = Field(
        False, description='"I performed this and stand by the result": '
                           'needs the recorder among performed_by (8.12)')


class EvidenceBulkItem(EvidenceCreate):
    identity_id: str = Field(description='The component the record is about')


class EvidenceBulk(BaseModel):
    """Several records, validated all, inserted all or none (7.2, 7.6):
    fan-out, apply-to-several."""
    model_config = ConfigDict(extra='forbid')

    records: List[EvidenceBulkItem] = Field(min_length=1, max_length=MAX_BULK)
    submit: bool = Field(False, description='Submit every record')


class VerificationBody(BaseModel):
    model_config = ConfigDict(extra='forbid')

    state: str = Field(description='unverified, self_attested, reviewed or '
                                   'accredited')
    note: Optional[str] = Field(
        None, description='What the reviewer checked; required for '
                          'accredited')


class ReasonBody(BaseModel):
    reason: str = Field(min_length=1)


# WHAT A CLIENT GETS ----------------------------------------------------------
class ContextView(BaseModel):
    snapshot_id: Optional[str] = None
    resolution: str


class EvidenceView(Evidence):
    """An evidence record as the API serves it: the stored document, the
    warnings the method computes from it (never stored) and, on request,
    the state of the piece it belongs to (4.1)."""
    warnings: List[str] = Field(default_factory=list)
    context: Optional[ContextView] = None


# ERRORS ----------------------------------------------------------------------
def invalid_http(exc: EvidenceInvalid, *, index: Optional[int] = None
                 ) -> HTTPException:
    detail: Dict[str, Any] = {
        'message': 'The evidence record is invalid.',
        'errors': [p.as_dict() for p in exc.problems]}
    if index is not None:
        detail['index'] = index
    return HTTPException(status_code=422, detail=detail)


def problem_http(path: str, message: str) -> HTTPException:
    return invalid_http(EvidenceInvalid([Problem(path, message)]))


def validated_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """The document against the Evidence model (I6, I7, I10, I22, I27 ...);
    sets the etag."""
    try:
        Evidence.model_validate(doc)
    except ValidationError as exc:
        raise invalid_http(EvidenceInvalid([
            Problem('.'.join(str(p) for p in error.get('loc', ())),
                    error['msg']) for error in exc.errors()])) from exc
    doc['etag'] = compute_snapshot_etag(doc)
    return doc


# LOADING AND VISIBILITY ------------------------------------------------------
async def load_evidence(request: Request, evidence_id: str) -> Dict[str, Any]:
    validate_uuid(evidence_id, label='evidence id')
    doc = await request.app.mongodb_component_evidence.find_one(
        {'_id': evidence_id})
    if doc is None:
        await raise_if_purged(request, evidence_id, 'Evidence')
    return doc


async def evidence_projection(request: Request, viewer: Viewer,
                              record: Dict[str, Any],
                              identity: Dict[str, Any]) -> Optional[str]:
    """'full', 'tombstone' or None. The records of a withdrawn identity
    are tombstones outside D whatever their own status (8.17)."""
    dataset = await dataset_of(request, identity.get('dataset'))
    visible = await component_visible(request, viewer, identity)
    projection = record_projection(
        viewer, dataset, kind='evidence',
        status=record.get('status') or 'published',
        author_id=record.get('recorded_by_user_id'),
        component_visible=visible)
    if projection == 'full' and identity.get('withdrawn'):
        projection = withdrawn_projection(viewer, dataset,
                                          component_visible=visible)
    return projection


async def ensure_evidence_visible(
    request: Request, evidence_id: str, user: Optional[User], *,
    allow_tombstone: bool = False
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """``(record, identity)`` for a record the caller sees in full. A
    tombstone viewer gets the tombstone where JSON is served; files and
    writes are for members only (8.17)."""
    viewer = viewer_of(user)
    record = await load_evidence(request, evidence_id)
    identity = await load_identity(request, str(record['identity_id']))
    projection = await evidence_projection(request, viewer, record, identity)
    if projection == 'full':
        return record, identity
    if projection == 'tombstone':
        if allow_tombstone:
            raise TombstoneHit(evidence_tombstone(record, identity))
        raise HTTPException(
            status_code=403,
            detail='Withdrawn: its files are for dataset members only.')
    raise deny_read(viewer)


async def viewer_context(request: Request, viewer: Viewer,
                         identity: Dict[str, Any]) -> Tuple[str, bool]:
    """``(tier, email_ok)``: how much of the people in a record this viewer
    sees (3.3.1)."""
    dataset = await dataset_of(request, identity.get('dataset'))
    roles = dataset_roles(viewer, dataset)
    tier = viewer_tier(logged_in=viewer.logged_in, member=bool(roles))
    return tier, viewer.is_admin or 'moderator' in roles


async def evidence_body(request: Request, viewer: Viewer,
                        record: Dict[str, Any], identity: Dict[str, Any], *,
                        listing: bool = False, with_context: bool = False,
                        snapshots: Optional[List[Dict[str, Any]]] = None,
                        context: Optional[Tuple[str, bool]] = None
                        ) -> Dict[str, Any]:
    """The record as ``viewer`` sees it, validated against the model.
    ``context`` is ``viewer_context`` when a list has it already."""
    tier, email_ok = context or await viewer_context(request, viewer,
                                                     identity)
    stored = Evidence.model_validate(record).model_dump(by_alias=True,
                                                        mode='json')
    body = project_evidence(stored, tier, email_ok=email_ok, listing=listing)
    body['warnings'] = record_warnings(record)
    body['context'] = None
    if with_context:
        if snapshots is None:
            snapshots = await request.app.mongodb_component_snapshots.find(
                {'identity_id': identity['_id']},
                {'_id': 1, 'version': 1, 'status': 1, 'superseded_by': 1,
                 'effective_from': 1, 'effective_from_precision': 1}
            ).to_list(length=None)
        context = contexts_for(identity, snapshots, [record])[record['_id']]
        body['context'] = context.as_dict()
    return body


async def projector(request: Request, viewer: Viewer,
                    identity: Dict[str, Any]):
    """A function ``record -> 'full' | 'tombstone' | None`` for the records
    of one identity; the component's visibility is asked once."""
    dataset = await dataset_of(request, identity.get('dataset'))
    visible = await component_visible(request, viewer, identity)

    def project(record: Dict[str, Any]) -> Optional[str]:
        projection = record_projection(
            viewer, dataset, kind='evidence',
            status=record.get('status') or 'published',
            author_id=record.get('recorded_by_user_id'),
            component_visible=visible)
        if projection == 'full' and identity.get('withdrawn'):
            projection = withdrawn_projection(viewer, dataset,
                                              component_visible=visible)
        return projection
    return project


async def published_bodies(request: Request, user: Optional[User],
                           identity: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The published, non-superseded evidence of a component as the caller
    sees it (a list: no e-mail addresses); for the passport's
    ``?include=evidence``."""
    viewer = viewer_of(user)
    project = await projector(request, viewer, identity)
    docs = await request.app.mongodb_component_evidence.find(
        {'identity_id': identity['_id'], 'status': 'published',
         'superseded_by': None}).sort(
        [('observed_at', 1), ('_id', 1)]).to_list(length=None)
    out = []
    for doc in docs:
        if project(doc) == 'full':
            out.append(await evidence_body(request, viewer, doc, identity,
                                           listing=True))
    return out


# GATES -----------------------------------------------------------------------
def gate_identity(identity: Dict[str, Any],
                  observed_at: Optional[str] = None) -> None:
    """I28: no evidence on a withdrawn identity (409, naming the canonical
    piece when there is one); after a terminal exit only observations from
    before it (8.16)."""
    withdrawn = identity.get('withdrawn')
    if withdrawn:
        duplicate = withdrawn.get('duplicate_of')
        message = 'The component is withdrawn' + (
            f'; it duplicates {duplicate}' if duplicate else '') + ' (I28).'
        raise HTTPException(status_code=409, detail={
            'message': message, 'duplicate_of': duplicate})
    exit_ = identity.get('exit')
    if observed_at and exit_ and exit_.get('kind') in TERMINAL_EXIT_KINDS \
            and parse_ts(observed_at) > parse_ts(exit_['at']):
        raise HTTPException(
            status_code=409,
            detail=f'The component no longer exists as this piece '
                   f'({exit_["kind"]}, {exit_["at"]}): only observations '
                   f'from before that date are recorded (I28).')


async def check_position(request: Request, identity_id: str,
                         position: Optional[Dict[str, Any]]) -> None:
    """I9: ``position.snapshot_id`` belongs to the record's identity."""
    sid = (position or {}).get('snapshot_id')
    if sid is None:
        return
    found = await request.app.mongodb_component_snapshots.find_one(
        {'_id': sid, 'identity_id': identity_id}, {'_id': 1})
    if found is None:
        raise problem_http('position.snapshot_id',
                           'not a snapshot of this component (I9)')


async def pairing_facts(request: Request, identity_id: str,
                        data: Dict[str, Any], *,
                        exclude: Tuple[str, ...] = ()
                        ) -> Optional[PairingFacts]:
    """The stored rebound record a core names and the other cores that name
    it (8.42); None when the data names none."""
    pid = paired_rebound_id(data)
    if pid is None:
        return None
    coll = request.app.mongodb_component_evidence
    rebound = await coll.find_one({'_id': pid})
    others = await coll.find(
        {'method': 'core_compression',
         'payload.sampling.paired_rebound_id': pid,
         '_id': {'$nin': list(exclude)},
         'status': {'$nin': ['rejected', 'withdrawn']},
         'superseded_by': None}, {'_id': 1}).to_list(length=None)
    return PairingFacts(identity_id=identity_id, rebound=rebound,
                        other_pairs=[o['_id'] for o in others])


def client_data(body: EvidenceCreate) -> Dict[str, Any]:
    """What ``prepare_record`` takes: the client's fields without the empty
    ones."""
    data = body.model_dump(mode='json', exclude={'self_attested', 'notes'},
                           exclude_none=True)
    data.setdefault('payload', {})
    if body.position is not None:
        data['position'] = body.position.model_dump(mode='json',
                                                    exclude_none=True)
    return data


async def prepare(request: Request, identity: Dict[str, Any],
                  data: Dict[str, Any], *, exclude: Tuple[str, ...] = (),
                  index: Optional[int] = None) -> PreparedRecord:
    """The registry's verdict plus the database checks (I9, I28, pairing);
    raises 422 / 409."""
    if data.get('method') not in SPEC_BY_NAME:
        raise problem_http('method', f'unknown method {data.get("method")!r}')
    try:
        pairing = await pairing_facts(request, identity['_id'], data,
                                      exclude=exclude)
        prepared = prepare_record(data, pairing=pairing)
    except EvidenceInvalid as exc:
        raise invalid_http(exc, index=index) from exc
    gate_identity(identity, prepared.fields['observed_at'])
    await check_position(request, identity['_id'], prepared.fields['position'])
    return prepared


async def require_contributor(request: Request, user: Optional[User],
                              action: str, identity: Dict[str, Any], *,
                              evidence: Optional[Dict[str, Any]] = None
                              ) -> Viewer:
    """``require`` for the actions that need ``contributor(D)`` (recording
    and correcting evidence). Roles are a set (8.70 e), so a 403 for a
    signed-in member of the dataset says which role is missing and what the
    caller holds."""
    try:
        return await require(request, user, action, identity=identity,
                             evidence=evidence)
    except HTTPException as exc:
        viewer = viewer_of(user)
        if exc.status_code != 403 or not viewer.logged_in:
            raise
        dataset = await dataset_of(request, identity.get('dataset'))
        roles = sorted(dataset_roles(viewer, dataset))
        if roles and 'contributor' not in roles:
            raise HTTPException(
                status_code=403,
                detail=f'Recording evidence needs the contributor role in '
                       f'dataset {dataset.id}; you hold: '
                       f'{", ".join(roles)}. Roles are a set: ask a '
                       f'moderator to add contributor.') from exc
        raise


def history_entry(frm: str, to: str, user_id: str, at: str,
                  reason: Optional[str] = None) -> Dict[str, Any]:
    return {'from': frm, 'to': to, 'at': at, 'by_user_id': user_id,
            'reason': reason}


def new_evidence_doc(identity_id: str, prepared: PreparedRecord,
                     body: EvidenceCreate, user: User, *, status: str,
                     supersedes: Optional[str] = None) -> Dict[str, Any]:
    """The stored document of a new record (draft; or pending, with the
    draft --> pending step in its history)."""
    now = now_iso()
    history: List[Dict[str, Any]] = []
    if status != 'draft':
        history.append(history_entry('draft', status, user.id, now))
    verification = {'state': 'unverified', 'by': None, 'at': None,
                    'note': None}
    performers = [a.model_dump(mode='json') for a in body.performed_by]
    if body.self_attested:
        verification = {'state': 'self_attested',
                        'by': {'kind': 'user', 'user_id': user.id},
                        'at': now, 'note': None}
    doc = {
        **prepared.fields, '_id': str(uuid.uuid4()),
        'identity_id': identity_id, 'performed_by': performers,
        'recorded_by_user_id': user.id,
        'recorded_by_username': user.username, 'attachments': [],
        'notes': body.notes, 'status': status,
        'status_changed_by_user_id': user.id, 'status_changed_at': now,
        'status_history': history, 'verification': verification,
        'supersedes': supersedes, 'superseded_by': None,
        'created': now, 'lastmodified': now}
    return validated_doc(doc)


def stored_input(doc: Dict[str, Any]) -> Dict[str, Any]:
    """A stored record as ``prepare_record`` input, for an edit or a
    correction. Where the payload decides the dates (a core) or the method
    derives the summary, the stored values are left out: they follow the
    new payload."""
    data = {k: doc.get(k) for k in RESULT_FIELDS if k not in (
        'method_version', 'source_tier', 'destructive')}
    spec = SPEC_BY_NAME[doc['method']]
    if doc['method'] == 'core_compression':
        data.pop('observed_at', None)
        data.pop('sampled_at', None)
    if not spec.summary_from_client:
        data.pop('summary', None)
    data['position'] = {k: v for k, v in (doc.get('position') or {}).items()
                        if v is not None}
    data['performed_by'] = list(doc.get('performed_by') or [])
    return data


RESULT_KEYS = ('payload', 'summary', 'derived', 'observed_at',
               'observed_at_precision', 'sampled_at', 'sampled_at_precision',
               'performed_by', 'standard', 'method')


def result_changed(old: Dict[str, Any], new: Dict[str, Any]) -> bool:
    """Whether a result field of a record differs (8.12 (4): a review never
    outlives what it reviewed)."""
    import json

    def same(a: Any, b: Any) -> bool:
        return json.dumps(a, sort_keys=True, default=str) == \
            json.dumps(b, sort_keys=True, default=str)
    if any(not same(old.get(k), new.get(k)) for k in RESULT_KEYS):
        return True
    op, np = old.get('position') or {}, new.get('position') or {}
    return any(not same(op.get(k), np.get(k))
               for k in ('snapshot_id', 'point', 'kind'))
