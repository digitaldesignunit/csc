#!/usr/bin/env python3.13
"""
Routes for the `component_identities` collection: one identity and what hangs
on it.

* `GET /identities/{identity_id}`
    -> one identity (`?expand=`, `?as_of=`)

* `GET /identities/{identity_id}/compose`
    -> passport (identity + snapshots[]): default current, `?snapshots=all`,
    or `?snapshots=<uuid>` (comma-separated for many)
    The `compose` path segment predates the `passport` term and stays for
    compatibility with released Grasshopper userobjects.

* `GET /identities/{identity_id}/snapshots`
    -> summary list of all snapshot versions for one identity

* `GET /identities/{identity_id}/children`
    -> shallow rows for identities that list this identity as a parent

* `GET /identities/{identity_id}/provenance`
    -> identity + snapshot lineage graph (ancestors, descendants, versions)

The catalogue reads are in `catalog_list.py`, the schema routes in
`schema_routes.py`. Single-snapshot reads: `GET /snapshots/{snapshot_id}` in
`snapshots.py`; the file routes in `snapshot_*.py`.

Write routes: `identity_edit.py`, `snapshot_lifecycle.py`.
"""

import hashlib
from dataclasses import dataclass
from typing import Annotated, Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from apps.catalog.models import User
from apps.catalog.read_models import (
    ComponentPassport,
    SnapshotSummaryItem,
    catalog_row,
    geometry_failed,
    identity_body,
    passport_body,
)
from apps.catalog.exports import jsonld as jsonld_export
from apps.catalog.people import for_viewer
from apps.catalog.permissions import dataset_roles
from apps.catalog.api.access import (
    and_match,
    dataset_of,
    deny_read,
    viewer_of,
    visible_identity_match,
    visible_snapshot_docs,
)
from apps.catalog.provenance import (
    DEFAULT_PROVENANCE_DEPTH,
    MAX_PROVENANCE_DEPTH,
    build_provenance_graph,
)
from .auth import get_optional_current_user
from .batches import remaining_of
from .public_access import (
    ensure_identity_read_access,
    identity_allows_anonymous_read,
    viewer_etag,
    viewer_headers,
)
from .catalog_common import (
    internal_error,
    not_modified_response,
    get_identities_col,
    get_snapshots_col,
    validate_uuid,
)
from .identity_filters import ExpandMode, children_identity_match
from .identity_query import (
    aggregate_identities,
    build_list_pipeline,
    shallow_row_for_identity,
)
from .snapshot_media import refresh_snapshot_photo_count
from logging_setup import get_logger


log = get_logger(__name__)

router = APIRouter()


def _compute_passport_etag(
    identity_doc: dict,
    snapshot_docs: List[dict],
    remaining: Optional[int] = None,
) -> str:
    """Composite ETag from identity.lastmodified + sorted snapshot etags
    (+ the pieces left of a batch, which a draw changes elsewhere)."""
    parts = [identity_doc.get('lastmodified', '')]
    if remaining is not None:
        parts.append(f'remaining={remaining}')
    for doc in sorted(
        snapshot_docs,
        key=lambda row: str(row.get('_id', '')),
    ):
        parts.append(str(doc.get('etag', '')))
    return hashlib.sha256('::'.join(parts).encode('utf-8')).hexdigest()


def _parse_snapshots_query(
    snapshots: Optional[str],
) -> tuple[str, List[str]]:
    """
    Parse ``snapshots`` query param.

    Returns ``('current'|'all'|'ids', uuid_list)``.
    """
    if not snapshots or not str(snapshots).strip():
        return 'current', []
    token = str(snapshots).strip()
    if token.lower() == 'current':
        return 'current', []
    if token.lower() == 'all':
        return 'all', []
    parsed: List[str] = []
    for part in token.split(','):
        item = part.strip()
        if item:
            parsed.append(item)
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail='snapshots must be "current", "all", or one or more UUIDs',
        )
    return 'ids', parsed


