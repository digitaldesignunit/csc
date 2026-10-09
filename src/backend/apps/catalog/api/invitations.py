#!/usr/bin/env python3.13
"""
Invitations and adding people to datasets by email (data model spec
section 3.7, section 7.7; decisions 8.14, 8.20; plan P3).

* ``POST /invitations`` --- admin (any dataset or none) or ``moderator(D)``
  (into D): one email-bound, single-use code per address, mailed once (a
  bulk over one SMTP connection); an address whose mail failed is reported
  as ``mail_failed``
* ``POST /invitations/{iid}/resend`` --- a new code (the old one is void),
  mailed again; who may revoke may resend
* ``GET /invitations`` --- admin: all; moderator: their datasets'
* ``DELETE /invitations/{iid}`` --- revoke while unused: its creator,
  ``moderator(D)``, admin
* ``POST /datasets/{did}/members`` --- ``moderator(D)``: an existing
  account (exact email) is added and notified, any other address invited

Registration with a code lives in ``auth.py`` and uses ``redeem``.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Literal, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr, Field

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import Dataset, Invitation
from apps.catalog.models import User
from apps.catalog.permissions import Target, can, dataset_roles
from apps.catalog.vocab import DATASET_ROLES, DatasetRole
from services import email_service
from .access import deny_write, load_datasets, require, viewer_of
from .auth import get_current_active_user
from .catalog_common import now_iso

router = APIRouter()

InvitationState = Literal['open', 'used', 'expired', 'revoked']
DEFAULT_EXPIRES_DAYS = 14


# CODES -----------------------------------------------------------------------
def new_code() -> str:
    """16 base32 characters = 80 bit (8.14)."""
    return base64.b32encode(secrets.token_bytes(10)).decode('ascii')


def code_sha256(code: str) -> str:
    raw = code.strip().upper().encode('ascii', 'ignore')
    return hashlib.sha256(raw).hexdigest()


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def invitation_state(doc: Dict[str, Any],
                     now: Optional[datetime] = None) -> InvitationState:
    now = now or datetime.now(timezone.utc)
    if doc.get('revoked_at'):
        return 'revoked'
    if doc.get('used_at'):
        return 'used'
    expires = datetime.fromisoformat(doc['expires_at'].replace('Z', '+00:00'))
    return 'expired' if expires <= now else 'open'


# BODIES / VIEWS --------------------------------------------------------------
class InvitationCreate(BaseModel):
    emails: List[EmailStr] = Field(min_length=1, max_length=100)
    dataset: Optional[str] = None
    roles: List[DatasetRole] = Field(default_factory=list)
    expires_days: int = Field(DEFAULT_EXPIRES_DAYS, ge=1, le=90)


class InvitationView(BaseModel):
    id: str = Field(alias='_id')
    email: str
    dataset: Optional[str] = None
    roles: List[DatasetRole]
    created_by_user_id: str
    created: str
    expires_at: str
    used_at: Optional[str] = None
    used_by_user_id: Optional[str] = None
    revoked_at: Optional[str] = None
    mail_failed: bool = False
    state: InvitationState

    model_config = {'populate_by_name': True}


class InviteResult(BaseModel):
    email: str
    result: Literal['invited', 'exists', 'mail_failed']
    invitation: Optional[InvitationView] = None


class MemberByEmail(BaseModel):
    email: EmailStr
    roles: List[DatasetRole] = Field(min_length=1)


class MemberByEmailResult(BaseModel):
    email: str
    result: Literal['added', 'invited']
    user_id: Optional[str] = None
    invitation: Optional[InvitationView] = None
    # the notice (or the invitation) was not mailed; the membership or the
    # invitation stands (8.124 b)
    mail_failed: bool = False


def _view(doc: Dict[str, Any]) -> InvitationView:
    return InvitationView(**{k: v for k, v in doc.items()
                             if k != 'code_sha256'},
                          state=invitation_state(doc))


def _ordered(roles) -> List[str]:
    return [r for r in DATASET_ROLES if r in roles]


async def _dataset_or_404(request: Request, slug: str) -> Dataset:
    dataset = (await load_datasets(request)).get(slug)
    if dataset is None:
        raise HTTPException(status_code=404,
                            detail=f'Dataset {slug} not found')
    return dataset


async def _require_invite(request: Request, user: User,
                          dataset_slug: Optional[str]) -> Optional[Dataset]:
    """Into a dataset: moderator(D); without one: admin (8.14)."""
    if dataset_slug is None:
        if user.role != 'admin':
            raise deny_write(viewer_of(user), 'invite without a dataset')
        return None
    dataset = await _dataset_or_404(request, dataset_slug)
    await require(request, user, 'invite', dataset=dataset)
    return dataset


# CREATE / MAIL ---------------------------------------------------------------
async def store_invitation(request: Request, user: User, email: str,
                           dataset: Optional[Dataset], roles: List[str],
                           expires_days: int = DEFAULT_EXPIRES_DAYS
                           ) -> tuple:
    """Store one invitation; ``(document, code)``. The code is in no
    response: it goes to the mailbox only, a code sign-up counts as verified
    at once (8.14)."""
    code = new_code()
    now = datetime.now(timezone.utc)
    doc = Invitation.model_validate({
        '_id': str(uuid.uuid4()), 'email': email.strip().lower(),
        'code_sha256': code_sha256(code),
        'dataset': dataset.id if dataset else None,
        'roles': _ordered(roles), 'created_by_user_id': user.id,
        'created': _iso(now),
        'expires_at': _iso(now + timedelta(days=expires_days)),
    }).model_dump(by_alias=True, mode='json')
    await request.app.mongodb_invitations.insert_one(doc)
    return doc, code


def invitation_mail_of(config: Dict[str, str], user: User,
                       doc: Dict[str, Any], code: str,
                       dataset_name: Optional[str]) -> email_service.Mail:
    return email_service.invitation_mail(
        config, doc['email'], code, user.full_name or user.username,
        user.email, dataset_name, doc['roles'], doc['expires_at'])


async def deliver(request: Request, mails: List[email_service.Mail]
                  ) -> List[Optional[str]]:
    """Send these mails off the event loop over one SMTP connection; per
    mail None (sent) or the error text. A server that cannot be reached
    fails them all, it never raises."""
    if not mails:
        return []
    try:
        config = email_service.load_email_config()
        return await run_in_threadpool(email_service.send_mails, config,
                                       mails)
    except Exception as exc:
        return [f'{type(exc).__name__}: {exc}'] * len(mails)


async def _mark_mail(request: Request, ids_failed: List[str],
                     ids_sent: List[str]) -> None:
    """Remember which invitations the mail did not reach."""
    coll = request.app.mongodb_invitations
    if ids_failed:
        await coll.update_many({'_id': {'$in': ids_failed}},
                               {'$set': {'mail_failed': True}})
    if ids_sent:
        await coll.update_many({'_id': {'$in': ids_sent}},
                               {'$set': {'mail_failed': False}})


async def create_invitations(request: Request, user: User,
                             emails: List[str], dataset: Optional[Dataset],
                             roles: List[str],
                             expires_days: int = DEFAULT_EXPIRES_DAYS
                             ) -> List[Dict[str, Any]]:
    """Store one invitation per address and mail them all over one
    connection; each returned document has ``mail_failed`` set from what
    the send said (the invitation stays either way)."""
    stored = [await store_invitation(request, user, email, dataset, roles,
                                     expires_days) for email in emails]
    try:
        config = email_service.load_email_config()
    except Exception as exc:
        print(f'[INVITE] mail not configured: {exc}')
        config = {}
    mails = [invitation_mail_of(config, user, doc, code,
                                dataset.name if dataset else None)
             for doc, code in stored] if config else []
    failures = await deliver(request, mails) if mails \
        else ['mail is not configured'] * len(stored)
    for (doc, _code), failure in zip(stored, failures):
        doc['mail_failed'] = failure is not None
        if failure:
            print(f'[INVITE] mail to {doc["email"]} failed: {failure}')
    await _mark_mail(
        request,
        [d['_id'] for (d, _), f in zip(stored, failures) if f],
        [d['_id'] for (d, _), f in zip(stored, failures) if not f])
    return [doc for doc, _code in stored]


async def create_invitation(request: Request, user: User, email: str,
                            dataset: Optional[Dataset], roles: List[str],
                            expires_days: int = DEFAULT_EXPIRES_DAYS
                            ) -> Dict[str, Any]:
    """One invitation, mailed (see ``create_invitations``)."""
    return (await create_invitations(request, user, [email], dataset, roles,
                                     expires_days))[0]


async def redeem(request: Request, code: str, email: str) -> Dict[str, Any]:
    """The open invitation for this code and address, or 400 (8.14)."""
    doc = await request.app.mongodb_invitations.find_one(
        {'code_sha256': code_sha256(code)})
    if doc is None or doc['email'] != email.strip().lower():
        raise HTTPException(
            status_code=400,
            detail='This invitation code is not valid for this email '
                   'address.')
    state = invitation_state(doc)
    if state != 'open':
        raise HTTPException(status_code=400,
                            detail=f'This invitation is {state}.')
    return doc


async def grant_invitation(request: Request, doc: Dict[str, Any],
                           user_id: str) -> None:
    """Mark used and grant its dataset roles (on registration)."""
    now = now_iso()
    result = await request.app.mongodb_invitations.update_one(
        {'_id': doc['_id'], 'used_at': None, 'revoked_at': None},
        {'$set': {'used_at': now, 'used_by_user_id': user_id}})
    if result.matched_count == 0:
        raise HTTPException(status_code=409,
                            detail='The invitation was used or revoked '
                                   'meanwhile.')
    if doc.get('dataset') and doc.get('roles'):
        await _merge_roles(request, doc['dataset'], user_id, doc['roles'],
                           doc['created_by_user_id'])


async def _merge_roles(request: Request, slug: str, user_id: str,
                       roles: List[str], by_user_id: str) -> List[str]:
    dataset = (await load_datasets(request)).get(slug)
    if dataset is None:
        return []
    members = [m.model_dump(mode='json') for m in dataset.members]
    existing = next((m for m in members if m['user_id'] == user_id), None)
    if existing is None:
        existing = {'user_id': user_id, 'roles': [],
                    'added_by_user_id': by_user_id, 'added_at': now_iso()}
        members.append(existing)
    existing['roles'] = _ordered(set(existing['roles']) | set(roles))
    await request.app.mongodb_datasets.update_one(
        {'_id': slug}, {'$set': {'members': members,
                                 'lastmodified': now_iso()}})
    request.state.csc_datasets = None
    return existing['roles']


async def _may_manage_invitation(request: Request, user: User,
                                 doc: Dict[str, Any]) -> Optional[Dataset]:
    """Revoke and resend: the creator, moderator(D), admin. Returns the
    invitation's dataset (or None)."""
    viewer = viewer_of(user)
    dataset = (await load_datasets(request)).get(doc.get('dataset') or '')
    target_dataset = dataset or Dataset.model_validate({
        '_id': 'none', 'name': 'none', 'created': now_iso(),
        'lastmodified': now_iso()})
    if not can(viewer, 'revoke_invitation', Target(
            dataset=target_dataset, kind='invitation',
            author_id=doc['created_by_user_id'])):
        raise deny_write(viewer, 'revoke invitation')
    return dataset


