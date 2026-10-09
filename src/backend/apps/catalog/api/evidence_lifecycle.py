#!/usr/bin/env python3.13
"""
The evidence lifecycle (data model spec section 3.3.3, 3.3.4, 7.2; I13 -
I15, I22, I26 - I28; decisions 8.12, 8.16, 8.18; plan P6), as the snapshot
lifecycle of P3:

* ``POST /evidence/{id}/submit|recall|resubmit`` --- the author's steps
* ``POST /evidence/{id}/publish|reject|withdraw|reinstate`` --- ``moderator(D)``
* ``POST /evidence/{id}/supersede`` --- a correction of a published record
* ``PUT /evidence/{id}/verification`` --- the recorder's claim, a reviewer's
  four eyes
* ``PATCH /evidence/{id}``, ``DELETE /evidence/{id}``

Every write goes through the change log (I30) and, where it moves the fold,
recomputes the properties.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import asyncio
from typing import Annotated, Any, Dict, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import Actor
from apps.catalog.evidence import files as evidence_files
from apps.catalog.lifecycle import patch_problems, transition_action
from apps.catalog.models import User
from apps.catalog.permissions import dataset_roles
from apps.catalog.vocab import VERIFICATION_STATES
from .access import (
    deny_read,
    deny_write,
    dataset_of,
    identity_ever_published,
    require,
    viewer_of,
)
from .auth import get_current_active_user
from .catalog_common import now_iso
from .change_log import log_change
from .evidence_fold import recompute_properties
from .evidence_service import (
    EvidenceCreate,
    ReasonBody,
    VerificationBody,
    client_data,
    evidence_body,
    evidence_projection,
    gate_identity,
    history_entry,
    load_evidence,
    new_evidence_doc,
    prepare,
    problem_http,
    require_contributor,
    result_changed,
    stored_input,
    validated_doc,
)
from .access import load_identity

router = APIRouter()

OPEN = ('draft', 'pending')


# HELPERS ---------------------------------------------------------------------
async def _load(request: Request, evidence_id: str):
    record = await load_evidence(request, evidence_id)
    identity = await load_identity(request, str(record['identity_id']))
    return record, identity


async def _ok(request: Request, user: User, record: Dict[str, Any],
              identity: Dict[str, Any], status: int = 200) -> JSONResponse:
    # the document is re-read: a recompute may have changed nothing on it,
    # but the caller gets what is stored
    return JSONResponse(status_code=status, content=await evidence_body(
        request, viewer_of(user), record, identity))


def _transition_or_409(record: Dict[str, Any], to: str) -> str:
    action = transition_action(record.get('status'), to)
    if action is None:
        raise HTTPException(
            status_code=409,
            detail=f'A {record.get("status")} record cannot become {to} '
                   f'(I15).')
    return action


async def _step(request: Request, user: User, record: Dict[str, Any],
                identity: Dict[str, Any], verb: str, to: str) -> None:
    """The permission of ``verb`` first (401 / 403), the status after (409):
    a caller who may not act never learns the record's status."""
    await require(request, user, verb, identity=identity, evidence=record)
    if _transition_or_409(record, to) != verb:
        raise HTTPException(
            status_code=409,
            detail=f'A {record.get("status")} record cannot be '
                   f'{verb}: it needs another state (I15).')


async def _replace(request: Request, before: Dict[str, Any],
                   after: Dict[str, Any], *, guard: Dict[str, Any]) -> None:
    result = await request.app.mongodb_component_evidence.replace_one(
        {'_id': before['_id'], **guard}, after)
    if result.matched_count == 0:
        raise HTTPException(status_code=409,
                            detail='The record changed meanwhile; reload.')


async def _change_status(request: Request, user: User, record: Dict[str, Any],
                         to: str, *, reason: Optional[str] = None
                         ) -> Dict[str, Any]:
    """One status step: history entry (8.30), new etag; 409 if someone
    changed the status meanwhile."""
    now = now_iso()
    updated = {
        **record, 'status': to, 'status_changed_by_user_id': user.id,
        'status_changed_at': now, 'lastmodified': now,
        'status_history': [*(record.get('status_history') or []),
                           history_entry(record['status'], to, user.id, now,
                                         reason)]}
    updated = validated_doc(updated)
    await _replace(request, record, updated,
                   guard={'status': record['status'],
                          'etag': record.get('etag')})
    return updated