async def _resolve_passport_snapshot_docs(
    request: Request,
    *,
    identity_id: str,
    identity_doc: dict,
    snapshots_col,
    mode: str,
    snapshot_ids: List[str],
) -> List[dict]:
    """Load full snapshot documents for a passport response."""
    if mode == 'all':
        try:
            cursor = snapshots_col.find(
                {'identity_id': identity_id},
            ).sort('version', 1)
            docs = await cursor.to_list(length=None)
        except PyMongoError:
            log.exception('passport snapshots=all DB')
            raise HTTPException(
                status_code=500,
                detail='Internal server error',
            )
        if not docs:
            raise HTTPException(
                status_code=404,
                detail=f'No snapshots found for identity {identity_id}',
            )
    elif mode == 'ids':
        docs = []
        for snapshot_id in snapshot_ids:
            validate_uuid(snapshot_id, label='snapshot id')
            doc = await snapshots_col.find_one({'_id': snapshot_id})
            if doc is None:
                raise HTTPException(
                    status_code=404,
                    detail=f'Snapshot {snapshot_id} not found',
                )
            if doc.get('identity_id') != identity_id:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f'Snapshot {snapshot_id} does not belong to identity '
                        f'{identity_id}'
                    ),
                )
            docs.append(doc)
        docs.sort(
            key=lambda row: (
                row.get('version', 0),
                str(row.get('_id', '')),
            ),
        )
    else:
        current_snapshot_id = identity_doc.get('current_snapshot_id')
        if not current_snapshot_id:
            return []                 # no published snapshot left (8.17)
        doc = await snapshots_col.find_one({'_id': current_snapshot_id})
        if doc is None:
            raise HTTPException(
                status_code=500,
                detail=(
                    f'current_snapshot_id={current_snapshot_id} of identity '
                    f'{identity_id} not found in component_snapshots.'
                ),
            )
        docs = [doc]

    for doc in docs:
        await refresh_snapshot_photo_count(
            request,
            str(doc['_id']),
            doc,
        )
    return docs


def passport_json(
    identity_doc: dict,
    snapshot_docs: List[dict],
    *,
    evidence: Optional[List[dict]] = None,
    user: Optional[User] = None,
    remaining: Optional[int] = None,
    can_undo_deinstall: bool = False,
) -> Dict[str, Any]:
    """The passport body as ``user`` may see it (people stripped for an
    anonymous caller, 8.101): what compose answers, and the base of every
    export (JSON-LD, CERO, PDF; 8.116 f)."""
    try:
        body = passport_body(identity_doc, snapshot_docs)
    except Exception as exc:
        raise internal_error(exc, 'passport body validation')
    if remaining is not None:              # a batch (8.105)
        body['identity']['remaining'] = remaining
    body['identity']['can_undo_deinstall'] = can_undo_deinstall
    if evidence is not None:               # ?include=evidence (7.2)
        body['evidence'] = evidence
    return for_viewer(body, user)


def _passport_response(
    identity_doc: dict,
    snapshot_docs: List[dict],
    *,
    etag: Optional[str] = None,
    status_code: int = status.HTTP_200_OK,
    anonymous_public: bool = False,
    evidence: Optional[List[dict]] = None,
    user: Optional[User] = None,
    remaining: Optional[int] = None,
    can_undo_deinstall: bool = False,
) -> JSONResponse:
    response_body = passport_json(identity_doc, snapshot_docs,
                                  evidence=evidence, user=user,
                                  remaining=remaining,
                                  can_undo_deinstall=can_undo_deinstall)
    resolved_etag = etag or viewer_etag(
        _compute_passport_etag(identity_doc, snapshot_docs, remaining), user)
    return JSONResponse(
        status_code=status_code,
        content=response_body,
        headers=viewer_headers(anonymous_public=anonymous_public,
                               etag=resolved_etag),
    )