# ROUTES ----------------------------------------------------------------------
@router.post('/invitations', response_model=List[InviteResult],
             response_model_by_alias=True, response_model_exclude_none=True,
             summary='Invite addresses (admin, or moderator(D) into D)')
async def post_invitations(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: InvitationCreate,
):
    """One invitation per address; an address that already has an
    account is reported (``exists``) --- add it with the member editor."""
    if body.roles and not body.dataset:
        raise HTTPException(status_code=422,
                            detail='roles are granted in a dataset')
    dataset = await _require_invite(request, current_user, body.dataset)
    results: Dict[str, Optional[InviteResult]] = {}
    fresh: List[str] = []
    for email in dict.fromkeys(e.strip().lower() for e in body.emails):
        if await request.app.mongodb_users.find_one({'email': email},
                                                    {'_id': 1}):
            results[email] = InviteResult(email=email, result='exists')
        else:
            results[email] = None            # keeps the order asked for
            fresh.append(email)
    docs = await create_invitations(request, current_user, fresh, dataset,
                                    body.roles, body.expires_days)
    for doc in docs:
        results[doc['email']] = InviteResult(
            email=doc['email'],
            result='mail_failed' if doc.get('mail_failed') else 'invited',
            invitation=_view(doc))
    return list(results.values())


