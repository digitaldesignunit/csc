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
* ``POST /datasets/{did}/members`` --- ``moderator(D)``: in a reviewed
  dataset an existing account (exact email) is added and notified, any other
  address invited; in a dataset an admin has not reviewed yet every address is
  invited, whether or not it has an account (8.144 b)
* ``POST /invitations/preview`` and ``POST /invitations/accept`` --- the
  signed-in account whose address the invitation names: what the invitation
  offers, and the consent that grants it (the page ``/invite``)

The mails of invitations are capped at 50 per user per day (admins are
exempt), counted from ``invitations.mail_log`` so that the count survives a
restart and holds across the workers (8.144 c).

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
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr, Field

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import Dataset, Invitation
from apps.catalog.models import User
from apps.catalog.permissions import dataset_roles
from apps.catalog.vocab import DATASET_ROLES, DatasetRole
from services import email_service
from .access import (
    deny_write,
    load_dataset,
    load_datasets,
    load_invitation,
    viewer_of,
)
from .auth import get_current_active_user
from .catalog_common import now_iso
from limiter import limiter, signed_in_or_ip

from logging_setup import get_logger

log = get_logger(__name__)

router = APIRouter()

InvitationState = Literal['open', 'used', 'expired', 'revoked']
DEFAULT_EXPIRES_DAYS = 14
# invitation mails one non-admin user may send in 24 hours: new, resent and
# member-by-email invitations (8.144 c)
INVITATION_MAILS_PER_DAY = 50
MAIL_LOG_KEEP = 200                  # entries kept per invitation document
ACCEPT_RATE = '30/hour'              # per user: a code is not guessed


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


class InvitationCode(BaseModel):
    """The code of the link in the mail."""
    code: str = Field(min_length=8, max_length=64)


class InvitationPreview(BaseModel):
    """What an invitation offers, for the account it is addressed to."""
    dataset: Optional[str] = None
    dataset_name: Optional[str] = None
    roles: List[DatasetRole]
    expires_at: str
    inviter_name: Optional[str] = None


class InvitationAccepted(BaseModel):
    dataset: Optional[str] = None
    dataset_name: Optional[str] = None
    roles: List[DatasetRole]            # the roles held in the dataset now


def _view(doc: Dict[str, Any]) -> InvitationView:
    return InvitationView(**{k: v for k, v in doc.items()
                             if k not in ('code_sha256', 'mail_log')},
                          state=invitation_state(doc))


def _ordered(roles) -> List[str]:
    return [r for r in DATASET_ROLES if r in roles]


async def _require_invite(request: Request, user: User,
                          dataset_slug: Optional[str]) -> Optional[Dataset]:
    """Into a dataset: moderator(D); without one: admin (8.14)."""
    if dataset_slug is None:
        if user.role != 'admin':
            raise deny_write(viewer_of(user), 'invite without a dataset')
        return None
    return (await load_dataset(request, user, dataset_slug, 'invite')).record


def invite_only(dataset: Optional[Dataset], user: User) -> bool:
    """In a dataset an admin has not reviewed yet (8.139 c) a moderator
    cannot add an account directly: every address is invited and the answer
    does not tell whether it has an account (8.144 b). An admin keeps the
    direct add."""
    return (dataset is not None and not dataset.reviewed
            and user.role != 'admin')


# THE DAILY CAP ---------------------------------------------------------------
async def mails_sent_since(request: Request, user_id: str,
                           since: datetime) -> int:
    """Invitation mails ``user_id`` sent since ``since``, counted from the
    ``mail_log`` of the invitations (resends included, whoever created the
    invitation)."""
    cursor = await request.app.mongodb_invitations.aggregate([
        {'$match': {'mail_log.by': user_id}},
        {'$unwind': '$mail_log'},
        {'$match': {'mail_log.by': user_id,
                    'mail_log.at': {'$gte': _iso(since)}}},
        {'$count': 'n'},
    ])
    rows = await cursor.to_list(length=1)
    return int(rows[0]['n']) if rows else 0