async def _open_correction(request: Request, old_id: str,
                           except_id: Optional[str] = None) -> None:
    """I14, 8.16: at most one draft / pending record names ``old_id`` in
    ``supersedes``."""
    query: Dict[str, Any] = {'supersedes': old_id, 'status': {'$in': OPEN}}
    if except_id:
        query['_id'] = {'$ne': except_id}
    other = await request.app.mongodb_component_evidence.find_one(
        query, {'_id': 1, 'status': 1})
    if other is not None:
        raise HTTPException(
            status_code=409,
            detail=f'A correction of this record is already open: '
                   f'{other["_id"]} ({other["status"]}) (I14).')


async def _link_predecessor(request: Request, user: User,
                            predecessor_id: str,
                            superseded_by: Optional[str], *,
                            expect: Optional[str]) -> Dict[str, Any]:
    """Set (or clear) ``superseded_by`` of the corrected record, guarded by
    its current value; logged (I30)."""
    coll = request.app.mongodb_component_evidence
    now = now_iso()
    before = await coll.find_one_and_update(
        {'_id': predecessor_id, 'superseded_by': expect,
         'status': 'published'},
        {'$set': {'superseded_by': superseded_by, 'lastmodified': now}})
    if before is None:
        raise HTTPException(
            status_code=409,
            detail='The record it corrects is no longer a published, '
                   'uncorrected one (I14).')
    after = {**before, 'superseded_by': superseded_by, 'lastmodified': now}
    after['etag'] = validated_doc(dict(after))['etag']
    await coll.update_one({'_id': predecessor_id},
                          {'$set': {'etag': after['etag']}})
    await log_change(request, 'evidence', before, after,
                     by_user_id=user.id, cause='patch', at=now)
    return after


# THE AUTHOR'S STEPS ----------------------------------------------------------
@router.post('/evidence/{evidence_id}/submit',
             summary='draft --> pending (author; never publishes, 8.120)')
async def submit_evidence(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    evidence_id: str,
):
    """Nobody publishes directly (8.120): for every role the submit only moves
    draft --> pending; ``/publish`` (moderator(D)) is the separate step. The
    old ``?publish=1`` of earlier clients is ignored."""
    record, identity = await _load(request, evidence_id)
    await _step(request, current_user, record, identity, 'submit',
                'pending')
    gate_identity(identity, record['observed_at'])
    pending = await _change_status(request, current_user, record, 'pending')
    return await _ok(request, current_user, pending, identity)


@router.post('/evidence/{evidence_id}/recall',
             summary='pending --> draft (author, 8.18)')
async def recall_evidence(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    evidence_id: str,
):
    record, identity = await _load(request, evidence_id)
    await _step(request, current_user, record, identity, 'recall', 'draft')
    return await _ok(request, current_user, await _change_status(
        request, current_user, record, 'draft'), identity)


@router.post('/evidence/{evidence_id}/resubmit',
             summary='rejected --> draft (author)')
async def resubmit_evidence(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    evidence_id: str,
):
    record, identity = await _load(request, evidence_id)
    await _step(request, current_user, record, identity, 'resubmit',
                'draft')
    if record.get('supersedes'):
        await _open_correction(request, record['supersedes'],
                               except_id=record['_id'])
    return await _ok(request, current_user, await _change_status(
        request, current_user, record, 'draft'), identity)


# MODERATION ------------------------------------------------------------------
async def _may(request: Request, user: User, action: str,
               record: Dict[str, Any], identity: Dict[str, Any]) -> bool:
    """``require`` without raising 401 / 403."""
    try:
        await require(request, user, action, identity=identity,
                      evidence=record)
        return True
    except HTTPException as exc:
        if exc.status_code in (401, 403):
            return False
        raise


async def _publish(request: Request, user: User, record: Dict[str, Any],
                   identity: Dict[str, Any]) -> Dict[str, Any]:
    """pending --> published (moderator(D)). Refused until the component is
    published (I26) and for a withdrawn one (I28). A correction marks the
    record it corrects as superseded, which drops it from the fold."""
    await require(request, user, 'publish', identity=identity,
                  evidence=record)
    if not await identity_ever_published(request, identity):
        raise HTTPException(
            status_code=409,
            detail='Publish the component first: evidence of an '
                   'unpublished component cannot be published (I26).')
    gate_identity(identity, record['observed_at'])
    predecessor = record.get('supersedes')
    if predecessor:
        await _link_predecessor(request, user, predecessor, record['_id'],
                                expect=None)
    try:
        published = await _change_status(request, user, record, 'published')
    except HTTPException:
        if predecessor:
            await _link_predecessor(request, user, predecessor, None,
                                    expect=record['_id'])
        raise
    await recompute_properties(request, identity['_id'])
    return published