@router.post('/invitations/{invitation_id}/resend',
             response_model=InviteResult, response_model_by_alias=True,
             response_model_exclude_none=True,
             summary='Resend an invitation: a new code, the old one void')
async def resend_invitation(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    invitation_id: str,
    expires_days: int = Query(DEFAULT_EXPIRES_DAYS, ge=1, le=90),
):
    """Whoever may revoke it may resend it. An open or an expired invitation
    gets a new code (the old one stops working at once) and a new expiry (the
    rule of a new invitation: ``expires_days`` from now, 14 by default), and
    is mailed again; a used or revoked one is a 409.
    The code is in no response: only the mailbox gets it (8.124 b)."""
    coll = request.app.mongodb_invitations
    doc = await coll.find_one({'_id': invitation_id})
    if doc is None:
        raise HTTPException(status_code=404, detail='Invitation not found')
    dataset = await _may_manage_invitation(request, current_user, doc)
    state = invitation_state(doc)
    if state not in ('open', 'expired'):
        raise HTTPException(status_code=409,
                            detail=f'The invitation is {state}.')
    now = datetime.now(timezone.utc)
    code = new_code()
    updated = {**doc, 'code_sha256': code_sha256(code),
               'expires_at': _iso(now + timedelta(days=expires_days))}
    # the old code stops working with this write
    result = await coll.update_one(
        {'_id': invitation_id, 'used_at': None, 'revoked_at': None,
         'code_sha256': doc['code_sha256']},
        {'$set': {'code_sha256': updated['code_sha256'],
                  'expires_at': updated['expires_at']}})
    if result.matched_count == 0:
        raise HTTPException(status_code=409,
                            detail='The invitation changed meanwhile.')
    failures = await deliver(request, [invitation_mail_of(
        email_service.load_email_config(), current_user, updated, code,
        dataset.name if dataset else None)])
    failed = failures[0] is not None
    if failed:
        print(f'[INVITE] mail to {doc["email"]} failed: {failures[0]}')
    await _mark_mail(request, [invitation_id] if failed else [],
                     [] if failed else [invitation_id])
    updated['mail_failed'] = failed
    return InviteResult(email=doc['email'],
                        result='mail_failed' if failed else 'invited',
                        invitation=_view(updated))