async def require_mail_budget(request: Request, user: User,
                              count: int) -> None:
    """429 when ``count`` more invitation mails would pass the daily cap of
    a non-admin user."""
    if user.role == 'admin' or count < 1:
        return
    used = await mails_sent_since(
        request, user.id, datetime.now(timezone.utc) - timedelta(days=1))
    if used + count > INVITATION_MAILS_PER_DAY:
        left = max(INVITATION_MAILS_PER_DAY - used, 0)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(f'You can send at most {INVITATION_MAILS_PER_DAY} '
                    f'invitation mails a day, and {left} are left in the '
                    f'last 24 hours. Try again later.'))


async def _log_mails(request: Request, ids: List[str], user_id: str) -> None:
    """Remember that ``user_id`` sent a mail for each of these invitations
    now (an attempt counts, whatever the server said)."""
    if not ids:
        return
    await request.app.mongodb_invitations.update_many(
        {'_id': {'$in': ids}},
        {'$push': {'mail_log': {
            '$each': [{'at': _iso(datetime.now(timezone.utc)),
                       'by': user_id}],
            '$slice': -MAIL_LOG_KEEP}}})


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
        log.warning('mail not configured: %s', type(exc).__name__)
        config = {}
    mails = [invitation_mail_of(config, user, doc, code,
                                dataset.name if dataset else None)
             for doc, code in stored] if config else []
    failures = await deliver(request, mails) if mails \
        else ['mail is not configured'] * len(stored)
    for (doc, _code), failure in zip(stored, failures):
        doc['mail_failed'] = failure is not None
        if failure:
            log.warning('mail for invitation %s failed: %s', doc['_id'],
                        email_service.failure_kind(failure))
    await _mark_mail(
        request,
        [d['_id'] for (d, _), f in zip(stored, failures) if f],
        [d['_id'] for (d, _), f in zip(stored, failures) if not f])
    if mails:
        await _log_mails(request, [doc['_id'] for doc, _code in stored],
                         user.id)
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
    # an unknown code and a known one for another address answer alike: the
    # answer is no oracle for codes (8.144), so this one stays a 400
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


# ROUTES ----------------------------------------------------------------------
@router.post('/invitations', response_model=List[InviteResult],
             response_model_by_alias=True, response_model_exclude_none=True,
             summary='Invite addresses (admin, or moderator(D) into D)')
