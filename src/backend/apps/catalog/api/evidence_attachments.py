#!/usr/bin/env python3.13
"""
Evidence attachments (data model spec section 3.3, 3.3.4, 3.5, 7.2, 7.3;
I24; decisions 7.3, 7.4, 8.13; plan P6):

* ``POST /evidence/attachments`` --- one upload attached to several records;
  the server stores one copy per record (a hard link where it can)
* ``GET /evidence/{id}/attachments`` --- the list, as the viewer may see it
* ``GET /evidence/{id}/attachments/{index}`` --- the file; **signed in only**
  (8.13), whatever the component's visibility
* ``DELETE /evidence/{id}/attachments/{index}`` --- before publish the entry
  goes with its file; after publish ``moderator(D)`` removes it with a
  reason and the entry stays as a tombstone (I24); the reason ``gdpr`` also
  blanks the file name (the checksum stays)

Files are sniffed, never trusted by name or declared type: PDF byte for byte,
images through the photo pipeline (EXIF GPS, owner and serial stripped).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import asyncio
import os
from typing import Annotated, Any, Dict, List, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.evidence import files as evidence_files
from apps.catalog.evidence.projection import attachment_list
from apps.catalog.models import User
from apps.catalog.permissions import dataset_roles
from utility import read_upload_limited
from .access import (
    dataset_of,
    deny_read,
    load_identity,
    require,
    viewer_of,
)
from .auth import get_current_active_user, get_optional_current_user
from .catalog_common import (
    not_modified_response,
    now_iso,
    validate_uuid,
)
from .change_log import log_change
from .evidence_service import (
    ensure_evidence_visible,
    evidence_projection,
    load_evidence,
    validated_doc,
    viewer_context,
)

router = APIRouter()

MAX_RECORDS = 100
RETRIES = 4


def _image_budget(request: Request):
    return (request.app.snapshot_photo_max_output_bytes,
            request.app.snapshot_photo_max_long_edge_px)


async def _add_entry(request: Request, user: User, record_id: str,
                     copy: evidence_files.StoredCopy, name: str
                     ) -> Dict[str, Any]:
    """Attach the processed upload to one record: index, file, entry, log.
    Retries when the record changed meanwhile."""
    coll = request.app.mongodb_component_evidence
    root = request.app.evidence_attachments_dir
    for _ in range(RETRIES):
        doc = await coll.find_one({'_id': record_id})
        if doc is None:
            raise HTTPException(status_code=404,
                                detail=f'Evidence {record_id} not found')
        attachments = list(doc.get('attachments') or [])
        index = evidence_files.next_index(attachments)
        now = now_iso()
        entry = {'index': index, 'name': name,
                 'media_type': copy.media_type, 'size': copy.size,
                 'sha256': copy.sha256, 'uploaded_by_user_id': user.id,
                 'uploaded_at': now, 'removed': None}
        updated = validated_doc({**doc, 'attachments': [*attachments, entry],
                                 'lastmodified': now})
        await asyncio.to_thread(evidence_files.place_copy, copy, root,
                                record_id, index)
        result = await coll.replace_one(
            {'_id': record_id, 'etag': doc.get('etag')}, updated)
        if result.matched_count:
            await log_change(request, 'evidence', doc, updated,
                             by_user_id=user.id, cause='patch', at=now)
            return entry
        await asyncio.to_thread(evidence_files.remove_file, root, record_id,
                                index, copy.media_type)
    raise HTTPException(status_code=409,
                        detail=f'Evidence {record_id} changed while the file '
                               f'was attached; try again.')


async def blank_attachment_name(request: Request, evidence_id: str,
                                index: int) -> int:
    """A ``gdpr`` removal blanks the file name of that index in every
    change-log entry of the record, as the actor redaction blanks actors
    (8.70 c): the log kept the old entry, name included. Returns how many
    entries changed."""
    log = request.app.mongodb_change_log
    count = 0
    async for entry in log.find({'record_id': evidence_id}):
        touched = False
        for change in entry.get('changes') or []:
            if change.get('path') != 'attachments':
                continue
            for side in ('old', 'new'):
                for item in change.get(side) or []:
                    if isinstance(item, dict) and item.get('index') == index \
                            and item.get('name'):
                        item['name'] = ''
                        touched = True
        if touched:
            count += 1
            await log.update_one({'_id': entry['_id']},
                                 {'$set': {'changes': entry['changes']}})
    return count


@router.post('/evidence/attachments', status_code=201,
             summary='Attach one upload to several evidence records')
async def attach_file(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    file: UploadFile = File(
        ..., description='A PDF, or a JPEG, PNG or WebP image. Private '
                         'persons, faces and number plates are redacted '
                         'before upload; nothing scans file content.'),
    record_ids: List[str] = Form(
        ..., description='Evidence records that get a copy (repeat the '
                         'field, or comma-separated)'),
):
    """Before publish as any edit of the record (7.0: a draft --- author or
    ``moderator(D)``; a pending record --- ``moderator(D)``); after publish
    ``contributor(D)`` adds (add-only, I24). The permission is checked for
    every record before anything is stored. The same document twice on one
    record is refused (409)."""
    ids: List[str] = []
    for raw in record_ids:
        ids.extend(part.strip() for part in raw.split(',') if part.strip())
    ids = list(dict.fromkeys(ids))
    if not ids or len(ids) > MAX_RECORDS:
        raise HTTPException(status_code=422,
                            detail=f'record_ids: 1 to {MAX_RECORDS} records')
    records = []
    for rid in ids:
        validate_uuid(rid, label='record id')
        record = await load_evidence(request, rid)
        identity = await load_identity(request, str(record['identity_id']))
        await require(request, current_user, 'add_attachment',
                      identity=identity, evidence=record)
        if record.get('status') == 'withdrawn':
            raise HTTPException(status_code=409,
                                detail=f'{rid} is withdrawn.')
        if len(record.get('attachments') or []) \
                >= evidence_files.MAX_ATTACHMENTS:
            raise HTTPException(
                status_code=409,
                detail=f'{rid} holds {evidence_files.MAX_ATTACHMENTS} '
                       f'attachments already.')
        records.append(record)

    raw = await read_upload_limited(file, request.app.evidence_upload_limit_bytes)
    max_bytes, max_edge = _image_budget(request)
    root = request.app.evidence_attachments_dir
    try:
        copy = await asyncio.to_thread(
            evidence_files.process_upload, raw, root,
            max_image_bytes=max_bytes, max_long_edge_px=max_edge)
    except evidence_files.UnsupportedFile as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    name = evidence_files.safe_name(file.filename)
    if copy.media_type == evidence_files.JPEG:
        stem = name.rsplit('.', 1)[0] if '.' in name else name
        name = f'{stem}.jpg'
    try:
        twice = [r['_id'] for r in records if any(
            a.get('sha256') == copy.sha256 and not a.get('removed')
            for a in r.get('attachments') or [])]
        if twice:
            raise HTTPException(
                status_code=409,
                detail=f'The same file is already attached to: '
                       f'{", ".join(twice)}.')
        attached: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []
        for record in records:
            try:
                entry = await _add_entry(request, current_user,
                                         record['_id'], copy, name)
            except HTTPException as exc:
                failed.append({'record_id': record['_id'],
                               'status': exc.status_code,
                               'reason': str(exc.detail)})
                continue
            attached.append({'record_id': record['_id'],
                             'index': entry['index']})
    finally:
        await asyncio.to_thread(evidence_files.discard_temp, copy)
    if failed:
        # permissions and duplicates were checked for every record before
        # anything was stored, so this is a record that changed meanwhile:
        # say exactly which records hold the file and which do not
        raise HTTPException(status_code=409, detail={
            'message': 'The file is attached to some of the records only.',
            'attached': attached, 'failed': failed,
            'sha256': copy.sha256})
    return JSONResponse(status_code=201, content={
        'name': name, 'media_type': copy.media_type, 'size': copy.size,
        'sha256': copy.sha256, 'attached': attached})


@router.get('/evidence/{evidence_id}/attachments',
            summary='Attachments of an evidence record')
async def list_attachments(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    evidence_id: str,
):
    """The list as the viewer may see it. Anonymous readers of a public
    piece get media type, size, checksum and date --- no names, no
    uploaders --- and "sign in to download" (8.13)."""
    record, identity = await ensure_evidence_visible(
        request, evidence_id, current_user, allow_tombstone=True)
    tier, _ = await viewer_context(request, viewer_of(current_user), identity)
    dataset = await dataset_of(request, identity.get('dataset'))
    member = bool(dataset_roles(viewer_of(current_user), dataset))
    return JSONResponse(status_code=200, content=attachment_list(
        record, tier, member=member))


@router.get('/evidence/{evidence_id}/attachments/{index}',
            summary='Download an attachment (signed in)')
async def download_attachment(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    evidence_id: str,
    index: int,
):
    """Signed-in users who can see the record, whatever the component's
    visibility; anonymous callers get 401 (8.13). The files of a withdrawn
    record are for members only (8.17)."""
    viewer = viewer_of(current_user)
    if not viewer.logged_in:
        raise HTTPException(
            status_code=401, headers={'WWW-Authenticate': 'Bearer'},
            detail='Sign in to download attachments.')
    record, _ = await ensure_evidence_visible(request, evidence_id,
                                              current_user)
    entry = next((a for a in record.get('attachments') or []
                  if a['index'] == index), None)
    if entry is None:
        raise HTTPException(status_code=404, detail='Attachment not found')
    if entry.get('removed'):
        raise HTTPException(status_code=410,
                            detail='The file was removed '
                                   f'({(entry["removed"] or {}).get("at")}).')
    path = evidence_files.file_path(request.app.evidence_attachments_dir,
                                    record['_id'], index, entry['media_type'])
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail='File not found')
    is_image = entry['media_type'] == evidence_files.JPEG
    # the checksum is the validator: the bytes under an index never change
    # and an index is never reused, but a removal or a withdrawal must show
    etag = f'"{entry["sha256"]}"'
    if request.headers.get('if-none-match') == etag:
        return not_modified_response(etag, **{
            'Cache-Control': 'private, no-cache'})
    return FileResponse(
        path, media_type=entry['media_type'],
        filename=evidence_files.safe_name(entry.get('name'), 'attachment'),
        content_disposition_type='inline' if is_image else 'attachment',
        headers={'X-Content-Type-Options': 'nosniff', 'ETag': etag,
                 'Cache-Control': 'private, no-cache'})


@router.delete('/evidence/{evidence_id}/attachments/{index}',
               summary='Remove an attachment')
async def remove_attachment(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    evidence_id: str,
    index: int,
    reason: Optional[str] = Query(
        None, description='required after publish; "gdpr" also blanks the '
                          'file name'),
):
    """Before publish: author / ``moderator(D)`` as any edit, the reason is
    optional. After publish: ``moderator(D)`` with a reason. Either way the
    file is deleted and the entry stays with ``removed {at, by_user_id,
    reason}`` --- an index is never reused (I24). The reason ``gdpr`` blanks
    the name, also in the change log; the checksum stays (decision 8.13)."""
    record = await load_evidence(request, evidence_id)
    identity = await load_identity(request, str(record['identity_id']))
    viewer = viewer_of(current_user)
    if await evidence_projection(request, viewer, record, identity) \
            != 'full':
        raise deny_read(viewer)
    await require(request, current_user, 'remove_attachment',
                  identity=identity, evidence=record)
    published = record.get('status') in ('published', 'withdrawn')
    if published and not (reason or '').strip():
        raise HTTPException(status_code=422,
                            detail='reason: a published record\'s '
                                   'attachment is removed with a reason')
    coll = request.app.mongodb_component_evidence
    root = request.app.evidence_attachments_dir
    for _ in range(RETRIES):
        doc = await coll.find_one({'_id': evidence_id})
        entries = list(doc.get('attachments') or [])
        entry = next((a for a in entries if a['index'] == index), None)
        if entry is None:
            raise HTTPException(status_code=404,
                                detail='Attachment not found')
        if entry.get('removed'):
            raise HTTPException(status_code=409,
                                detail='Already removed.')
        now = now_iso()
        # the entry always stays, marked removed: an index is never reused
        # (a cached download URL must not serve another file), also in a
        # draft; before publish the reason is optional
        why = (reason or '').strip() or 'removed before publish'
        gone = {**entry, 'removed': {
            'at': now, 'by_user_id': current_user.id, 'reason': why}}
        gdpr = why.lower() == 'gdpr'
        if gdpr:
            gone['name'] = ''
        entries = [gone if a['index'] == index else a for a in entries]
        updated = validated_doc({**doc, 'attachments': entries,
                                 'lastmodified': now})
        result = await coll.replace_one(
            {'_id': evidence_id, 'etag': doc.get('etag')}, updated)
        if result.matched_count:
            await log_change(request, 'evidence', doc, updated,
                             by_user_id=current_user.id, cause='patch',
                             at=now)
            if gdpr:
                await blank_attachment_name(request, evidence_id, index)
            await asyncio.to_thread(evidence_files.remove_file, root,
                                    evidence_id, index, entry['media_type'])
            return JSONResponse(status_code=200, content={
                'ok': True, 'evidence_id': evidence_id, 'index': index,
                'tombstone': True})
    raise HTTPException(status_code=409,
                        detail='The record changed meanwhile; try again.')