@router.post('/evidence/{evidence_id}/publish',
             summary='pending --> published (moderator(D))')
async def publish_evidence(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    evidence_id: str,
):
    record, identity = await _load(request, evidence_id)
    await _step(request, current_user, record, identity, 'publish',
                'published')
    return await _ok(request, current_user, await _publish(
        request, current_user, record, identity), identity)


@router.post('/evidence/{evidence_id}/reject',
             summary='pending --> rejected with a reason (moderator(D))')
async def reject_evidence(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    evidence_id: str,
    body: ReasonBody,
):
    record, identity = await _load(request, evidence_id)
    await _step(request, current_user, record, identity, 'reject',
                'rejected')
    return await _ok(request, current_user, await _change_status(
        request, current_user, record, 'rejected', reason=body.reason),
        identity)


@router.post('/evidence/{evidence_id}/withdraw',
             summary='published --> withdrawn with a reason (moderator(D))')
async def withdraw_evidence(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    evidence_id: str,
    body: ReasonBody,
):
    """Out of the fold and the public tier; members keep the full record
    (8.17). Withdrawing a correction gives the record it corrected back its
    place (it stays superseded only while its correction is live)."""
    record, identity = await _load(request, evidence_id)
    await _step(request, current_user, record, identity, 'withdraw',
                'withdrawn')
    withdrawn = await _change_status(request, current_user, record,
                                     'withdrawn', reason=body.reason)
    predecessor = record.get('supersedes')
    if predecessor:
        old = await request.app.mongodb_component_evidence.find_one(
            {'_id': predecessor}, {'superseded_by': 1, 'status': 1})
        if old and old.get('superseded_by') == record['_id'] \
                and old.get('status') == 'published':
            await _link_predecessor(request, current_user, predecessor,
                                    None, expect=record['_id'])
    await recompute_properties(request, identity['_id'])
    return await _ok(request, current_user, withdrawn, identity)


@router.post('/evidence/{evidence_id}/reinstate',
             summary='withdrawn --> published (moderator(D))')
async def reinstate_evidence(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    evidence_id: str,
):
    record, identity = await _load(request, evidence_id)
    await _step(request, current_user, record, identity, 'reinstate',
                'published')
    predecessor = record.get('supersedes')
    old = None
    if predecessor:
        # a newer correction of the same record is open: it would fork (I14)
        await _open_correction(request, predecessor,
                               except_id=record['_id'])
        old = await request.app.mongodb_component_evidence.find_one(
            {'_id': predecessor}, {'superseded_by': 1, 'status': 1})
        if old and old.get('status') == 'published' \
                and old.get('superseded_by') not in (None, record['_id']):
            raise HTTPException(
                status_code=409,
                detail='The record it corrects was corrected again '
                       f'({old["superseded_by"]}); it cannot be '
                       'reinstated (I14).')
        if old and old.get('status') == 'published' \
                and old.get('superseded_by') is None:
            await _link_predecessor(request, current_user, predecessor,
                                    record['_id'], expect=None)
    published = await _change_status(request, current_user, record,
                                     'published')
    await recompute_properties(request, identity['_id'])
    return await _ok(request, current_user, published, identity)


# CORRECTION ------------------------------------------------------------------
@router.post('/evidence/{evidence_id}/supersede', status_code=201,
             summary='Correct a published record (a new pending record)')
async def supersede_evidence(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    evidence_id: str,
    body: EvidenceCreate,
):
    """contributor(D). The body is the whole new record, of the same
    method; it enters as ``pending``. On publish the old record is marked
    superseded and leaves the fold and the default lists (3.3.4). 409 if a
    correction of it is already open (I14, 8.16)."""
    old, identity = await _load(request, evidence_id)
    await require_contributor(request, current_user, 'supersede_evidence',
                              identity, evidence=old)
    if old.get('status') != 'published' or old.get('superseded_by'):
        raise HTTPException(
            status_code=409,
            detail='Only a published, uncorrected record is corrected '
                   '(I14).')
    if body.method != old['method']:
        raise problem_http('method', f'a correction has the method of the '
                                     f'record it corrects ({old["method"]}; '
                                     f'I14)')
    gate_identity(identity)
    await _open_correction(request, old['_id'])
    prepared = await prepare(request, identity, client_data(body),
                             exclude=(old['_id'],))
    doc = new_evidence_doc(identity['_id'], prepared, body, current_user,
                           status='pending', supersedes=old['_id'])
    await request.app.mongodb_component_evidence.insert_one(dict(doc))
    return await _ok(request, current_user, doc, identity, status=201)