async def post_invitations(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: InvitationCreate,
):
    """One invitation per address. For an admin, and in a reviewed dataset, an
    address that already has an account is reported (``exists``) --- add it
    with the member editor. In a dataset an admin has not reviewed yet every
    address is invited and the answer is the same for all: it does not tell
    whether an address has an account (8.144 b)."""
    if body.roles and not body.dataset:
        raise HTTPException(status_code=422,
                            detail='roles are granted in a dataset')
    dataset = await _require_invite(request, current_user, body.dataset)
    blind = invite_only(dataset, current_user)
    results: Dict[str, Optional[InviteResult]] = {}
    fresh: List[str] = []
    for email in dict.fromkeys(e.strip().lower() for e in body.emails):
        if not blind and await request.app.mongodb_users.find_one(
                {'email': email}, {'_id': 1}):
            results[email] = InviteResult(email=email, result='exists')
        else:
            results[email] = None            # keeps the order asked for
            fresh.append(email)
    await require_mail_budget(request, current_user, len(fresh))
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
    """Whoever may invite now may resend: the caller's current ``invite``
    permission on the invitation's dataset (an admin for one without a
    dataset), not the creation of the invitation --- a moderator who was
    demoted cannot send it again (8.144 e). An open or an expired invitation
    gets a new code (the old one stops working at once) and a new expiry (the
    rule of a new invitation: ``expires_days`` from now, 14 by default), and
    is mailed again; a used or revoked one is a 409. A resend counts for the
    daily cap of mails.
    The code is in no response: only the mailbox gets it (8.124 b)."""
    coll = request.app.mongodb_invitations
    loaded = await load_invitation(request, current_user, invitation_id,
                                   'invite')
    doc, dataset = loaded.record, loaded.dataset
    state = invitation_state(doc)
    if state not in ('open', 'expired'):
        raise HTTPException(status_code=409,
                            detail=f'The invitation is {state}.')
    await require_mail_budget(request, current_user, 1)
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
        log.warning('mail for invitation %s failed: %s', invitation_id,
                    email_service.failure_kind(failures[0]))
    await _mark_mail(request, [invitation_id] if failed else [],
                     [] if failed else [invitation_id])
    await _log_mails(request, [invitation_id], current_user.id)
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
    doc = (await load_invitation(request, current_user, invitation_id,
                                 'revoke_invitation')).record
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
    In a reviewed dataset (and for an admin): the exact address of an existing
    account is added at once (roles are merged) and notified by mail; any
    other address --- any domain --- gets an invitation into D with these
    roles (8.20). In a dataset an admin has not reviewed yet every address
    gets the invitation, with the same answer and the same mail, whether or
    not it has an account: the account joins by opening the link signed in
    with that address and accepting (8.144 b).
    """
    dataset = (await load_dataset(request, current_user, did,
                                  'manage_members')).record
    email = body.email.strip().lower()
    account = None
    if not invite_only(dataset, current_user):
        account = await request.app.mongodb_users.find_one(
            {'email': email}, {'_id': 1, 'full_name': 1, 'username': 1})
    if account is None:
        await require_mail_budget(request, current_user, 1)
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
            log.warning('member notice failed: %s',
                        email_service.failure_kind(failures[0]))
    except Exception as exc:
        log.warning('member notice failed: %s', type(exc).__name__)
    return MemberByEmailResult(email=email, result='added',
                               user_id=account['_id'], mail_failed=failed)


# ACCEPT (the page /invite) ---------------------------------------------------
async def _invitation_for_account(request: Request, user: User, code: str
                                  ) -> Dict[str, Any]:
    """The open invitation with this code, addressed to this account's
    address. An unknown code and another address are the same 400 (``redeem``),
    so the answer tells nobody whether a code exists."""
    return await redeem(request, code, user.email or '')


@router.post('/invitations/preview', response_model=InvitationPreview,
             response_model_by_alias=True, response_model_exclude_none=True,
             summary='What an invitation offers (the account it names)')
@limiter.limit(ACCEPT_RATE, key_func=signed_in_or_ip)
async def preview_invitation(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: InvitationCode,
):
    """For the page ``/invite``: the dataset and the roles, only to the
    signed-in account whose address the invitation names. The code goes in
    the body, not in a URL (a URL is logged)."""
    doc = await _invitation_for_account(request, current_user, body.code)
    dataset = (await load_datasets(request)).get(doc.get('dataset') or '')
    creator = await request.app.mongodb_users.find_one(
        {'_id': doc['created_by_user_id']}, {'full_name': 1, 'username': 1})
    return InvitationPreview(
        dataset=doc.get('dataset'),
        dataset_name=dataset.name if dataset else None,
        roles=doc.get('roles') or [], expires_at=doc['expires_at'],
        inviter_name=((creator or {}).get('full_name')
                      or (creator or {}).get('username')))


@router.post('/invitations/accept', response_model=InvitationAccepted,
             response_model_by_alias=True, response_model_exclude_none=True,
             summary='Accept an invitation with an existing account')
@limiter.limit(ACCEPT_RATE, key_func=signed_in_or_ip)
async def accept_invitation(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: InvitationCode,
):
    """The consent: the signed-in account whose address the invitation names
    joins the dataset with the invited roles. An unknown code and another
    address are the same 400. The invitation works once (the compare-and-set
    of ``grant_invitation``)."""
    doc = await _invitation_for_account(request, current_user, body.code)
    await grant_invitation(request, doc, current_user.id)
    slug = doc.get('dataset')
    dataset = (await load_datasets(request)).get(slug or '')
    held = []
    if dataset is not None:
        member = next((m for m in dataset.members
                       if m.user_id == current_user.id), None)
        held = _ordered(member.roles) if member else []
    return InvitationAccepted(
        dataset=slug, dataset_name=dataset.name if dataset else None,
        roles=held)