async def _next_snapshot_version(
    snapshots,
    identity_id: str,
) -> int:
    """Return max(existing version) + 1 for one identity."""
    doc = await snapshots.find_one(
        {'identity_id': identity_id},
        sort=[('version', -1)],
        projection={'version': 1},
    )
    if doc is None:
        return 0
    return int(doc['version']) + 1


async def _resolve_snapshot_name(
    snapshots,
    identity_doc: dict,
    requested_name: Optional[str],
) -> str:
    trimmed = (requested_name or '').strip()
    if trimmed and trimmed.lower() != 'unnamed component':
        return trimmed

    current_snapshot_id = identity_doc.get('current_snapshot_id')
    if current_snapshot_id:
        current = await snapshots.find_one(
            {'_id': current_snapshot_id},
            {'name': 1},
        )
        if current and current.get('name'):
            return str(current['name'])

    catalog_number = identity_doc.get('catalog_number')
    if catalog_number is not None:
        return f'Component #{catalog_number}'
    return 'Unnamed Component'


@router.get(
    '/identities/{identity_id}/children',
    summary='List identities that list this identity as a parent',
)
async def list_identity_children(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    identity_id: str,
):
    """
    Reverse lookup of ``parent_identities``.

    Returns catalog rows (same shape as ``GET /identities?expand=shallow``),
    including exited and unpublished children. Anonymous callers who can read a public parent only see
    public children.
    """
    validate_uuid(identity_id, label='identity id')
    identity_doc = await ensure_identity_read_access(
        request,
        identity_id,
        current_user,
        projection={'_id': 1, 'is_public': 1},
    )

    identity_match = and_match(
        children_identity_match(identity_id),
        await visible_identity_match(request, viewer_of(current_user)),
    )
    try:
        pipeline = build_list_pipeline(
            snapshots_collection=request.app.mongodb_component_snapshots.name,
            identity_match=identity_match,
            snapshot_match={},
            sortkey='_id',
            sort_order=1,
            page=0,
            size=0,
            include_username=True,
            current_user_id=current_user.id if current_user else None,
            reserved_filter=None,
        )
        docs = await aggregate_identities(request, pipeline)
    except PyMongoError:
        log.exception('list_identity_children DB error')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )

    docs.sort(
        key=lambda doc: (
            doc.get('catalog_number') is None,
            doc.get('catalog_number')
            if isinstance(doc.get('catalog_number'), (int, float))
            else 0,
            str(doc.get('_id') or ''),
        )
    )

    try:
        content = for_viewer([catalog_row(doc) for doc in docs],
                             current_user)
    except Exception as exc:
        raise internal_error(exc, 'child row validation')
    anonymous_public = (
        current_user is None and identity_allows_anonymous_read(identity_doc)
    )
    return JSONResponse(
        status_code=200,
        content=content,
        headers=viewer_headers(anonymous_public=anonymous_public),
    )


_IDENTITY_LINEAGE_PROJECTION = {
    '_id': 1,
    'parent_identities': 1,
    'catalog_number': 1,
    'original_function': 1,
    'exit': 1,
    'is_public': 1,
    'current_snapshot_id': 1,
    'dataset': 1,
    'created_by_user_id': 1,
    'withdrawn': 1,
}

_SNAPSHOT_LINEAGE_PROJECTION = {
    '_id': 1,
    'identity_id': 1,
    'version': 1,
    'status': 1,
    'superseded_by': 1,
    'added_by_user_id': 1,
    'name': 1,
}