# VERIFICATION ----------------------------------------------------------------
@router.put('/evidence/{evidence_id}/verification',
            summary='Set the verification state (recorder / reviewer)')
async def put_verification(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    evidence_id: str,
    body: VerificationBody,
):
    """The recorder toggles ``unverified`` <--> ``self_attested`` (when they
    are among the performers, and never over a reviewer's state);
    ``reviewed`` / ``accredited`` and stepping a state back to
    ``unverified`` are for ``reviewer(D)`` or admin who is neither the
    recorder nor a performer --- no admin exception (8.12, I27); a reviewer
    never sets ``self_attested``. The server sets ``by`` and ``at``;
    ``accredited`` needs a note and an accreditation covering the standard
    (I22). Changing the state of a published record recomputes the fold."""
    record, identity = await _load(request, evidence_id)
    viewer = viewer_of(current_user)
    projection = await evidence_projection(request, viewer, record, identity)
    if projection != 'full':
        raise deny_read(viewer)
    if body.state not in VERIFICATION_STATES:
        raise problem_http('state', f'one of {list(VERIFICATION_STATES)}')
    current = (record.get('verification') or {}).get('state') or 'unverified'
    soft = ('unverified', 'self_attested')
    # self_attested is the recorder's own claim: a reviewer sets reviewed,
    # accredited, or steps a state back to unverified --- never
    # self_attested (8.70 a)
    reviewer = body.state != 'self_attested' and await _may(
        request, current_user, 'review_verification', record, identity)
    recorder = (await _may(request, current_user, 'self_attest', record,
                           identity)
                and current in soft and body.state in soft)
    if not (reviewer or recorder):
        raise deny_write(viewer, f'set verification to {body.state}')
    now = now_iso()
    if body.state in ('reviewed', 'accredited'):
        verification = {'state': body.state,
                        'by': {'kind': 'user', 'user_id': current_user.id},
                        'at': now, 'note': body.note}
    elif body.state == 'self_attested':
        verification = {'state': body.state,
                        'by': {'kind': 'user',
                               'user_id': record['recorded_by_user_id']},
                        'at': now, 'note': body.note}
    else:
        verification = {'state': 'unverified', 'by': None, 'at': None,
                        'note': None}
    updated = validated_doc({**record, 'verification': verification,
                             'lastmodified': now})
    await _replace(request, record, updated,
                   guard={'etag': record.get('etag')})
    await log_change(request, 'evidence', record, updated,
                     by_user_id=current_user.id, cause='patch', at=now)
    if record.get('status') == 'published' and not record.get(
            'superseded_by'):
        await recompute_properties(request, identity['_id'])
    return await _ok(request, current_user, updated, identity)


# EDIT, DELETE ----------------------------------------------------------------
@router.patch('/evidence/{evidence_id}',
              summary='Edit a record; per-field permission (8.3, I13)')
