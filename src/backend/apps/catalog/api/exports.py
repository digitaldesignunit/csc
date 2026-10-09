#!/usr/bin/env python3.13
"""
Exports of a component passport (data model spec section 7.8; decisions 8.44
and 8.116; plan P10).

* `GET /context/v1.jsonld`
    -> the JSON-LD context (public, cacheable, versioned). The passport as
       JSON-LD is `GET /identities/{id}/compose?format=jsonld`
       (``identities.py``).

* `GET /identities/{identity_id}/export/cero`
    -> the component in CERO (Turtle; `?format=jsonld`): one literal per
       property, the conservative bound of its folded range. Only concrete
       and autoclaved aerated concrete (else 409).

* `GET /identities/{identity_id}/export/pdf`
    -> the passport summary, at most two pages.

Every export reads through the passport's read path (``read_passport``): the
same visibility, 401 / 403 and people rules as compose, viewer-specific ETags
and ``Vary: Authorization`` (8.101, 8.116 f).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import hashlib
import io
import os
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Literal, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response
from fastapi.concurrency import run_in_threadpool
from PIL import Image

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.exports import cero as cero_export
from apps.catalog.exports import jsonld as jsonld_export
from apps.catalog.exports.pdf import PassportPdfData, build_pdf
from apps.catalog.models import User
from apps.catalog.permissions import dataset_roles
from .access import dataset_of, viewer_of, visible_identity_match
from .auth import get_optional_current_user
from .catalog_common import not_modified_response
from .identities import (
    JSONLD_MEDIA_TYPE,

    passport_json,
    read_passport,
)
from .identity_filters import children_identity_match
from .public_access import viewer_headers
from limiter import limiter, signed_in_or_ip
from .snapshots import _list_photo_indices, _resolve_photo_path

router = APIRouter()

CONTEXT_CACHE = 'public, max-age=86400'
TURTLE_MEDIA_TYPE = 'text/turtle; charset=utf-8'

# an export is CPU work any anonymous caller can ask for on a public piece:
# the PDF (a render) tighter than CERO (a few literals). Counted per user for
# a signed-in caller, per client address otherwise (limiter.py, 8.117 e)
PDF_RATE = '20/minute'
CERO_RATE = '60/minute'

# the rendered PDFs by their ETag (which holds everything the PDF shows), so
# that repeated requests for a public piece do not render again; bounded
PDF_CACHE_SIZE = 64
_PDF_CACHE: 'OrderedDict[str, bytes]' = OrderedDict()


def clear_pdf_cache() -> None:
    _PDF_CACHE.clear()


def _cached_pdf(etag: str) -> Optional[bytes]:
    pdf = _PDF_CACHE.get(etag)
    if pdf is not None:
        _PDF_CACHE.move_to_end(etag)
    return pdf


def _remember_pdf(etag: str, pdf: bytes) -> None:
    _PDF_CACHE[etag] = pdf
    _PDF_CACHE.move_to_end(etag)
    while len(_PDF_CACHE) > PDF_CACHE_SIZE:
        _PDF_CACHE.popitem(last=False)


def pdf_filename(identity: Dict[str, Any]) -> str:
    """``csc-passport-<catalog number>.pdf``; the identity id where a
    component has no catalog number (as the web names the file)."""
    return f'csc-passport-{identity.get("catalog_number") or identity["_id"]}.pdf'


def _etag_of(*parts: Any) -> str:
    return hashlib.sha256('::'.join(str(p) for p in parts).encode(
        'utf-8')).hexdigest()


def _site(request: Request) -> str:
    return jsonld_export.site_base(str(request.base_url))


# CONTEXT ---------------------------------------------------------------------
@router.get(
    f'/context/{jsonld_export.CONTEXT_VERSION}.jsonld',
    summary='JSON-LD context of the passport (public)',
)
async def get_jsonld_context(request: Request):
    """The versioned ``@context`` the JSON-LD editions point to: SOSA/SSN,
    PROV-O, BOT, QUDT, IFC and bSDD terms from the vocabulary mapping
    columns. Public: a processor fetches it without signing in."""
    context = jsonld_export.build_context(_site(request))
    etag = jsonld_export.context_etag(context)
    headers = {'Cache-Control': CONTEXT_CACHE, 'ETag': etag}
    if request.headers.get('if-none-match') == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED,
                        headers=headers)
    return JSONResponse(content=context, media_type=JSONLD_MEDIA_TYPE,
                        headers=headers)


# CERO ------------------------------------------------------------------------
@router.get(
    '/identities/{identity_id}/export/cero',
    summary='The component in CERO (Turtle or JSON-LD)',
)
@limiter.limit(CERO_RATE, key_func=signed_in_or_ip)
async def export_cero(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    identity_id: str,
    format: Literal['turtle', 'jsonld'] = Query(
        default='turtle',
        description='turtle (default) or jsonld'),
):
    read = await read_passport(request, current_user, identity_id,
                               include='evidence')
    if not cero_export.is_cero_material(read.identity_doc.get('material')):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=cero_export.NOT_CONCRETE)
    etag = _etag_of(read.etag, 'cero', format)
    headers = viewer_headers(anonymous_public=read.anonymous_public,
                             etag=etag)
    if request.headers.get('if-none-match') == etag:
        return not_modified_response(etag, **{
            k: v for k, v in headers.items() if k != 'ETag'})
    body = passport_json(read.identity_doc, read.snapshot_docs,
                         evidence=read.evidence, user=current_user,
                         remaining=read.remaining)
    element = cero_export.cero_element(body, base=_site(request))
    if format == 'jsonld':
        return JSONResponse(content=cero_export.to_jsonld(element),
                            media_type=JSONLD_MEDIA_TYPE, headers=headers)
    return Response(content=cero_export.to_turtle(element),
                    media_type=TURTLE_MEDIA_TYPE, headers=headers)


# PDF -------------------------------------------------------------------------
def preview_path(request: Request, snapshot_id: Optional[str]
                 ) -> Optional[str]:
    """The file the picture of the state comes from: its preview, else its
    first photo, else None."""
    if not snapshot_id:
        return None
    path = os.path.join(request.app.snapshot_preview_dir,
                        f'{snapshot_id}.webp')
    if os.path.exists(path):
        return path
    indices = _list_photo_indices(request, snapshot_id)
    if not indices:
        return None
    try:
        return _resolve_photo_path(request, snapshot_id, indices[0])[0]
    except HTTPException:
        return None


def _file_stamp(path: Optional[str]) -> Any:
    """What tells a replaced picture from the old one: path, mtime, size."""
    if not path:
        return None
    try:
        stat = os.stat(path)
    except OSError:
        return (path, None, None)
    return (path, stat.st_mtime_ns, stat.st_size)


def _preview_bytes(path: Optional[str]) -> Optional[bytes]:
    """The picture as a JPEG of at most 700 px."""
    if not path:
        return None
    try:
        with Image.open(path) as image:
            image = image.convert('RGB')
            image.thumbnail((700, 700))
            out = io.BytesIO()
            image.save(out, format='JPEG', quality=82)
            return out.getvalue()
    except Exception:           # a file Pillow cannot read: no picture
        return None


async def _relatives(request: Request, current_user: Optional[User],
                     identity_doc: Dict[str, Any]
                     ) -> Dict[str, List[Dict[str, Any]]]:
    """Parents and children the caller may see, by id, catalog number and
    function (no name of a person)."""
    visible = await visible_identity_match(request, viewer_of(current_user))
    collection = request.app.mongodb_component_identities
    projection = {'_id': 1, 'catalog_number': 1, 'original_function': 1}
    parent_ids = identity_doc.get('parent_identities') or []
    parents = await collection.find(
        {'$and': [{'_id': {'$in': parent_ids}}, visible]}, projection
    ).to_list(length=None) if parent_ids else []
    children = await collection.find(
        {'$and': [children_identity_match(identity_doc['_id']), visible]},
        projection).sort('catalog_number', 1).to_list(length=None)
    rows = lambda docs: [{'id': d['_id'],                       # noqa: E731
                          'catalog_number': d.get('catalog_number'),
                          'original_function': d.get('original_function')}
                         for d in docs]
    return {'parents': rows(parents), 'children': rows(children)}


async def _change_info(request: Request, identity_id: str
                       ) -> Dict[str, Any]:
    log = request.app.mongodb_change_log
    count = await log.count_documents({'identity_id': identity_id})
    last = await log.find({'identity_id': identity_id}, {'at': 1}).sort(
        'at', -1).limit(1).to_list(length=1)
    return {'count': count, 'last_at': last[0]['at'] if last else None}


@router.get(
    '/identities/{identity_id}/export/pdf',
    summary='The passport summary as a PDF (at most two pages)',
)
@limiter.limit(PDF_RATE, key_func=signed_in_or_ip)
async def export_pdf(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    identity_id: str,
):
    read = await read_passport(request, current_user, identity_id,
                               include='evidence')
    identity = read.identity_doc
    viewer = viewer_of(current_user)
    dataset = await dataset_of(request, identity.get('dataset'))
    member = bool(dataset_roles(viewer, dataset))
    relatives = await _relatives(request, current_user, identity)
    change_info = await _change_info(request, identity['_id']) \
        if member else None
    snapshot_id = (read.snapshot_docs[0]['_id'] if read.snapshot_docs
                   else None)
    picture = preview_path(request, snapshot_id)

    # the PDF holds more than the passport (dataset name, relatives, the
    # change log, the picture): they belong in the ETag
    etag = _etag_of(
        read.etag, 'pdf', dataset.name, member,
        [(r['id'], r['catalog_number']) for r in
         relatives['parents'] + relatives['children']],
        change_info, _file_stamp(picture))
    headers = viewer_headers(anonymous_public=read.anonymous_public,
                             etag=etag)
    if request.headers.get('if-none-match') == etag:
        return not_modified_response(etag, **{
            k: v for k, v in headers.items() if k != 'ETag'})

    headers['Content-Disposition'] = (
        f'attachment; filename="{pdf_filename(identity)}"')
    pdf = _cached_pdf(etag)
    if pdf is not None:
        return Response(content=pdf, media_type='application/pdf',
                        headers=headers)

    body = passport_json(identity, read.snapshot_docs, evidence=read.evidence,
                         user=current_user, remaining=read.remaining)
    material = await request.app.mongodb_materials.find_one(
        {'_id': identity.get('material')}, {'label': 1})
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    # the render is CPU work: off the event loop
    preview = await run_in_threadpool(_preview_bytes, picture)
    pdf = await run_in_threadpool(build_pdf, PassportPdfData(
        body=body, dataset_name=dataset.name,
        material_label=(material or {}).get('label'),
        base=_site(request), api_base=str(request.base_url).rstrip('/'),
        generated_at=now, member=member,
        parents=relatives['parents'], children=relatives['children'],
        change_info=change_info, preview=preview))
    _remember_pdf(etag, pdf)
    return Response(content=pdf, media_type='application/pdf',
                    headers=headers)