async def _collect_lineage_identity_docs(
    identities_col,
    *,
    root_doc: Dict[str, Any],
    max_depth: int,
    visibility: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    collected: Dict[str, Dict[str, Any]] = {str(root_doc['_id']): root_doc}

    frontier = {
        str(pid)
        for pid in (root_doc.get('parent_identities') or [])
        if pid and str(pid) not in collected
    }
    for _ in range(max_depth):
        pending = [pid for pid in frontier if pid not in collected]
        if not pending:
            break
        query = and_match({'_id': {'$in': pending}}, visibility)
        docs = await identities_col.find(
            query,
            _IDENTITY_LINEAGE_PROJECTION,
        ).to_list(length=None)
        frontier = set()
        for doc in docs:
            ident_id = str(doc['_id'])
            collected[ident_id] = doc
            for pid in doc.get('parent_identities') or []:
                if pid and str(pid) not in collected:
                    frontier.add(str(pid))

    frontier = {str(root_doc['_id'])}
    for _ in range(max_depth):
        query = and_match({'parent_identities': {'$in': list(frontier)}},
                          visibility)
        docs = await identities_col.find(
            query,
            _IDENTITY_LINEAGE_PROJECTION,
        ).to_list(length=None)
        next_frontier: set = set()
        for doc in docs:
            ident_id = str(doc['_id'])
            if ident_id in collected:
                continue
            collected[ident_id] = doc
            next_frontier.add(ident_id)
        if not next_frontier:
            break
        frontier = next_frontier

    return collected


@router.get(
    '/identities/{identity_id}/provenance',
    summary='Lineage graph of related identities and snapshots',
)
async def get_identity_provenance(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    identity_id: str,
    depth: int = Query(
        DEFAULT_PROVENANCE_DEPTH,
        ge=1,
        le=MAX_PROVENANCE_DEPTH,
        description='Max ancestor/descendant hops',
    ),
):
    """
    Walk ``parent_identities`` up and down from this identity, then attach
    each identity's snapshot versions. Anonymous callers who can read a
    public root only see public relatives.
    """
    validate_uuid(identity_id, label='identity id')
    identity_doc = await ensure_identity_read_access(
        request,
        identity_id,
        current_user,
        projection=_IDENTITY_LINEAGE_PROJECTION,
    )
    visibility = await visible_identity_match(request,
                                              viewer_of(current_user))
    identities_col = await get_identities_col(request)
    snapshots_col = await get_snapshots_col(request)

    try:
        lineage = await _collect_lineage_identity_docs(
            identities_col,
            root_doc=identity_doc,
            max_depth=depth,
            visibility=visibility,
        )
        identity_ids = list(lineage.keys())
        snapshot_docs: List[Dict[str, Any]] = []
        if identity_ids:
            cursor = snapshots_col.find(
                {'identity_id': {'$in': identity_ids}},
                _SNAPSHOT_LINEAGE_PROJECTION,
            )
            snapshot_docs = await cursor.to_list(length=None)
    except PyMongoError:
        log.exception('get_identity_provenance DB error')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )

    snapshots_by_identity: Dict[str, List[Dict[str, Any]]] = {}
    for snap in snapshot_docs:
        ident_id = str(snap.get('identity_id') or '')
        if not ident_id:
            continue
        snapshots_by_identity.setdefault(ident_id, []).append(snap)
    # drafts / pending / rejected only for their author and moderator(D)
    for ident_id, snaps in snapshots_by_identity.items():
        snapshots_by_identity[ident_id] = await visible_snapshot_docs(
            request, current_user, lineage[ident_id], snaps, tombstones=True)

    graph = build_provenance_graph(
        root_identity_id=identity_id,
        identities=lineage,
        snapshots_by_identity=snapshots_by_identity,
    )
    graph = for_viewer(graph, current_user)
    anonymous_public = (
        current_user is None and identity_allows_anonymous_read(identity_doc)
    )
    return JSONResponse(
        status_code=200,
        content=graph,
        headers=viewer_headers(anonymous_public=anonymous_public),
    )