@router.get('/invitations', response_model=List[InvitationView],
            response_model_by_alias=True,
            summary='Invitations: admin all, moderators their datasets\'')
async def list_invitations(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    state: Optional[InvitationState] = Query(None),
    dataset: Optional[str] = Query(None),
):
    viewer = viewer_of(current_user)
    match: Dict[str, Any] = {}
    if not viewer.is_admin:
        moderated = [d.id for d in (await load_datasets(request)).values()
                     if 'moderator' in dataset_roles(viewer, d)]
        if not moderated:
            raise deny_write(viewer, 'list invitations')
        match['dataset'] = {'$in': moderated}
    if dataset:
        match = {'$and': [match, {'dataset': dataset}]} if match \
            else {'dataset': dataset}
    docs = await request.app.mongodb_invitations.find(match).sort(
        'created', -1).to_list(length=None)
    views = [_view(d) for d in docs]
    return [v for v in views if state is None or v.state == state]


@router.delete('/invitations/{invitation_id}', response_model=InvitationView,
               response_model_by_alias=True,
               summary='Revoke an unused invitation')
async def revoke_invitation(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    invitation_id: str,
):
    doc = await request.app.mongodb_invitations.find_one(
        {'_id': invitation_id})
    if doc is None:
        raise HTTPException(status_code=404, detail='Invitation not found')
    await _may_manage_invitation(request, current_user, doc)
    if invitation_state(doc) != 'open':
        raise HTTPException(status_code=409,
                            detail=f'The invitation is '
                                   f'{invitation_state(doc)}.')
    now = now_iso()
    await request.app.mongodb_invitations.update_one(
        {'_id': invitation_id},
        {'$set': {'revoked_at': now, 'revoked_by_user_id': current_user.id}})
    return _view({**doc, 'revoked_at': now})


@router.post('/datasets/{did}/members', response_model=MemberByEmailResult,
             response_model_by_alias=True, response_model_exclude_none=True,
             summary='Add a person by email (moderator(D)); invites unknown '
                     'addresses')
async def add_member_by_email(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    did: str,
    body: MemberByEmail,
):
    """
    The exact address of an existing account: added at once (roles are
    merged) and notified by mail. Any other address --- any domain ---
    gets an invitation into D with these roles (8.20).
    """
    dataset = await _dataset_or_404(request, did)
    await require(request, current_user, 'manage_members', dataset=dataset)
    email = body.email.strip().lower()
    account = await request.app.mongodb_users.find_one(
        {'email': email}, {'_id': 1, 'full_name': 1, 'username': 1})
    if account is None:
        doc = await create_invitation(request, current_user, email, dataset,
                                      body.roles)
        return MemberByEmailResult(email=email, result='invited',
                                   invitation=_view(doc),
                                   mail_failed=bool(doc.get('mail_failed')))
    roles = await _merge_roles(request, did, account['_id'], body.roles,
                               current_user.id)
    # the membership stands whatever the mail does (8.124 b)
    failed = True
    try:
        config = email_service.load_email_config()
        failures = await deliver(request, [email_service.member_added_mail(
            config, email,
            account.get('full_name') or account.get('username') or '',
            dataset.name, roles,
            current_user.full_name or current_user.username,
            current_user.email)])
        failed = failures[0] is not None
        if failed:
            print(f'[MEMBERS] notice to {email} failed: {failures[0]}')
    except Exception as exc:
        print(f'[MEMBERS] notice to {email} failed: {exc}')
    return MemberByEmailResult(email=email, result='added',
                               user_id=account['_id'], mail_failed=failed)