async def patch_evidence(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    evidence_id: str,
    body: Annotated[Dict[str, Any], Body()],
):
    """
    A draft: author or ``moderator(D)``; a pending record: ``moderator(D)``
    (8.18); a rejected one: nobody. Before publish any field of the create
    body may change --- ``payload`` and ``performed_by`` are replaced as a
    whole, ``position`` is merged; resend a stored payload without its
    server-computed fields --- and the record is recomputed and checked
    again; a result change resets ``reviewed`` / ``accredited`` to
    ``unverified`` (8.12). After publish only ``notes`` and
    ``position.description`` change, by ``moderator(D)``; frozen fields
    --> 409 pointing at ``/supersede`` (I13), server-maintained fields
    --> 422.
    """
    record, identity = await _load(request, evidence_id)
    viewer = viewer_of(current_user)
    if await evidence_projection(request, viewer, record, identity) \
            != 'full':
        raise deny_read(viewer)
    dataset = await dataset_of(request, identity.get('dataset'))
    roles = dataset_roles(viewer, dataset)
    fields = {k: (list(v) if k == 'position' and isinstance(v, dict) else [])
              for k, v in body.items()}
    problems = patch_problems(
        'evidence', fields, status=record.get('status'),
        is_author=current_user.id == record.get('recorded_by_user_id'),
        is_moderator=viewer.is_admin or 'moderator' in roles)
    if problems.get('derived'):
        raise HTTPException(status_code=422, detail={
            'message': 'Server-maintained fields cannot be set.',
            'fields': problems['derived']})
    if problems.get('frozen'):
        raise HTTPException(status_code=409, detail={
            'message': 'Frozen on a published record; record a correction '
                       '(POST /evidence/{id}/supersede).',
            'fields': problems['frozen']})
    if problems.get('forbidden'):
        raise deny_write(viewer, 'edit ' + ', '.join(problems['forbidden']))
    now = now_iso()
    if record.get('status') in ('published', 'withdrawn'):
        updated = {**record}
        if 'notes' in body:
            updated['notes'] = body['notes']
        if isinstance(body.get('position'), dict):
            updated['position'] = {**(record.get('position') or {}),
                                   'description': body['position'].get(
                                       'description')}
        updated['lastmodified'] = now
        updated = validated_doc(updated)
    else:
        if 'method' in body and body['method'] != record['method']:
            raise problem_http('method', 'the method of a record is not '
                                         'changed; record a new one')
        data = stored_input(record)
        for key, value in body.items():
            if key == 'position' and isinstance(value, dict):
                data['position'] = {**data.get('position', {}), **value}
            elif key != 'notes':
                data[key] = value
        try:
            performers = [Actor.model_validate(a).model_dump(mode='json')
                          for a in data.get('performed_by') or []]
        except ValidationError as exc:
            raise problem_http(
                'performed_by', exc.errors()[0]['msg']) from exc
        prepared = await prepare(request, identity, data,
                                 exclude=(record['_id'],))
        updated = {**record, **prepared.fields, 'performed_by': performers,
                   'notes': body.get('notes', record.get('notes')),
                   'lastmodified': now}
        verification = dict(record.get('verification') or {})
        state = verification.get('state') or 'unverified'
        recorders = {a.get('user_id') for a in performers}
        if (state in ('reviewed', 'accredited')
                and result_changed(record, updated)) or (
                state == 'self_attested'
                and record['recorded_by_user_id'] not in recorders):
            updated['verification'] = {'state': 'unverified', 'by': None,
                                       'at': None, 'note': None}
        updated = validated_doc(updated)
    await _replace(request, record, updated,
                   guard={'etag': record.get('etag')})
    await log_change(request, 'evidence', record, updated,
                     by_user_id=current_user.id, cause='patch', at=now)
    return await _ok(request, current_user, updated, identity)


@router.delete('/evidence/{evidence_id}',
               summary='Delete a never-published record (author or '
                       'moderator(D))')
async def delete_evidence(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    evidence_id: str,
):
    """Only draft / pending / rejected (I15); a published one is withdrawn
    instead. Its files go with it. Refused while a core names it as its
    pair."""
    record, identity = await _load(request, evidence_id)
    viewer = viewer_of(current_user)
    if await evidence_projection(request, viewer, record, identity) \
            != 'full':
        raise deny_read(viewer)
    if record.get('status') not in ('draft', 'pending', 'rejected'):
        # for everyone who can read it, admin included (I15)
        raise HTTPException(
            status_code=409,
            detail='A published record is never deleted; withdraw it '
                   '(I15).')
    await require(request, current_user, 'delete_record', identity=identity,
                  evidence=record)
    coll = request.app.mongodb_component_evidence
    paired = await coll.find_one(
        {'payload.sampling.paired_rebound_id': record['_id']}, {'_id': 1})
    if paired is not None:
        raise HTTPException(
            status_code=409,
            detail=f'The core record {paired["_id"]} is paired with this '
                   f'one; remove that link first (8.42).')
    result = await coll.delete_one(
        {'_id': record['_id'], 'status': {'$in': ['draft', 'pending',
                                                  'rejected']}})
    if result.deleted_count:
        await asyncio.to_thread(
            evidence_files.remove_record_files,
            request.app.evidence_attachments_dir, record['_id'])
    return JSONResponse(status_code=200, content={
        'ok': True, 'evidence_id': record['_id'],
        'identity_id': identity['_id']})