@router.get(
    '/identities/{identity_id}/snapshots',
    summary='List snapshot versions for an identity (summary rows)',
    response_model=List[SnapshotSummaryItem],
    response_model_by_alias=True,
)
async def list_identity_snapshots(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    identity_id: str,
):
    """Return all snapshots for one identity, ordered by version ascending."""
    validate_uuid(identity_id, label='identity id')

    identity_doc = await ensure_identity_read_access(
        request,
        identity_id,
        current_user,
        projection={'_id': 1, 'current_snapshot_id': 1, 'is_public': 1},
    )

    snapshots = await get_snapshots_col(request)
    current_snapshot_id = identity_doc.get('current_snapshot_id')
    projection = {
        '_id': 1,
        'identity_id': 1,
        'version': 1,
        'status': 1,
        'name': 1,
        'effective_from': 1,
        'effective_from_precision': 1,
        'supersedes': 1,
        'superseded_by': 1,
        'added_by_user_id': 1,
        'added_by_username': 1,
        'status_changed_at': 1,
        'derivation': 1,
        'created': 1,
        'lastmodified': 1,
    }

    try:
        cursor = snapshots.find(
            {'identity_id': identity_id},
            projection,
        ).sort('version', 1)
        docs = await visible_snapshot_docs(
            request, current_user, identity_doc,
            await cursor.to_list(length=None), tombstones=True)
    except PyMongoError:
        log.exception('list_identity_snapshots DB error')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )

    items: List[Dict[str, Any]] = []
    for doc in docs:
        row = {
            **doc,
            'is_current': doc.get('_id') == current_snapshot_id,
            'geometry_failed': geometry_failed(doc),
        }
        try:
            items.append(
                SnapshotSummaryItem.model_validate(row).model_dump(
                    by_alias=True
                )
            )
        except Exception as exc:
            raise internal_error(exc, 'snapshot summary validation')

    return JSONResponse(status_code=200,
                        content=for_viewer(items, current_user))


async def _identity_as_of(request: Request, user: Optional[User],
                          identity_id: str, at: str) -> JSONResponse:
    """Old values may name people: members of D and admin only (8.36)."""
    from .change_log import as_of_body
    doc = await (await get_identities_col(request)).find_one(
        {'_id': identity_id})
    viewer = viewer_of(user)
    dataset = await dataset_of(request, doc.get('dataset'))
    if not dataset_roles(viewer, dataset):
        raise HTTPException(status_code=403,
                            detail='Earlier versions are for members of the '
                                   'dataset.')
    return JSONResponse(status_code=200,
                        content=await as_of_body(request, 'identity', doc, at))


@router.get(
    '/identities/{identity_id}',
    summary='Get one identity (shallow, passport, or identity-only)',
)
async def get_identity(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    identity_id: str,
    expand: ExpandMode = Query(
        'shallow',
        description=(
            'shallow=catalog row; '
            'current_snapshot={identity,snapshots[]}; none=identity only'
        ),
    ),
    as_of: Optional[str] = Query(
        None, description='the identity as it was at this ISO date '
                          '(members of D and admin; section 3.8)'),
):
    validate_uuid(identity_id, label='identity id')

    await ensure_identity_read_access(request, identity_id, current_user)
    if as_of is not None:
        return await _identity_as_of(request, current_user, identity_id,
                                     as_of)

    if expand == 'shallow':
        row = await shallow_row_for_identity(request, identity_id)
        return JSONResponse(status_code=200,
                            content=for_viewer(row, current_user))

    identities = await get_identities_col(request)
    identity_doc = await identities.find_one({'_id': identity_id})
    if identity_doc is None:
        raise HTTPException(
            status_code=404,
            detail=f'Identity {identity_id} not found',
        )

    anonymous_public = (
        current_user is None and identity_allows_anonymous_read(identity_doc)
    )

    if expand == 'none':
        try:
            body = identity_body(identity_doc)
        except Exception as exc:
            raise internal_error(exc, 'identity validation')
        pieces_left = await remaining_of(request, identity_doc)
        if pieces_left is not None:
            body['remaining'] = pieces_left
        body['can_undo_deinstall'] = await _can_undo_deinstall(
            request, identity_doc, current_user)
        return JSONResponse(
            status_code=200,
            content=for_viewer(body, current_user),
            headers=viewer_headers(anonymous_public=anonymous_public),
        )

    snapshots = await get_snapshots_col(request)
    current_snapshot_id = identity_doc.get('current_snapshot_id')
    if not current_snapshot_id:              # no published snapshot (8.17)
        return _passport_response(identity_doc, [],
                                  anonymous_public=anonymous_public,
                                  user=current_user)
    pieces_left = await remaining_of(request, identity_doc)
    snapshot_doc = await snapshots.find_one({'_id': current_snapshot_id})
    if snapshot_doc is None:
        raise HTTPException(
            status_code=500,
            detail=f'current_snapshot_id={current_snapshot_id} not found',
        )
    await refresh_snapshot_photo_count(
        request, str(snapshot_doc['_id']), snapshot_doc
    )
    return _passport_response(
        identity_doc,
        [snapshot_doc],
        anonymous_public=anonymous_public,
        user=current_user,
        remaining=pieces_left,
    )


async def _can_undo_deinstall(
    request: Request, identity_doc: Dict[str, Any], user: Optional[User]
) -> bool:
    """Whether the undo of the deinstall act is open (8.115 a) for this
    caller: asked only of a moderator(D) or an admin (only they can act on
    it) and only of a piece that looks deinstalled, so the common read costs
    nothing; False for everyone else without a query."""
    if user is None:
        return False
    dataset = await dataset_of(request, identity_doc.get('dataset'))
    if 'moderator' not in dataset_roles(viewer_of(user), dataset):
        return False
    origin = identity_doc.get('origin') or {}
    if origin.get('planned') or origin.get('kind') not in (
            'deinstallation', 'demolition'):
        return False
    from .identity_edit import undo_deinstall_refusal
    return await undo_deinstall_refusal(request, identity_doc) is None


@dataclass
class PassportRead:
    """What the passport's read path found for one caller: the documents the
    caller may see and the ETag of that representation (viewer-specific)."""
    identity_doc: Dict[str, Any]
    snapshot_docs: List[Dict[str, Any]]
    evidence: Optional[List[Dict[str, Any]]]
    remaining: Optional[int]
    etag: str
    anonymous_public: bool
    can_undo_deinstall: bool = False


async def read_passport(
    request: Request,
    current_user: Optional[User],
    identity_id: str,
    *,
    snapshots: Optional[str] = None,
    include: Optional[str] = None,
) -> PassportRead:
    """The passport's read path (3.6, 8.13, 8.101): the visibility rule, the
    snapshots the caller may see, the evidence as the caller sees it and the
    viewer-specific ETag. Compose and every export (8.116 f) read through
    it, so they answer 401 / 403 alike and never show more."""
    validate_uuid(identity_id, label='identity id')

    snapshots_col = await get_snapshots_col(request)

    identity_doc = await ensure_identity_read_access(
        request,
        identity_id,
        current_user,
    )
    anonymous_public = (
        current_user is None and identity_allows_anonymous_read(identity_doc)
    )

    mode, snapshot_ids = _parse_snapshots_query(snapshots)

    snapshot_docs = await _resolve_passport_snapshot_docs(
        request,
        identity_id=identity_id,
        identity_doc=identity_doc,
        snapshots_col=snapshots_col,
        mode=mode,
        snapshot_ids=snapshot_ids,
    )
    visible = await visible_snapshot_docs(
        request, current_user, identity_doc, snapshot_docs)
    if mode == 'ids' and len(visible) < len(snapshot_docs):
        raise deny_read(viewer_of(current_user))
    snapshot_docs = visible
    pieces_left = await remaining_of(request, identity_doc)
    etag = _compute_passport_etag(identity_doc, snapshot_docs, pieces_left)
    can_undo = await _can_undo_deinstall(request, identity_doc,
                                         current_user)
    if can_undo:
        # a later record can close the undo without changing the identity
        etag = hashlib.sha256(f'{etag}::undo'.encode('utf-8')).hexdigest()
    evidence = None
    if 'evidence' in {part.strip() for part in (include or '').split(',')}:
        from .evidence_service import published_bodies, viewer_context
        evidence = await published_bodies(request, current_user,
                                          identity_doc)
        tier, _ = await viewer_context(request, viewer_of(current_user),
                                       identity_doc)
        # the evidence and what the caller may see of it (its tier: people,
        # reasons) change the representation: they belong in the ETag
        etag = hashlib.sha256('::'.join([etag, tier, *(
            f'{e["_id"]}:{e.get("etag")}:{e.get("lastmodified")}'
            for e in evidence)]).encode('utf-8')).hexdigest()
    return PassportRead(
        identity_doc=identity_doc, snapshot_docs=snapshot_docs,
        evidence=evidence, remaining=pieces_left,
        etag=viewer_etag(etag, current_user),
        anonymous_public=anonymous_public,
        can_undo_deinstall=can_undo)


JSONLD_MEDIA_TYPE = 'application/ld+json'


@router.get(
    '/identities/{identity_id}/compose',
    summary='Component passport (identity + snapshot(s))',
    response_model=ComponentPassport,
    response_model_by_alias=True,
)
async def get_identity_passport(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    identity_id: str,
    snapshots: Optional[str] = Query(
        default=None,
        description=(
            'Which snapshots to include: omitted or "current" = live '
            'current_snapshot_id; "all" = every version; or one or more '
            'snapshot UUIDs (comma-separated).'
        ),
    ),
    include: Optional[str] = Query(
        default=None,
        description=(
            'evidence: add the published, non-superseded evidence records '
            'as the caller sees them (the identity block already carries '
            'the folded properties).'
        ),
    ),
    format: Literal['json', 'jsonld'] = Query(
        default='json',
        description=(
            'jsonld: the same passport as JSON-LD (the keys plus @context, '
            '@id and @type; context at /context/v1.jsonld).'
        ),
    ),
):
    """
    Return ``{identity, snapshots[]}``.

    - Default / ``?snapshots=current``: live ``current_snapshot_id``.
    - ``?snapshots=all``: every version (ascending by version).
    - ``?snapshots=<uuid>`` or comma-separated UUIDs: specific versions.
    - ``?format=jsonld``: the same body as JSON-LD (spec 7.8).
    """
    read = await read_passport(request, current_user, identity_id,
                               snapshots=snapshots, include=include)
    etag = read.etag
    if format == 'jsonld':
        etag = hashlib.sha256(f'{etag}::jsonld'.encode('utf-8')).hexdigest()

    if_none_match = request.headers.get('if-none-match')
    if if_none_match and if_none_match == etag:
        return not_modified_response(etag, **viewer_headers(
            anonymous_public=read.anonymous_public))

    if format == 'jsonld':
        body = passport_json(
            read.identity_doc, read.snapshot_docs, evidence=read.evidence,
            user=current_user, remaining=read.remaining,
            can_undo_deinstall=read.can_undo_deinstall)
        base = jsonld_export.site_base(str(request.base_url))
        document = jsonld_export.to_jsonld(
            body, base=base,
            context_url=f'{jsonld_export.api_base(str(request.base_url))}'
                        f'/context/{jsonld_export.CONTEXT_VERSION}.jsonld')
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=document,
            media_type=JSONLD_MEDIA_TYPE,
            headers=viewer_headers(anonymous_public=read.anonymous_public,
                                   etag=etag))

    return _passport_response(
        read.identity_doc,
        read.snapshot_docs,
        etag=etag,
        anonymous_public=read.anonymous_public,
        evidence=read.evidence,
        user=current_user,
        remaining=read.remaining,
        can_undo_deinstall=read.can_undo_deinstall,
    )
